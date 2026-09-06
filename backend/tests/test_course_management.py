from __future__ import annotations

from fastapi.testclient import TestClient


def _create_course(client: TestClient) -> str:
    response = client.post(
        "/api/v1/courses",
        json={
            "name": "Physics I",
            "exam_date": "2026-09-14",
            "target_grade": 25,
            "max_grade": 30,
        },
    )
    assert response.status_code == 201
    return response.json()["id"]


def test_course_metadata_can_be_updated(client: TestClient) -> None:
    course_id = _create_course(client)

    response = client.patch(
        f"/api/v1/courses/{course_id}",
        json={
            "name": "Physics I — Retake",
            "exam_date": "2026-10-01",
            "target_grade": 27,
        },
    )

    assert response.status_code == 200
    updated = response.json()
    assert updated["name"] == "Physics I — Retake"
    assert updated["exam_date"] == "2026-10-01"
    assert updated["target_grade"] == 27
    assert updated["max_grade"] == 30


def test_course_update_rejects_target_above_existing_scale(client: TestClient) -> None:
    course_id = _create_course(client)

    response = client.patch(
        f"/api/v1/courses/{course_id}",
        json={"target_grade": 31},
    )

    assert response.status_code == 422


def test_deleting_source_marks_analysis_stale(client: TestClient) -> None:
    course_id = _create_course(client)
    document_ids: list[str] = []

    for filename, content in [
        ("mechanics.txt", b"Newton's Second Law\nForce is F = m a. Momentum is p = m v."),
        ("exam.txt", b"Written Exam\nQuestion 1 Calculate force. Question 2 Calculate momentum."),
    ]:
        uploaded = client.post(
            f"/api/v1/courses/{course_id}/documents",
            files={"file": (filename, content, "text/plain")},
        )
        assert uploaded.status_code == 201
        document_id = uploaded.json()["id"]
        document_ids.append(document_id)
        processed = client.post(
            f"/api/v1/courses/{course_id}/documents/{document_id}/process"
        )
        assert processed.status_code == 200

    analyzed = client.post(f"/api/v1/courses/{course_id}/analyze")
    assert analyzed.status_code == 200

    before = client.get(f"/api/v1/courses/{course_id}/setup").json()
    assert before["ready_for_planning"] is True
    assert before["analysis_stale"] is False

    deleted = client.delete(
        f"/api/v1/courses/{course_id}/documents/{document_ids[0]}"
    )
    assert deleted.status_code == 204

    after = client.get(f"/api/v1/courses/{course_id}/setup").json()
    assert after["document_count"] == 1
    assert after["processed_document_count"] == 1
    assert after["course_analyzed"] is True
    assert after["analysis_stale"] is True
    assert after["ready_for_planning"] is False
    assert after["next_step"] == "analyze_course"

    reanalyzed = client.post(f"/api/v1/courses/{course_id}/analyze")
    assert reanalyzed.status_code == 200
    ready = client.get(f"/api/v1/courses/{course_id}/setup").json()
    assert ready["analysis_stale"] is False
    assert ready["ready_for_planning"] is True
