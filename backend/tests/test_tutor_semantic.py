from __future__ import annotations

from types import SimpleNamespace

from fastapi.testclient import TestClient

from app.schemas.tutor import TutorSearchRequest
from app.services.tutor import search_course_material
from app.services.tutor_embeddings import OpenAIEmbeddingProvider, TutorEmbeddingConfig


class _FakeEmbeddingProvider:
    name = "fake-semantic-v1"

    def embed(self, texts: list[str]) -> list[list[float]]:
        vectors: list[list[float]] = []
        for text in texts:
            lowered = text.lower()
            if "derivative" in lowered or "rate of change" in lowered:
                vectors.append([1.0, 0.0])
            else:
                vectors.append([0.0, 1.0])
        return vectors


class _FakeEmbeddingsEndpoint:
    def __init__(self) -> None:
        self.calls: list[dict] = []

    def create(self, **kwargs):
        self.calls.append(kwargs)
        return SimpleNamespace(
            data=[
                SimpleNamespace(embedding=[1.0, 0.0]),
                SimpleNamespace(embedding=[0.5, 0.5]),
            ]
        )


class _FakeOpenAIClient:
    def __init__(self) -> None:
        self.embeddings = _FakeEmbeddingsEndpoint()


def _create_course(client: TestClient) -> str:
    response = client.post("/api/v1/courses", json={"name": "Calculus"})
    assert response.status_code == 201
    return response.json()["id"]


def _upload(client: TestClient, course_id: str, filename: str, text: str) -> None:
    upload = client.post(
        f"/api/v1/courses/{course_id}/documents",
        files={"file": (filename, text.encode(), "text/plain")},
    )
    assert upload.status_code == 201
    document_id = upload.json()["id"]
    assert (
        client.post(f"/api/v1/courses/{course_id}/documents/{document_id}/process").status_code
        == 200
    )


def test_semantic_retrieval_can_rank_paraphrase_without_token_overlap(
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

    with client.app.state.session_factory() as db:
        result = search_course_material(
            db,
            course_id,
            TutorSearchRequest(query="derivative", retrieval_mode="semantic"),
            embedding_config=TutorEmbeddingConfig(max_candidates=16),
            embedding_provider=_FakeEmbeddingProvider(),
        )

    assert result.retrieval_model == "semantic-vector-rerank-v1"
    assert result.semantic_signal_applied is True
    assert result.embedding_provider == "fake-semantic-v1"
    assert result.citations[0].document_name == "calculus.txt"
    assert result.citations[0].semantic_score == 1.0
    assert result.citations[0].lexical_score == 0.0


def test_explicit_semantic_api_requires_configured_embedding_provider(
    client: TestClient,
) -> None:
    course_id = _create_course(client)
    _upload(client, course_id, "notes.txt", "A derivative is an instantaneous rate of change.")

    response = client.post(
        f"/api/v1/courses/{course_id}/tutor/search",
        json={"query": "derivative", "retrieval_mode": "semantic"},
    )

    assert response.status_code == 503
    assert "embedding provider" in response.json()["detail"].lower()


def test_openai_embedding_adapter_batches_inputs() -> None:
    client = _FakeOpenAIClient()
    provider = OpenAIEmbeddingProvider(
        api_key="test-key",
        model="text-embedding-3-small",
        client=client,
    )

    vectors = provider.embed(["first", "second"])

    assert vectors == [[1.0, 0.0], [0.5, 0.5]]
    assert client.embeddings.calls[0]["model"] == "text-embedding-3-small"
    assert client.embeddings.calls[0]["input"] == ["first", "second"]
