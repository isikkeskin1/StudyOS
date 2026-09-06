from __future__ import annotations

import hashlib
import re
from pathlib import Path
from uuid import uuid4

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.models.course import Course
from app.models.document import Document
from app.models.document_content import DocumentAnalysis, DocumentChunk, DocumentUnit
from app.services.chunking import chunk_text
from app.services.classification import classify_document
from app.services.extraction import DocumentExtractionError, extract_document


class DocumentProcessingError(RuntimeError):
    pass



def _normalized_text_fingerprint(text: str) -> str | None:
    normalized = re.sub(r"\s+", " ", text).strip().lower()
    if not normalized:
        return None
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest()


def _extraction_quality(
    *,
    unit_count: int,
    empty_unit_count: int,
    extracted_characters: int,
) -> float:
    if unit_count <= 0 or extracted_characters <= 0:
        return 0.0
    nonempty_ratio = max(0.0, 1.0 - empty_unit_count / unit_count)
    density = min(1.0, extracted_characters / max(1, unit_count * 200))
    return round(nonempty_ratio * density, 4)


def _duplicate_source(
    db: Session,
    document: Document,
    text_sha256: str | None,
) -> str | None:
    if text_sha256 is None:
        return None
    statement = (
        select(DocumentAnalysis.document_id)
        .join(Document, Document.id == DocumentAnalysis.document_id)
        .join(Course, Course.id == Document.course_id)
        .where(
            DocumentAnalysis.text_sha256 == text_sha256,
            Document.id != document.id,
        )
        .order_by(Document.created_at, Document.id)
    )
    user_id = db.info.get("user_id")
    if user_id:
        statement = statement.where(Course.user_id == user_id)
    return db.scalar(statement)


def process_document(db: Session, document: Document) -> DocumentAnalysis:
    try:
        extracted_units = extract_document(Path(document.storage_path), document.extension)
    except DocumentExtractionError as exc:
        db.rollback()
        persisted = db.get(Document, document.id)
        if persisted is not None:
            persisted.status = "failed"
            db.commit()
        raise DocumentProcessingError(str(exc)) from exc

    combined_text = "\n\n".join(unit.text for unit in extracted_units if unit.text)
    classification = classify_document(document.original_filename, combined_text)

    try:
        db.execute(delete(DocumentChunk).where(DocumentChunk.document_id == document.id))
        db.execute(delete(DocumentUnit).where(DocumentUnit.document_id == document.id))
        db.execute(delete(DocumentAnalysis).where(DocumentAnalysis.document_id == document.id))

        chunk_count = 0
        for unit_index, extracted in enumerate(extracted_units):
            unit_id = str(uuid4())
            unit = DocumentUnit(
                id=unit_id,
                document_id=document.id,
                unit_index=unit_index,
                locator_type=extracted.locator_type,
                locator_index=extracted.locator_index,
                source_label=extracted.source_label,
                text=extracted.text,
            )
            db.add(unit)

            for unit_chunk_index, text in enumerate(chunk_text(extracted.text)):
                db.add(
                    DocumentChunk(
                        id=str(uuid4()),
                        document_id=document.id,
                        unit_id=unit_id,
                        chunk_index=chunk_count,
                        unit_chunk_index=unit_chunk_index,
                        source_label=extracted.source_label,
                        text=text,
                        character_count=len(text),
                    )
                )
                chunk_count += 1

        extracted_characters = sum(len(unit.text) for unit in extracted_units)
        empty_unit_count = sum(not unit.text.strip() for unit in extracted_units)
        text_sha256 = _normalized_text_fingerprint(combined_text)
        analysis = DocumentAnalysis(
            document_id=document.id,
            document_type=classification.document_type,
            classifier_confidence=classification.confidence,
            unit_count=len(extracted_units),
            chunk_count=chunk_count,
            extracted_characters=extracted_characters,
            empty_unit_count=empty_unit_count,
            extraction_quality=_extraction_quality(
                unit_count=len(extracted_units),
                empty_unit_count=empty_unit_count,
                extracted_characters=extracted_characters,
            ),
            text_sha256=text_sha256,
            duplicate_of_document_id=_duplicate_source(db, document, text_sha256),
            needs_ocr=document.extension == ".pdf" and extracted_characters < 20,
        )
        db.add(analysis)
        document.status = "processed"
        db.commit()
        db.refresh(analysis)
        return analysis
    except Exception as exc:
        db.rollback()
        persisted = db.get(Document, document.id)
        if persisted is not None:
            persisted.status = "failed"
            db.commit()
        raise DocumentProcessingError("Could not persist extracted document content") from exc
