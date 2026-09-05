from __future__ import annotations

from fastapi.testclient import TestClient


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


def _prepare_course(client: TestClient) -> str:
    course_id = _create_course(client)
    _upload_and_process(
        client,
        course_id,
        "lecture-mechanics.txt",
        (
            b"Newton's Laws\n"
            b"Newton's laws relate force, mass, and acceleration. "
            b"Newton's second law is used in dynamics problems.\n\n"
            b"Momentum\n"
            b"Momentum is conserved in isolated collisions. "
            b"Impulse changes momentum. Momentum is a vector quantity."
        ),
    )
    _upload_and_process(
        client,
        course_id,
        "2025-written-exam.txt",
        (
            b"Physics I Written Exam\n"
            b"Question 1 (8 marks)\n"
            b"Use Newton's second law to calculate the force and acceleration.\n\n"
            b"Question 2 (12 marks)\n"
            b"Use conservation of momentum to solve the collision and find momentum after impact."
        ),
    )
    analysis = client.post(f"/api/v1/courses/{course_id}/analyze")
    assert analysis.status_code == 200
    exams = client.post(f"/api/v1/courses/{course_id}/exam-intelligence/analyze")
    assert exams.status_code == 200
    return course_id


def test_diagnostic_selects_questions_updates_mastery_and_completes(
    client: TestClient,
) -> None:
    course_id = _prepare_course(client)
    start = client.post(
        f"/api/v1/courses/{course_id}/diagnostics",
        json={"question_count": 2},
    )
    assert start.status_code == 201
    session = start.json()
    session_id = session["id"]
    assert session["status"] == "active"
    assert session["requested_question_count"] == 2

    first = client.get(f"/api/v1/courses/{course_id}/diagnostics/{session_id}/next")
    assert first.status_code == 200
    first_question = first.json()["question"]
    assert first_question is not None
    assert first_question["topics"]

    repeated = client.get(f"/api/v1/courses/{course_id}/diagnostics/{session_id}/next")
    assert repeated.status_code == 200
    assert repeated.json()["question"]["id"] == first_question["id"]

    scored = client.post(
        f"/api/v1/courses/{course_id}/diagnostics/{session_id}/responses",
        json={
            "diagnostic_question_id": first_question["id"],
            "score": 1.0,
            "confidence": 0.9,
            "grading_source": "self",
            "duration_seconds": 180,
        },
    )
    assert scored.status_code == 200
    assert scored.json()["mastery"]
    assert any(item["mastery"] > 0.5 for item in scored.json()["mastery"])

    second = client.get(f"/api/v1/courses/{course_id}/diagnostics/{session_id}/next")
    assert second.status_code == 200
    second_question = second.json()["question"]
    assert second_question is not None
    assert second_question["id"] != first_question["id"]

    final = client.post(
        f"/api/v1/courses/{course_id}/diagnostics/{session_id}/responses",
        json={
            "diagnostic_question_id": second_question["id"],
            "score": 0.0,
            "confidence": 0.8,
            "grading_source": "self",
        },
    )
    assert final.status_code == 200
    assert final.json()["session"]["status"] == "completed"
    assert final.json()["session"]["answered_question_count"] == 2


def test_duplicate_diagnostic_response_is_rejected(client: TestClient) -> None:
    course_id = _prepare_course(client)
    start = client.post(
        f"/api/v1/courses/{course_id}/diagnostics",
        json={"question_count": 1},
    )
    session_id = start.json()["id"]
    question = client.get(
        f"/api/v1/courses/{course_id}/diagnostics/{session_id}/next"
    ).json()["question"]

    payload = {
        "diagnostic_question_id": question["id"],
        "score": 0.75,
        "confidence": 0.5,
        "grading_source": "manual",
    }
    first = client.post(
        f"/api/v1/courses/{course_id}/diagnostics/{session_id}/responses",
        json=payload,
    )
    second = client.post(
        f"/api/v1/courses/{course_id}/diagnostics/{session_id}/responses",
        json=payload,
    )

    assert first.status_code == 200
    assert second.status_code == 409


def test_study_plan_uses_diagnostic_mastery_by_default(client: TestClient) -> None:
    course_id = _prepare_course(client)
    start = client.post(
        f"/api/v1/courses/{course_id}/diagnostics",
        json={"question_count": 1},
    )
    session_id = start.json()["id"]
    question = client.get(
        f"/api/v1/courses/{course_id}/diagnostics/{session_id}/next"
    ).json()["question"]
    response = client.post(
        f"/api/v1/courses/{course_id}/diagnostics/{session_id}/responses",
        json={
            "diagnostic_question_id": question["id"],
            "score": 1.0,
            "confidence": 1.0,
        },
    )
    assert response.status_code == 200

    plan = client.post(
        f"/api/v1/courses/{course_id}/study-plan",
        json={"baseline_mastery": 0.1, "available_hours": 4},
    )
    assert plan.status_code == 200
    assert any(
        item["mastery_source"] == "diagnostic"
        for item in plan.json()["allocations"]
    )


def test_diagnostic_requires_past_exam_questions(client: TestClient) -> None:
    course_id = _create_course(client)
    _upload_and_process(
        client,
        course_id,
        "lecture.txt",
        b"Momentum\nMomentum is conserved. Momentum is a vector quantity.",
    )
    analysis = client.post(f"/api/v1/courses/{course_id}/analyze")
    assert analysis.status_code == 200

    response = client.post(
        f"/api/v1/courses/{course_id}/diagnostics",
        json={"question_count": 5},
    )
    assert response.status_code == 409
