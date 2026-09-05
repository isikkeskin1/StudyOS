from __future__ import annotations

from fastapi.testclient import TestClient
from sqlalchemy import select

from app.models.course_intelligence import CourseTopic
from app.models.tutor_practice import TutorPracticeAttempt, TutorPracticeItem, TutorPracticeMistake


def _create_course(client: TestClient) -> str:
    response = client.post("/api/v1/courses", json={"name": "Physics I"})
    assert response.status_code == 201
    return response.json()["id"]


def _upload_and_process(
    client: TestClient,
    course_id: str,
    filename: str,
    content: bytes,
) -> str:
    upload = client.post(
        f"/api/v1/courses/{course_id}/documents",
        files={"file": (filename, content, "text/plain")},
    )
    assert upload.status_code == 201
    document_id = upload.json()["id"]
    process = client.post(f"/api/v1/courses/{course_id}/documents/{document_id}/process")
    assert process.status_code == 200
    return document_id


def _analyzed_course(client: TestClient) -> str:
    course_id = _create_course(client)
    _upload_and_process(
        client,
        course_id,
        "lecture-mechanics.txt",
        (
            b"Newton's Second Law\n"
            b"The force formula is F = m a, where m is mass and a is acceleration. "
            b"Method: first draw a free-body diagram, then choose axes and apply the equation.\n\n"
            b"Momentum\n"
            b"Momentum is p = m v. In an isolated system total momentum is conserved."
        ),
    )
    _upload_and_process(
        client,
        course_id,
        "2025-written-exam.txt",
        (
            b"Physics I Written Exam\n"
            b"Question 1: Use Newton's second law to determine the acceleration.\n"
            b"Question 2: Calculate momentum before and after a collision."
        ),
    )
    analysis = client.post(f"/api/v1/courses/{course_id}/analyze")
    assert analysis.status_code == 200
    return course_id


def test_cheat_sheet_is_source_grounded_and_persistent(client: TestClient) -> None:
    course_id = _analyzed_course(client)

    created = client.post(
        f"/api/v1/courses/{course_id}/cheat-sheets",
        json={"max_topics": 6, "max_items_per_topic": 3},
    )

    assert created.status_code == 201
    sheet = created.json()
    assert sheet["course_id"] == course_id
    assert sheet["topic_count"] > 0
    assert sheet["item_count"] > 0
    assert sheet["source_count"] > 0
    assert sheet["source_manifest"]
    assert any(
        item["kind"] in {"formula", "method"}
        for section in sheet["sections"]
        for item in section["items"]
    )

    material_items = [
        item
        for section in sheet["sections"]
        for item in section["items"]
    ]
    assert material_items
    for item in material_items:
        assert item["citations"]
        citation = item["citations"][0]
        assert citation["document_id"]
        assert citation["chunk_id"]
        assert citation["source_label"]
        assert citation["filename"]
        assert citation["quote"] == item["text"]

    listed = client.get(f"/api/v1/courses/{course_id}/cheat-sheets")
    fetched = client.get(
        f"/api/v1/courses/{course_id}/cheat-sheets/{sheet['id']}"
    )
    assert listed.status_code == 200
    assert listed.json()[0]["id"] == sheet["id"]
    assert fetched.status_code == 200
    assert fetched.json() == sheet


def test_cheat_sheet_requires_course_analysis(client: TestClient) -> None:
    course_id = _create_course(client)

    response = client.post(
        f"/api/v1/courses/{course_id}/cheat-sheets",
        json={},
    )

    assert response.status_code == 409
    assert response.json()["detail"] == "Course has not been analyzed"


def test_cheat_sheet_can_include_recurring_mistake_warnings(client: TestClient) -> None:
    course_id = _analyzed_course(client)
    session_factory = client.app.state.session_factory

    with session_factory() as db:
        topic = db.scalar(
            select(CourseTopic)
            .where(CourseTopic.course_id == course_id)
            .order_by(CourseTopic.importance_score.desc())
        )
        assert topic is not None
        practice = TutorPracticeItem(
            course_id=course_id,
            topic_id=topic.id,
            topic_name=topic.name,
            topic_selection="test",
            difficulty="medium",
            marks=4,
            provider_requested="local",
            generation_provider="local",
            generation_mode="test",
            retrieval_model=None,
            question="State the governing relationship.",
            hints=[],
            solution="Use the source equation.",
        )
        db.add(practice)
        db.flush()

        attempt = TutorPracticeAttempt(
            practice_id=practice.id,
            course_id=course_id,
            student_answer="Incorrect setup",
            score=0.25,
            grader_name="test",
            grader_confidence=1.0,
            evidence_coverage=1.0,
            mastery_weight=1.0,
            hints_used=0,
            duration_seconds=30,
            feedback="Check the sign convention.",
        )
        db.add(attempt)
        db.flush()
        db.add(
            TutorPracticeMistake(
                attempt_id=attempt.id,
                category="sign_error",
                severity=1.0,
                source="test",
                note="Used the wrong sign.",
            )
        )
        db.commit()
        topic_id = topic.id

    response = client.post(
        f"/api/v1/courses/{course_id}/cheat-sheets",
        json={"max_topics": 20, "include_mistakes": True},
    )

    assert response.status_code == 201
    section = next(
        item for item in response.json()["sections"] if item["topic_id"] == topic_id
    )
    assert section["mistake_burden"] > 0
    assert section["mistake_warnings"]
    assert section["mistake_warnings"][0]["category"] == "sign_error"


def test_cheat_sheet_request_limits_are_validated(client: TestClient) -> None:
    course_id = _analyzed_course(client)

    response = client.post(
        f"/api/v1/courses/{course_id}/cheat-sheets",
        json={"max_topics": 0, "max_items_per_topic": 99},
    )

    assert response.status_code == 422
