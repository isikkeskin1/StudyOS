from __future__ import annotations

import hashlib
import math
from dataclasses import dataclass
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.document import Document
from app.models.document_content import DocumentChunk
from app.models.tutor_embedding_index import TutorChunkEmbedding
from app.schemas.tutor_embedding_index import TutorEmbeddingIndexRead
from app.services.tutor_embeddings import TutorEmbeddingFailure, TutorEmbeddingProvider


@dataclass(frozen=True)
class EmbeddingCacheResult:
    vectors: dict[str, list[float]]
    cache_hits: int
    embedded_now: int
    stale_reembedded: int


def _content_sha256(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _provider_identity(provider: TutorEmbeddingProvider) -> tuple[str, str]:
    provider_name = str(provider.name)
    model_name = str(getattr(provider, "model", provider_name))
    return provider_name, model_name


def _course_chunks(db: Session, course_id: str) -> list[DocumentChunk]:
    return list(
        db.scalars(
            select(DocumentChunk)
            .join(Document, Document.id == DocumentChunk.document_id)
            .where(Document.course_id == course_id, Document.status == "processed")
            .order_by(Document.id, DocumentChunk.chunk_index)
        ).all()
    )


def _normalize_vector(vector: object) -> list[float]:
    if not isinstance(vector, list) or not vector:
        raise TutorEmbeddingFailure("Embedding provider returned an invalid vector")
    normalized: list[float] = []
    for value in vector:
        try:
            number = float(value)
        except (TypeError, ValueError) as exc:
            raise TutorEmbeddingFailure("Embedding provider returned a non-numeric vector") from exc
        if not math.isfinite(number):
            raise TutorEmbeddingFailure("Embedding provider returned a non-finite vector")
        normalized.append(number)
    return normalized


def _embed_chunks(
    provider: TutorEmbeddingProvider,
    chunks: list[DocumentChunk],
    batch_size: int,
) -> dict[str, list[float]]:
    embedded: dict[str, list[float]] = {}
    expected_dimensions: int | None = None
    for start in range(0, len(chunks), batch_size):
        batch = chunks[start : start + batch_size]
        vectors = provider.embed([chunk.text for chunk in batch])
        if len(vectors) != len(batch):
            raise TutorEmbeddingFailure("Embedding provider returned an invalid vector batch")
        for chunk, raw_vector in zip(batch, vectors, strict=True):
            vector = _normalize_vector(raw_vector)
            if expected_dimensions is None:
                expected_dimensions = len(vector)
            elif len(vector) != expected_dimensions:
                raise TutorEmbeddingFailure("Embedding provider returned inconsistent dimensions")
            embedded[chunk.id] = vector
    return embedded


def _row_is_current(row: TutorChunkEmbedding, chunk: DocumentChunk) -> bool:
    if row.content_sha256 != _content_sha256(chunk.text):
        return False
    if row.dimensions <= 0 or not isinstance(row.vector, list):
        return False
    return len(row.vector) == row.dimensions and row.dimensions > 0


def _matching_rows(
    db: Session,
    course_id: str,
    chunk_ids: list[str],
    provider_name: str,
    model_name: str,
) -> dict[str, TutorChunkEmbedding]:
    if not chunk_ids:
        return {}
    rows = db.scalars(
        select(TutorChunkEmbedding).where(
            TutorChunkEmbedding.course_id == course_id,
            TutorChunkEmbedding.chunk_id.in_(chunk_ids),
            TutorChunkEmbedding.provider_name == provider_name,
            TutorChunkEmbedding.model_name == model_name,
        )
    ).all()
    return {row.chunk_id: row for row in rows}


def ensure_chunk_embeddings(
    db: Session,
    course_id: str,
    chunks: list[DocumentChunk],
    provider: TutorEmbeddingProvider,
    *,
    batch_size: int = 64,
) -> EmbeddingCacheResult:
    unique = {chunk.id: chunk for chunk in chunks}
    ordered = list(unique.values())
    if not ordered:
        return EmbeddingCacheResult({}, 0, 0, 0)

    provider_name, model_name = _provider_identity(provider)
    rows = _matching_rows(
        db,
        course_id,
        [chunk.id for chunk in ordered],
        provider_name,
        model_name,
    )
    current: dict[str, list[float]] = {}
    targets: list[DocumentChunk] = []
    stale_count = 0
    for chunk in ordered:
        row = rows.get(chunk.id)
        if row is not None and _row_is_current(row, chunk):
            current[chunk.id] = [float(value) for value in row.vector]
        else:
            if row is not None:
                stale_count += 1
            targets.append(chunk)

    new_vectors = _embed_chunks(provider, targets, batch_size) if targets else {}
    now = datetime.now(UTC)
    for chunk in targets:
        vector = new_vectors[chunk.id]
        row = rows.get(chunk.id)
        if row is None:
            row = TutorChunkEmbedding(
                course_id=course_id,
                chunk_id=chunk.id,
                provider_name=provider_name,
                model_name=model_name,
                content_sha256=_content_sha256(chunk.text),
                dimensions=len(vector),
                vector=vector,
                indexed_at=now,
            )
            db.add(row)
        else:
            row.content_sha256 = _content_sha256(chunk.text)
            row.dimensions = len(vector)
            row.vector = vector
            row.indexed_at = now
        current[chunk.id] = vector
    if targets:
        db.commit()

    return EmbeddingCacheResult(
        vectors=current,
        cache_hits=len(ordered) - len(targets),
        embedded_now=len(targets),
        stale_reembedded=stale_count,
    )


def embedding_index_status(
    db: Session,
    course_id: str,
    provider: TutorEmbeddingProvider | None,
) -> TutorEmbeddingIndexRead:
    chunks = _course_chunks(db, course_id)
    chunk_by_id = {chunk.id: chunk for chunk in chunks}
    all_rows = list(
        db.scalars(
            select(TutorChunkEmbedding).where(TutorChunkEmbedding.course_id == course_id)
        ).all()
    )
    orphaned = sum(1 for row in all_rows if row.chunk_id not in chunk_by_id)

    if provider is None:
        return TutorEmbeddingIndexRead(
            course_id=course_id,
            status="disabled",
            provider_name=None,
            model_name=None,
            total_chunks=len(chunks),
            indexed_chunks=0,
            missing_chunks=len(chunks),
            stale_chunks=0,
            orphaned_embeddings=orphaned,
            coverage=0.0,
            dimensions=None,
        )

    provider_name, model_name = _provider_identity(provider)
    matching = {
        row.chunk_id: row
        for row in all_rows
        if row.provider_name == provider_name and row.model_name == model_name
    }
    indexed = 0
    stale = 0
    missing = 0
    dimensions: set[int] = set()
    for chunk in chunks:
        row = matching.get(chunk.id)
        if row is None:
            missing += 1
        elif _row_is_current(row, chunk):
            indexed += 1
            dimensions.add(row.dimensions)
        else:
            stale += 1

    total = len(chunks)
    if total == 0:
        status = "empty"
    elif indexed == total and stale == 0 and missing == 0:
        status = "ready"
    else:
        status = "stale"
    return TutorEmbeddingIndexRead(
        course_id=course_id,
        status=status,
        provider_name=provider_name,
        model_name=model_name,
        total_chunks=total,
        indexed_chunks=indexed,
        missing_chunks=missing,
        stale_chunks=stale,
        orphaned_embeddings=orphaned,
        coverage=round(indexed / total, 4) if total else 1.0,
        dimensions=next(iter(dimensions)) if len(dimensions) == 1 else None,
    )


def sync_course_embedding_index(
    db: Session,
    course_id: str,
    provider: TutorEmbeddingProvider,
    *,
    batch_size: int = 64,
    force: bool = False,
) -> TutorEmbeddingIndexRead:
    chunks = _course_chunks(db, course_id)
    chunk_by_id = {chunk.id: chunk for chunk in chunks}
    provider_name, model_name = _provider_identity(provider)
    all_rows = list(
        db.scalars(
            select(TutorChunkEmbedding).where(TutorChunkEmbedding.course_id == course_id)
        ).all()
    )
    rows = {
        row.chunk_id: row
        for row in all_rows
        if row.provider_name == provider_name and row.model_name == model_name
    }
    targets: list[DocumentChunk] = []
    for chunk in chunks:
        row = rows.get(chunk.id)
        if force or row is None or not _row_is_current(row, chunk):
            targets.append(chunk)

    vectors = _embed_chunks(provider, targets, batch_size) if targets else {}
    orphan_rows = [row for row in all_rows if row.chunk_id not in chunk_by_id]
    for row in orphan_rows:
        db.delete(row)

    now = datetime.now(UTC)
    for chunk in targets:
        vector = vectors[chunk.id]
        row = rows.get(chunk.id)
        if row is None:
            db.add(
                TutorChunkEmbedding(
                    course_id=course_id,
                    chunk_id=chunk.id,
                    provider_name=provider_name,
                    model_name=model_name,
                    content_sha256=_content_sha256(chunk.text),
                    dimensions=len(vector),
                    vector=vector,
                    indexed_at=now,
                )
            )
        else:
            row.content_sha256 = _content_sha256(chunk.text)
            row.dimensions = len(vector)
            row.vector = vector
            row.indexed_at = now
    if targets or orphan_rows:
        db.commit()

    snapshot = embedding_index_status(db, course_id, provider)
    return snapshot.model_copy(
        update={
            "embedded_now": len(targets),
            "reused_chunks": len(chunks) - len(targets),
            "deleted_orphans": len(orphan_rows),
        }
    )
