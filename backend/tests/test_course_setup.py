from __future__ import annotations

from fastapi.testclient import TestClient


def test_course_setup_tracks_import_pipeline(client: TestClient) -> None:
    created = client.post(
        "/api/v1/courses",
        json={
            "name": "Physics I",
            "exam_date": "2026-09-14",
            "target_grade": 25,
            "max_grade": 30,
        },
    )
    assert created.status_code == 201
    course_id = created.json()["id"]

    empty = client.get(f"/api/v1/courses/{course_id}/setup")
    assert empty.status_code == 200
    assert empty.json()["next_step"] == "upload_documents"
    assert empty.json()["ready_for_planning"] is False

    uploaded = client.post(
        f"/api/v1/courses/{course_id}/documents",
        files={
            "file": (
                "mechanics.txt",
                b"Newton's Second Law\nForce is F = m a. Momentum is p = m v.",
                "text/plain",
            )
        },
    )
    assert uploaded.status_code == 201
    document_id = uploaded.json()["id"]

    pending = client.get(f"/api/v1/courses/{course_id}/setup")
    assert pending.json()["document_count"] == 1
    assert pending.json()["processed_document_count"] == 0
    assert pending.json()["next_step"] == "process_documents"

    processed = client.post(
        f"/api/v1/courses/{course_id}/documents/{document_id}/process"
    )
    assert processed.status_code == 200

    needs_analysis = client.get(f"/api/v1/courses/{course_id}/setup")
    assert needs_analysis.json()["processed_document_count"] == 1
    assert needs_analysis.json()["next_step"] == "analyze_course"

    analyzed = client.post(f"/api/v1/courses/{course_id}/analyze")
    assert analyzed.status_code == 200

    ready = client.get(f"/api/v1/courses/{course_id}/setup")
    assert ready.status_code == 200
    assert ready.json()["course_analyzed"] is True
    assert ready.json()["ready_for_planning"] is True
    assert ready.json()["next_step"] == "ready"


def test_course_setup_missing_course_returns_404(client: TestClient) -> None:
    response = client.get("/api/v1/courses/not-a-real-course/setup")
    assert response.status_code == 404
