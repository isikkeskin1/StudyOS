from __future__ import annotations

from datetime import UTC, datetime, timedelta

from fastapi.testclient import TestClient
from sqlalchemy import select

from app.models.diagnostics import TopicMastery


def _create_course(client: TestClient) -> str:
    response = client.post(
        "/api/v1/courses",
        json={
            "name": "Physics I",
            "target_grade": 25,
            "max_grade": 30,
        },
    )
    assert response.status_code == 201
    return response.json()["id"]


def _upload_and_process(
    client: TestClient,
    course_id: str,
    filename: str,
    content: bytes,
) -> None:
    upload = client.post(
        f"/api/v1/courses/{course_id}/documents",
        files={"file": (filename, content, "text/plain")},
    )
    assert upload.status_code == 201
    document_id = upload.json()["id"]
    process = client.post(f"/api/v1/courses/{course_id}/documents/{document_id}/process")
    assert process.status_code == 200


def _prepare_mastery(client: TestClient) -> str:
    course_id = _create_course(client)
    _upload_and_process(
        client,
        course_id,
        "lecture-mechanics.txt",
        (
            b"Momentum\n"
            b"Momentum is conserved. Momentum equals mass times velocity. "
            b"Momentum is a vector quantity.\n\n"
            b"Force\n"
            b"Force equals mass times acceleration. Force is measured in newtons."
        ),
    )
    _upload_and_process(
        client,
        course_id,
        "2025-written-exam.txt",
        (
            b"Physics I Written Exam\n"
            b"Question 1 (10 marks)\n"
            b"Use conservation of momentum to calculate momentum after impact.\n\n"
            b"Question 2 (10 marks)\n"
            b"Use force and acceleration to calculate the net force."
        ),
    )
    assert client.post(f"/api/v1/courses/{course_id}/analyze").status_code == 200
    assert (
        client.post(f"/api/v1/courses/{course_id}/exam-intelligence/analyze").status_code
        == 200
    )
    start = client.post(
        f"/api/v1/courses/{course_id}/diagnostics",
        json={"question_count": 1},
    )
    session_id = start.json()["id"]
    question = client.get(
        f"/api/v1/courses/{course_id}/diagnostics/{session_id}/next"
    ).json()["question"]
    scored = client.post(
        f"/api/v1/courses/{course_id}/diagnostics/{session_id}/responses",
        json={
            "diagnostic_question_id": question["id"],
            "score": 1.0,
            "confidence": 0.9,
        },
    )
    assert scored.status_code == 200
    return course_id


def _age_mastery(client: TestClient, course_id: str, days: int) -> None:
    session_factory = client.app.state.session_factory
    with session_factory() as db:
        rows = list(
            db.scalars(
                select(TopicMastery).where(TopicMastery.course_id == course_id)
            ).all()
        )
        assert rows
        for row in rows:
            row.updated_at = datetime.now(UTC) - timedelta(days=days)
        db.commit()


def test_recent_mastery_has_little_forgetting(client: TestClient) -> None:
    course_id = _prepare_mastery(client)

    response = client.get(f"/api/v1/courses/{course_id}/reviews")

    assert response.status_code == 200
    payload = response.json()
    assert payload["tracked_topic_count"] >= 1
    item = payload["items"][0]
    assert item["days_since_evidence"] < 1
    assert abs(item["raw_mastery"] - item["effective_mastery"]) < 0.01
    assert item["forgetting_loss"] < 0.01


def test_old_mastery_becomes_due_for_review(client: TestClient) -> None:
    course_id = _prepare_mastery(client)
    _age_mastery(client, course_id, 35)

    response = client.get(f"/api/v1/courses/{course_id}/reviews")

    assert response.status_code == 200
    payload = response.json()
    assert payload["due_topic_count"] >= 1
    due = [item for item in payload["items"] if item["due_for_review"]]
    assert due
    assert due[0]["effective_mastery"] < due[0]["raw_mastery"]
    assert due[0]["forgetting_loss"] >= 0.05
    assert due[0]["recommended_minutes"] >= 10
    assert payload["total_recommended_minutes"] >= due[0]["recommended_minutes"]


def test_study_plan_uses_decayed_diagnostic_mastery(client: TestClient) -> None:
    course_id = _prepare_mastery(client)
    raw_mastery = {
        item["topic_id"]: item["mastery"]
        for item in client.get(f"/api/v1/courses/{course_id}/mastery").json()
    }
    _age_mastery(client, course_id, 45)

    plan = client.post(
        f"/api/v1/courses/{course_id}/study-plan",
        json={"baseline_mastery": 0.1, "available_hours": 4},
    )

    assert plan.status_code == 200
    assert plan.json()["planning_model"] == "heuristic-v4"
    diagnostic_rows = [
        item
        for item in plan.json()["allocations"]
        if item["mastery_source"] == "diagnostic"
    ]
    assert diagnostic_rows
    row = diagnostic_rows[0]
    assert row["raw_mastery"] == raw_mastery[row["topic_id"]]
    assert row["current_mastery"] < row["raw_mastery"]
    assert row["forgetting_loss"] > 0
    assert row["days_since_evidence"] >= 44
    assert row["retention_half_life_days"] > 0
