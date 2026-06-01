from __future__ import annotations

from fastapi.testclient import TestClient


def _prepare_course(client: TestClient) -> str:
    course = client.post(
        "/api/v1/courses",
        json={"name": "Physics I", "target_grade": 25, "max_grade": 30},
    )
    assert course.status_code == 201
    course_id = course.json()["id"]

    lecture = client.post(
        f"/api/v1/courses/{course_id}/documents",
        files={
            "file": (
                "momentum-lecture.txt",
                (
                    b"Momentum\n"
                    b"Momentum is conserved in isolated collisions. "
                    b"Impulse changes momentum. Momentum is a vector quantity. "
                    b"Conservation of momentum applies to collision problems."
                ),
                "text/plain",
            )
        },
    )
    assert lecture.status_code == 201
    assert client.post(
        f"/api/v1/courses/{course_id}/documents/{lecture.json()['id']}/process"
    ).status_code == 200

    exam = client.post(
        f"/api/v1/courses/{course_id}/documents",
        files={
            "file": (
                "2025-momentum-exam.txt",
                (
                    b"Physics I Written Exam\n"
                    b"Question 1 (10 marks)\n"
                    b"Use conservation of momentum to solve the collision.\n\n"
                    b"Question 2 (10 marks)\n"
                    b"Calculate momentum after impact using conservation of momentum."
                ),
                "text/plain",
            )
        },
    )
    assert exam.status_code == 201
    assert client.post(
        f"/api/v1/courses/{course_id}/documents/{exam.json()['id']}/process"
    ).status_code == 200
    assert client.post(f"/api/v1/courses/{course_id}/analyze").status_code == 200
    assert (
        client.post(f"/api/v1/courses/{course_id}/exam-intelligence/analyze").status_code
        == 200
    )
    return course_id


def _answer_next(
    client: TestClient,
    course_id: str,
    session_id: str,
    score: float,
) -> None:
    next_question = client.get(
        f"/api/v1/courses/{course_id}/diagnostics/{session_id}/next"
    )
    assert next_question.status_code == 200
    question = next_question.json()["question"]
    assert question is not None
    response = client.post(
        f"/api/v1/courses/{course_id}/diagnostics/{session_id}/responses",
        json={
            "diagnostic_question_id": question["id"],
            "score": score,
            "confidence": 1.0,
        },
    )
    assert response.status_code == 200


def test_mastery_history_is_empty_before_diagnostic_evidence(client: TestClient) -> None:
    course_id = _prepare_course(client)

    response = client.get(f"/api/v1/courses/{course_id}/mastery/history")

    assert response.status_code == 200
    payload = response.json()
    assert payload["tracked_topic_count"] == 0
    assert payload["total_history_points"] == 0
    assert payload["topics"] == []


def test_mastery_history_tracks_response_level_learning_curve(client: TestClient) -> None:
    course_id = _prepare_course(client)
    session = client.post(
        f"/api/v1/courses/{course_id}/diagnostics",
        json={"question_count": 2},
    )
    assert session.status_code == 201
    session_id = session.json()["id"]

    _answer_next(client, course_id, session_id, 0.2)
    _answer_next(client, course_id, session_id, 1.0)

    response = client.get(f"/api/v1/courses/{course_id}/mastery/history")
    assert response.status_code == 200
    payload = response.json()
    assert payload["tracked_topic_count"] > 0
    assert payload["total_history_points"] >= 2

    repeated = [topic for topic in payload["topics"] if topic["point_count"] >= 2]
    assert repeated
    improving = max(repeated, key=lambda item: item["change_from_first"])
    assert improving["change_from_first"] > 0
    assert improving["trend_direction"] == "improving"
    assert improving["recent_response_count"] == 2
    assert 0 <= improving["recent_accuracy"] <= 1
    assert improving["observed_gain_per_evidence"] is not None
    assert improving["points"][-1]["response_count"] == 2

    mastery = {
        item["topic_id"]: item
        for item in client.get(f"/api/v1/courses/{course_id}/mastery").json()
    }
    assert improving["topic_id"] in mastery
    assert improving["raw_mastery"] == mastery[improving["topic_id"]]["mastery"]


def test_mastery_history_missing_course_returns_404(client: TestClient) -> None:
    response = client.get("/api/v1/courses/not-a-course/mastery/history")
    assert response.status_code == 404
