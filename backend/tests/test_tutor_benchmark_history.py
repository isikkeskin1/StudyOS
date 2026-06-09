from __future__ import annotations

from fastapi.testclient import TestClient

from app.models.tutor_benchmark_history import TutorRetrievalBenchmarkRun


def _course(client: TestClient) -> str:
    response = client.post("/api/v1/courses", json={"name": "Physics Benchmark"})
    assert response.status_code == 201
    return response.json()["id"]


def _upload(client: TestClient, course_id: str, name: str, text: str) -> str:
    uploaded = client.post(
        f"/api/v1/courses/{course_id}/documents",
        files={"file": (name, text.encode(), "text/plain")},
    )
    assert uploaded.status_code == 201
    document_id = uploaded.json()["id"]
    processed = client.post(f"/api/v1/courses/{course_id}/documents/{document_id}/process")
    assert processed.status_code == 200
    return document_id


def _fixture(client: TestClient) -> tuple[str, str, str]:
    course_id = _course(client)
    document_id = _upload(
        client,
        course_id,
        "mechanics.txt",
        "The change in velocity is aligned with the resultant interaction on the body.",
    )
    _upload(
        client,
        course_id,
        "keyword-distractor.txt",
        "Acceleration direction force direction acceleration force direction force acceleration.",
    )
    search = client.post(
        f"/api/v1/courses/{course_id}/tutor/search",
        json={"query": "aligned resultant interaction change velocity", "limit": 4},
    )
    assert search.status_code == 200
    chunk_id = search.json()["citations"][0]["chunk_id"]
    return course_id, document_id, chunk_id


def _create_suite(client: TestClient, course_id: str, chunk_id: str) -> dict:
    response = client.post(
        f"/api/v1/courses/{course_id}/tutor/retrieval-benchmark-suites",
        json={
            "name": "Physics retrieval regression suite",
            "description": "Stable mechanics retrieval checks",
            "cases": [
                {
                    "case_id": "net-force-direction",
                    "label": "direction relationship",
                    "query": "What determines acceleration direction?",
                    "relevant_chunk_ids": [chunk_id],
                }
            ],
            "default_modes": ["bm25", "topic"],
            "default_k": 1,
            "default_max_results": 3,
        },
    )
    assert response.status_code == 201
    return response.json()


def test_persisted_suite_lists_summary_and_gets_immutable_cases(client: TestClient) -> None:
    course_id, _, chunk_id = _fixture(client)
    suite = _create_suite(client, course_id, chunk_id)

    listed = client.get(f"/api/v1/courses/{course_id}/tutor/retrieval-benchmark-suites")
    assert listed.status_code == 200
    assert listed.json()[0]["id"] == suite["id"]
    assert listed.json()[0]["cases"] is None
    assert listed.json()[0]["case_count"] == 1

    fetched = client.get(
        f"/api/v1/courses/{course_id}/tutor/retrieval-benchmark-suites/{suite['id']}"
    )
    assert fetched.status_code == 200
    assert fetched.json()["cases"][0]["relevant_chunk_ids"] == [chunk_id]


def test_suite_run_history_uses_previous_same_k_as_baseline(client: TestClient) -> None:
    course_id, _, chunk_id = _fixture(client)
    suite = _create_suite(client, course_id, chunk_id)
    base = f"/api/v1/courses/{course_id}/tutor/retrieval-benchmark-suites/{suite['id']}"

    first = client.post(f"{base}/runs", json={"revision_label": "baseline"})
    assert first.status_code == 201
    assert first.json()["comparison"]["verdict"] == "no_baseline"
    assert first.json()["result"] is not None

    second = client.post(f"{base}/runs", json={"revision_label": "candidate"})
    assert second.status_code == 201
    assert second.json()["comparison"]["baseline_run_id"] == first.json()["id"]
    assert second.json()["comparison"]["verdict"] == "pass"

    history = client.get(f"{base}/runs")
    assert history.status_code == 200
    assert history.json()["run_count"] == 2
    assert all(run["result"] is None for run in history.json()["runs"])

    fetched = client.get(f"{base}/runs/{second.json()['id']}")
    assert fetched.status_code == 200
    assert fetched.json()["result"]["benchmark_model"] == "retrieval-hard-negative-v1"


def test_suite_run_flags_material_metric_regression(client: TestClient) -> None:
    course_id, _, chunk_id = _fixture(client)
    suite = _create_suite(client, course_id, chunk_id)
    base = f"/api/v1/courses/{course_id}/tutor/retrieval-benchmark-suites/{suite['id']}"
    first = client.post(f"{base}/runs", json={})
    assert first.status_code == 201

    with client.app.state.session_factory() as db:
        row = db.get(TutorRetrievalBenchmarkRun, first.json()["id"])
        assert row is not None
        result = dict(row.result)
        modes = [dict(mode) for mode in result["modes"]]
        for mode in modes:
            if mode["status"] == "evaluated":
                mode["top1_accuracy"] = 1.0
                mode["hit_rate_at_k"] = 1.0
                mode["recall_at_k"] = 1.0
                mode["mean_reciprocal_rank"] = 1.0
        result["modes"] = modes
        row.result = result
        db.commit()

    second = client.post(
        f"{base}/runs",
        json={"regression_tolerance": 0.01, "revision_label": "regressed-candidate"},
    )
    assert second.status_code == 201
    comparison = second.json()["comparison"]
    assert comparison["verdict"] == "regression"
    assert comparison["regressed_modes"]
    assert any(delta["regressed_metrics"] for delta in comparison["mode_deltas"])


def test_suite_fails_closed_when_reprocessing_invalidates_chunk_labels(client: TestClient) -> None:
    course_id, document_id, chunk_id = _fixture(client)
    suite = _create_suite(client, course_id, chunk_id)
    base = f"/api/v1/courses/{course_id}/tutor/retrieval-benchmark-suites/{suite['id']}"

    reprocessed = client.post(
        f"/api/v1/courses/{course_id}/documents/{document_id}/process"
    )
    assert reprocessed.status_code == 200

    run = client.post(f"{base}/runs", json={})
    assert run.status_code == 409
    assert "not processed members" in run.json()["detail"]
