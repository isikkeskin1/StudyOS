from __future__ import annotations

from pathlib import Path
from uuid import uuid4

from sqlalchemy import delete
from sqlalchemy.orm import Session

from app.models.document import Document
from app.models.document_content import DocumentAnalysis, DocumentChunk, DocumentUnit
from app.services.chunking import chunk_text
from app.services.classification import classify_document
from app.services.extraction import DocumentExtractionError, extract_document


class DocumentProcessingError(RuntimeError):
    pass


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
        analysis = DocumentAnalysis(
            document_id=document.id,
            document_type=classification.document_type,
            classifier_confidence=classification.confidence,
            unit_count=len(extracted_units),
            chunk_count=chunk_count,
            extracted_characters=extracted_characters,
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
