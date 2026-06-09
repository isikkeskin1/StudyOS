from __future__ import annotations

from fastapi.testclient import TestClient

from app.schemas.tutor_benchmark import TutorRetrievalBenchmarkRequest
from app.services.tutor_benchmark import run_retrieval_benchmark
from app.services.tutor_embeddings import TutorEmbeddingConfig


class FakeBenchmarkEmbeddingProvider:
    name = "fake-benchmark-embeddings"

    def embed(self, texts: list[str]) -> list[list[float]]:
        vectors: list[list[float]] = []
        for text in texts:
            lowered = text.lower()
            if "which way does acceleration" in lowered:
                vectors.append([1.0, 0.0])
            elif "aligned with the resultant interaction" in lowered:
                vectors.append([1.0, 0.0])
            elif "acceleration direction force direction" in lowered:
                vectors.append([0.0, 1.0])
            else:
                vectors.append([0.2, 0.8])
        return vectors


def _course(client: TestClient) -> str:
    response = client.post("/api/v1/courses", json={"name": "Physics I"})
    assert response.status_code == 201
    return response.json()["id"]


def _upload(client: TestClient, course_id: str, name: str, text: str) -> None:
    uploaded = client.post(
        f"/api/v1/courses/{course_id}/documents",
        files={"file": (name, text.encode(), "text/plain")},
    )
    assert uploaded.status_code == 201
    processed = client.post(
        f"/api/v1/courses/{course_id}/documents/{uploaded.json()['id']}/process"
    )
    assert processed.status_code == 200


def _chunk_id(client: TestClient, course_id: str, query: str) -> str:
    response = client.post(
        f"/api/v1/courses/{course_id}/tutor/search",
        json={"query": query, "limit": 6},
    )
    assert response.status_code == 200
    return response.json()["citations"][0]["chunk_id"]


def _fixture(client: TestClient) -> tuple[str, str]:
    course_id = _course(client)
    _upload(
        client,
        course_id,
        "keyword-distractor.txt",
        "Acceleration direction force direction acceleration force direction force acceleration.",
    )
    _upload(
        client,
        course_id,
        "paraphrase-answer.txt",
        "The change in velocity is aligned with the resultant interaction on the body.",
    )
    _upload(
        client,
        course_id,
        "formula-note.txt",
        "Newton's second law relates net force, mass, and acceleration through F equals m a.",
    )
    relevant_id = _chunk_id(
        client,
        course_id,
        "aligned resultant interaction change velocity",
    )
    return course_id, relevant_id


def test_benchmark_compares_same_cases_and_exposes_hard_negative_failure(
    client: TestClient,
) -> None:
    course_id, relevant_id = _fixture(client)
    payload = TutorRetrievalBenchmarkRequest.model_validate(
        {
            "cases": [
                {
                    "case_id": "direction-paraphrase",
                    "label": "paraphrased direction relation",
                    "query": "Which way does acceleration point relative to net force?",
                    "relevant_chunk_ids": [relevant_id],
                }
            ],
            "modes": ["bm25", "semantic", "hybrid"],
            "k": 2,
            "max_results": 3,
        }
    )

    with client.app.state.session_factory() as db:
        result = run_retrieval_benchmark(
            db,
            course_id,
            payload,
            embedding_config=TutorEmbeddingConfig(max_candidates=16, batch_size=8),
            embedding_provider=FakeBenchmarkEmbeddingProvider(),
        )

    by_mode = {mode.mode: mode for mode in result.modes}
    assert result.benchmark_model == "retrieval-hard-negative-v1"
    assert result.case_count == 1
    assert all(mode.evaluated_cases == 1 for mode in result.modes)
    assert by_mode["semantic"].top1_accuracy == 1.0
    assert by_mode["semantic"].mean_reciprocal_rank == 1.0
    assert by_mode["bm25"].mean_reciprocal_rank < by_mode["semantic"].mean_reciprocal_rank
    assert by_mode["bm25"].failures
    assert by_mode["bm25"].failures[0].case_id == "direction-paraphrase"
    assert by_mode["semantic"].cases[0].retrieved[0].relevant is True


def test_benchmark_api_keeps_lexical_baselines_when_embeddings_disabled(
    client: TestClient,
) -> None:
    course_id, relevant_id = _fixture(client)
    response = client.post(
        f"/api/v1/courses/{course_id}/tutor/retrieval-benchmark",
        json={
            "cases": [
                {
                    "case_id": "offline",
                    "label": "offline benchmark",
                    "query": "Which way does acceleration point relative to net force?",
                    "relevant_chunk_ids": [relevant_id],
                }
            ],
            "modes": ["bm25", "topic", "semantic", "hybrid"],
            "k": 2,
        },
    )

    assert response.status_code == 200
    body = response.json()
    by_mode = {item["mode"]: item for item in body["modes"]}
    assert by_mode["bm25"]["status"] == "evaluated"
    assert by_mode["topic"]["status"] == "evaluated"
    assert by_mode["semantic"]["status"] == "unavailable"
    assert by_mode["hybrid"]["status"] == "unavailable"
    assert by_mode["semantic"]["evaluated_cases"] == 0
    assert body["best_mode"] in {"bm25", "topic"}


def test_benchmark_rejects_cross_course_or_unknown_chunk_labels(client: TestClient) -> None:
    course_id, _ = _fixture(client)
    response = client.post(
        f"/api/v1/courses/{course_id}/tutor/retrieval-benchmark",
        json={
            "cases": [
                {
                    "case_id": "bad-label",
                    "label": "invalid chunk",
                    "query": "net force direction",
                    "relevant_chunk_ids": ["not-a-course-chunk"],
                }
            ],
            "modes": ["bm25"],
        },
    )

    assert response.status_code == 400
    assert "not processed members" in response.json()["detail"]


def test_benchmark_request_rejects_duplicate_case_ids(client: TestClient) -> None:
    course_id, relevant_id = _fixture(client)
    case = {
        "case_id": "duplicate",
        "label": "duplicate case",
        "query": "net force direction",
        "relevant_chunk_ids": [relevant_id],
    }
    response = client.post(
        f"/api/v1/courses/{course_id}/tutor/retrieval-benchmark",
        json={"cases": [case, case], "modes": ["bm25"]},
    )

    assert response.status_code == 422
