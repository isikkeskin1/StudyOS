from __future__ import annotations

from fastapi.testclient import TestClient
from sqlalchemy import select

from app.models.document_content import DocumentChunk
from app.schemas.tutor import TutorSearchRequest
from app.services.tutor import search_course_material
from app.services.tutor_embedding_index import (
    embedding_index_status,
    sync_course_embedding_index,
)
from app.services.tutor_embeddings import TutorEmbeddingConfig


class _CountingEmbeddingProvider:
    name = "fake-index-provider-v1"
    model = "fake-index-model-v1"

    def __init__(self) -> None:
        self.calls: list[list[str]] = []

    def embed(self, texts: list[str]) -> list[list[float]]:
        self.calls.append(list(texts))
        vectors: list[list[float]] = []
        for text in texts:
            lowered = text.lower()
            if "derivative" in lowered or "rate of change" in lowered:
                vectors.append([1.0, 0.0])
            else:
                vectors.append([0.0, 1.0])
        return vectors


def _create_course(client: TestClient, name: str = "Calculus") -> str:
    response = client.post("/api/v1/courses", json={"name": name})
    assert response.status_code == 201
    return response.json()["id"]


def _upload(
    client: TestClient,
    course_id: str,
    filename: str,
    text: str,
) -> str:
    upload = client.post(
        f"/api/v1/courses/{course_id}/documents",
        files={"file": (filename, text.encode(), "text/plain")},
    )
    assert upload.status_code == 201
    document_id = upload.json()["id"]
    processed = client.post(
        f"/api/v1/courses/{course_id}/documents/{document_id}/process"
    )
    assert processed.status_code == 200
    return document_id


def test_embedding_index_sync_reuses_unchanged_chunks(client: TestClient) -> None:
    course_id = _create_course(client)
    _upload(
        client,
        course_id,
        "calculus.txt",
        "The instantaneous rate of change describes a derivative at one point.",
    )
    _upload(
        client,
        course_id,
        "thermal.txt",
        "Temperature measures thermal state and heat transfer between systems.",
    )
    provider = _CountingEmbeddingProvider()

    with client.app.state.session_factory() as db:
        first = sync_course_embedding_index(db, course_id, provider, batch_size=16)
        assert first.status == "ready"
        assert first.embedded_now == first.total_chunks
        assert first.indexed_chunks == first.total_chunks
        assert first.coverage == 1.0

        provider.calls.clear()
        second = sync_course_embedding_index(db, course_id, provider, batch_size=16)
        assert second.embedded_now == 0
        assert second.reused_chunks == second.total_chunks
        assert provider.calls == []


def test_semantic_retrieval_lazily_persists_and_reuses_chunk_vectors(
    client: TestClient,
) -> None:
    course_id = _create_course(client)
    _upload(
        client,
        course_id,
        "calculus.txt",
        "The instantaneous rate of change describes how a function changes at one point.",
    )
    _upload(
        client,
        course_id,
        "thermal.txt",
        "Temperature measures thermal state and heat transfer between systems.",
    )
    provider = _CountingEmbeddingProvider()
    config = TutorEmbeddingConfig(max_candidates=16, batch_size=16)

    with client.app.state.session_factory() as db:
        first = search_course_material(
            db,
            course_id,
            TutorSearchRequest(query="derivative", retrieval_mode="semantic"),
            embedding_config=config,
            embedding_provider=provider,
        )
        assert first.citations[0].document_name == "calculus.txt"
        assert "persistent_embedding_cache" in first.retrieval_components
        assert len(provider.calls) == 2

        provider.calls.clear()
        second = search_course_material(
            db,
            course_id,
            TutorSearchRequest(query="derivative", retrieval_mode="semantic"),
            embedding_config=config,
            embedding_provider=provider,
        )
        assert second.citations[0].document_name == "calculus.txt"
        assert provider.calls == [["derivative"]]


def test_changed_chunk_is_stale_and_only_that_chunk_is_reembedded(
    client: TestClient,
) -> None:
    course_id = _create_course(client)
    _upload(client, course_id, "notes.txt", "A derivative is an instantaneous rate of change.")
    provider = _CountingEmbeddingProvider()

    with client.app.state.session_factory() as db:
        initial = sync_course_embedding_index(db, course_id, provider)
        assert initial.status == "ready"
        chunk = db.scalar(select(DocumentChunk).limit(1))
        assert chunk is not None
        chunk.text = chunk.text + " Updated explanation."
        chunk.character_count = len(chunk.text)
        db.commit()

        stale = embedding_index_status(db, course_id, provider)
        assert stale.status == "stale"
        assert stale.stale_chunks == 1

        provider.calls.clear()
        refreshed = sync_course_embedding_index(db, course_id, provider)
        assert refreshed.status == "ready"
        assert refreshed.embedded_now == 1
        assert sum(len(call) for call in provider.calls) == 1


def test_reprocessing_document_cleans_orphaned_embeddings(client: TestClient) -> None:
    course_id = _create_course(client)
    document_id = _upload(
        client,
        course_id,
        "notes.txt",
        "A derivative is an instantaneous rate of change.",
    )
    provider = _CountingEmbeddingProvider()

    with client.app.state.session_factory() as db:
        initial = sync_course_embedding_index(db, course_id, provider)
        old_count = initial.total_chunks
        assert old_count > 0

    reprocess = client.post(
        f"/api/v1/courses/{course_id}/documents/{document_id}/process"
    )
    assert reprocess.status_code == 200

    with client.app.state.session_factory() as db:
        before = embedding_index_status(db, course_id, provider)
        # Reprocessing replaces document chunks. Enforced foreign keys cascade-delete
        # embeddings for the replaced chunks immediately, leaving only fresh misses.
        assert before.orphaned_embeddings == 0
        assert before.missing_chunks == before.total_chunks

        refreshed = sync_course_embedding_index(db, course_id, provider)
        assert refreshed.status == "ready"
        assert refreshed.deleted_orphans == 0
        assert refreshed.orphaned_embeddings == 0


def test_embedding_index_api_reports_disabled_and_sync_requires_provider(
    client: TestClient,
) -> None:
    course_id = _create_course(client)
    _upload(client, course_id, "notes.txt", "A derivative is a rate of change.")

    status_response = client.get(
        f"/api/v1/courses/{course_id}/tutor/embedding-index"
    )
    assert status_response.status_code == 200
    payload = status_response.json()
    assert payload["status"] == "disabled"
    assert payload["total_chunks"] > 0
    assert payload["coverage"] == 0.0

    sync_response = client.post(
        f"/api/v1/courses/{course_id}/tutor/embedding-index/sync",
        json={},
    )
    assert sync_response.status_code == 503
    assert "embedding provider" in sync_response.json()["detail"].lower()
