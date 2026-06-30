from __future__ import annotations

from fastapi.testclient import TestClient


def _course(client: TestClient, name: str) -> str:
    response = client.post("/api/v1/courses", json={"name": name})
    assert response.status_code == 201
    return response.json()["id"]


def _upload_process(
    client: TestClient,
    course_id: str,
    filename: str,
    content: bytes,
) -> tuple[str, dict]:
    upload = client.post(
        f"/api/v1/courses/{course_id}/documents",
        files={"file": (filename, content, "text/plain")},
    )
    assert upload.status_code == 201
    document_id = upload.json()["id"]
    processed = client.post(
        f"/api/v1/courses/{course_id}/documents/{document_id}/process"
    )
    assert processed.status_code == 200
    return document_id, processed.json()


def test_processing_records_quality_and_cross_course_text_duplicate(
    client: TestClient,
) -> None:
    first_course = _course(client, "Physics I")
    second_course = _course(client, "Mechanics Review")
    content = (
        b"Conservation of momentum states that total momentum remains constant "
        b"in an isolated system. Impulse equals change in momentum."
    )

    first_id, first = _upload_process(
        client,
        first_course,
        "lecture-notes.txt",
        content,
    )
    second_id, second = _upload_process(
        client,
        second_course,
        "copied-notes.txt",
        content,
    )

    assert first["text_sha256"]
    assert first["text_sha256"] == second["text_sha256"]
    assert first["duplicate_of_document_id"] is None
    assert second["duplicate_of_document_id"] == first_id
    assert second_id != first_id
    assert first["empty_unit_count"] == 0
    assert 0 < first["extraction_quality"] <= 1
    assert first["needs_ocr"] is False


def test_global_search_finds_sources_and_is_tenant_scoped(
    client: TestClient,
) -> None:
    course_id = _course(client, "Physics I")
    _upload_process(
        client,
        course_id,
        "momentum-notes.txt",
        (
            b"Linear momentum is mass times velocity. "
            b"Conservation of momentum applies when external impulse is zero."
        ),
    )

    response = client.get("/api/v1/search", params={"q": "momentum", "kind": "source"})
    assert response.status_code == 200
    body = response.json()
    assert body["result_count"] >= 1
    assert all(item["kind"] == "source" for item in body["results"])
    assert all(item["course_id"] == course_id for item in body["results"])
    assert any("momentum" in (item["excerpt"] or "").lower() for item in body["results"])

    registered = client.post(
        "/api/v1/auth/register",
        json={"email": "other@studyos.local", "password": "other-password-123"},
    )
    assert registered.status_code == 201

    isolated = client.get("/api/v1/search", params={"q": "momentum"})
    assert isolated.status_code == 200
    assert isolated.json()["results"] == []


def test_global_search_can_filter_course_results(client: TestClient) -> None:
    first = _course(client, "Quantum Physics")
    _course(client, "Classical Physics")

    response = client.get(
        "/api/v1/search",
        params={"q": "physics", "kind": "course", "course_id": first},
    )

    assert response.status_code == 200
    results = response.json()["results"]
    assert len(results) == 1
    assert results[0]["kind"] == "course"
    assert results[0]["course_id"] == first
