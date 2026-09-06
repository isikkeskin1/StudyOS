from __future__ import annotations

from fastapi.testclient import TestClient


def _prepare(client: TestClient) -> tuple[str, str]:
    course = client.post(
        "/api/v1/courses",
        json={"name": "Physics I", "target_grade": 25, "max_grade": 30},
    )
    assert course.status_code == 201
    course_id = course.json()["id"]

    for filename, content in [
        (
            "lecture.txt",
            b"Newton's Second Law\nForce is F = m a. Momentum is p = m v. Momentum is conserved.",
        ),
        (
            "exam.txt",
            b"Physics I Written Exam\nQuestion 1 (8 marks)\nCalculate force using Newton's second law.\n\nQuestion 2 (12 marks)\nUse conservation of momentum.",
        ),
    ]:
        upload = client.post(
            f"/api/v1/courses/{course_id}/documents",
            files={"file": (filename, content, "text/plain")},
        )
        assert upload.status_code == 201
        process = client.post(
            f"/api/v1/courses/{course_id}/documents/{upload.json()['id']}/process"
        )
        assert process.status_code == 200

    assert client.post(f"/api/v1/courses/{course_id}/analyze").status_code == 200
    assert (
        client.post(f"/api/v1/courses/{course_id}/exam-intelligence/analyze").status_code
        == 200
    )
    started = client.post(
        f"/api/v1/courses/{course_id}/diagnostics",
        json={"question_count": 2},
    )
    assert started.status_code == 201
    return course_id, started.json()["id"]


def test_diagnostic_summary_aggregates_scores_topics_and_mistakes(
    client: TestClient,
) -> None:
    course_id, session_id = _prepare(client)

    first = client.get(
        f"/api/v1/courses/{course_id}/diagnostics/{session_id}/next"
    ).json()["question"]
    response = client.post(
        f"/api/v1/courses/{course_id}/diagnostics/{session_id}/responses",
        json={
            "diagnostic_question_id": first["id"],
            "score": 0.5,
            "confidence": 0.8,
            "grading_source": "self",
            "duration_seconds": 90,
            "student_answer": "Partial answer",
            "mistakes": [
                {
                    "category": "incomplete_reasoning",
                    "severity": 0.6,
                    "source": "self",
                }
            ],
        },
    )
    assert response.status_code == 200

    second = client.get(
        f"/api/v1/courses/{course_id}/diagnostics/{session_id}/next"
    ).json()["question"]
    response = client.post(
        f"/api/v1/courses/{course_id}/diagnostics/{session_id}/responses",
        json={
            "diagnostic_question_id": second["id"],
            "score": 1.0,
            "confidence": 0.9,
            "grading_source": "manual",
            "duration_seconds": 120,
        },
    )
    assert response.status_code == 200

    summary = client.get(
        f"/api/v1/courses/{course_id}/diagnostics/{session_id}/summary"
    )
    assert summary.status_code == 200
    body = summary.json()
    assert body["status"] == "completed"
    assert body["answered_question_count"] == 2
    assert body["average_score"] == 0.75
    assert body["average_confidence"] == 0.85
    assert body["total_duration_seconds"] == 210
    assert body["automatic_grade_count"] == 0
    assert body["self_grade_count"] == 2
    assert body["topic_summaries"]
    assert body["mistakes"][0]["category"] == "incomplete_reasoning"
    assert body["mistakes"][0]["occurrences"] == 1


def test_empty_diagnostic_summary_is_valid(client: TestClient) -> None:
    course_id, session_id = _prepare(client)

    summary = client.get(
        f"/api/v1/courses/{course_id}/diagnostics/{session_id}/summary"
    )

    assert summary.status_code == 200
    body = summary.json()
    assert body["answered_question_count"] == 0
    assert body["average_score"] is None
    assert body["topic_summaries"] == []
    assert body["mistakes"] == []
