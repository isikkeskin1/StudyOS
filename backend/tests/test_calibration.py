from __future__ import annotations

from collections import defaultdict
from datetime import UTC, datetime, timedelta

from fastapi.testclient import TestClient
from sqlalchemy import select

from app.models.mastery_history import MasterySnapshot


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

    exam_text = b"Physics I Written Exam\n"
    for number in range(1, 5):
        exam_text += (
            f"Question {number} (5 marks)\n"
            "Use conservation of momentum to solve the collision and calculate momentum.\n\n"
        ).encode()
    exam = client.post(
        f"/api/v1/courses/{course_id}/documents",
        files={"file": ("2025-momentum-exam.txt", exam_text, "text/plain")},
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


def _answer_sequence(client: TestClient, course_id: str, scores: list[float]) -> None:
    session = client.post(
        f"/api/v1/courses/{course_id}/diagnostics",
        json={"question_count": len(scores)},
    )
    assert session.status_code == 201
    session_id = session.json()["id"]

    for score in scores:
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


def test_calibration_defaults_to_generic_without_history(client: TestClient) -> None:
    course_id = _prepare_course(client)

    response = client.get(f"/api/v1/courses/{course_id}/calibration")

    assert response.status_code == 200
    payload = response.json()
    assert payload["topic_count"] > 0
    assert payload["history_point_count"] == 0
    assert payload["calibrated_learning_topic_count"] == 0
    assert all(item["learning_scale_hours"] == 2.8 for item in payload["topics"])
    assert all(item["calibration_source"] == "heuristic" for item in payload["topics"])


def test_learning_calibration_uses_improving_mastery_history(client: TestClient) -> None:
    course_id = _prepare_course(client)
    _answer_sequence(client, course_id, [0.2, 0.5, 0.8, 1.0])

    response = client.get(f"/api/v1/courses/{course_id}/calibration")

    assert response.status_code == 200
    payload = response.json()
    repeated = [item for item in payload["topics"] if item["history_point_count"] >= 2]
    assert repeated
    fastest = max(repeated, key=lambda item: item["learning_rate_multiplier"])
    assert fastest["learning_rate_multiplier"] > 1.0
    assert fastest["learning_scale_hours"] < 2.8
    assert payload["calibrated_learning_topic_count"] > 0

    plan = client.post(
        f"/api/v1/courses/{course_id}/study-plan",
        json={"available_hours": 6, "baseline_mastery": 0.5},
    )
    assert plan.status_code == 200
    plan_payload = plan.json()
    assert plan_payload["planning_model"] == "heuristic-v5"
    assert plan_payload["calibrated_learning_topic_count"] > 0
    assert any(
        item["learning_scale_hours"] < 2.8 for item in plan_payload["allocations"]
    )


def test_retention_calibration_uses_time_separated_performance_drop(
    client: TestClient,
) -> None:
    course_id = _prepare_course(client)
    _answer_sequence(client, course_id, [0.9, 0.8, 0.7, 0.6])

    session_factory = client.app.state.session_factory
    with session_factory() as db:
        snapshots = list(
            db.scalars(
                select(MasterySnapshot)
                .where(MasterySnapshot.course_id == course_id)
                .order_by(MasterySnapshot.recorded_at, MasterySnapshot.id)
            ).all()
        )
        grouped: dict[str, list[MasterySnapshot]] = defaultdict(list)
        for snapshot in snapshots:
            grouped[snapshot.topic_id].append(snapshot)
        topic_id, points = max(grouped.items(), key=lambda item: len(item[1]))
        assert len(points) >= 3

        now = datetime.now(UTC)
        scores = [0.95, 0.75, 0.55, 0.45]
        for index, point in enumerate(points):
            point.recorded_at = now - timedelta(days=7 * (len(points) - index - 1))
            point.source_score = scores[min(index, len(scores) - 1)]
        db.commit()

    response = client.get(f"/api/v1/courses/{course_id}/calibration")
    assert response.status_code == 200
    by_topic = {item["topic_id"]: item for item in response.json()["topics"]}
    calibrated = by_topic[topic_id]
    assert calibrated["retention_observation_count"] >= 2
    assert calibrated["retention_confidence"] in {"medium", "high"}
    assert calibrated["retention_half_life_days"] is not None

    reviews = client.get(f"/api/v1/courses/{course_id}/reviews")
    assert reviews.status_code == 200
    review_by_topic = {item["topic_id"]: item for item in reviews.json()["items"]}
    assert review_by_topic[topic_id]["retention_model"] == "calibrated"


def test_calibration_missing_course_returns_404(client: TestClient) -> None:
    response = client.get("/api/v1/courses/not-a-course/calibration")
    assert response.status_code == 404
