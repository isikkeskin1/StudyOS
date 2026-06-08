from __future__ import annotations

from fastapi.testclient import TestClient


def _create_course(client: TestClient) -> str:
    response = client.post(
        "/api/v1/courses",
        json={"name": "Physics I", "target_grade": 25, "max_grade": 30},
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
    assert (
        client.post(f"/api/v1/courses/{course_id}/documents/{document_id}/process").status_code
        == 200
    )


def _prepare_solution_course(client: TestClient) -> str:
    course_id = _create_course(client)
    _upload_and_process(
        client,
        course_id,
        "lecture-mechanics.txt",
        (
            b"Force\n"
            b"Force depends on mass and acceleration. Force is measured in newtons. "
            b"Force and acceleration are central to Newton's second law.\n\n"
            b"Momentum\n"
            b"Momentum is conserved in collisions. Momentum equals mass times velocity."
        ),
    )
    _upload_and_process(
        client,
        course_id,
        "2025-written-exam-solutions.txt",
        (
            b"Physics I Written Exam Solutions\n"
            b"Question 1 (8 marks)\n"
            b"State Newton's second law and calculate the force.\n"
            b"Solution: Newton's second law says force equals mass times acceleration. "
            b"The force is 10 N.\n\n"
            b"Question 2 (12 marks)\n"
            b"Use conservation of momentum to determine the final momentum.\n"
            b"Solution: Momentum is conserved, so initial momentum equals final momentum. "
            b"The final momentum is 20 kg m/s."
        ),
    )
    assert client.post(f"/api/v1/courses/{course_id}/analyze").status_code == 200
    assert (
        client.post(f"/api/v1/courses/{course_id}/exam-intelligence/analyze").status_code
        == 200
    )
    return course_id


def _start_session(client: TestClient, course_id: str, max_items: int = 5) -> dict:
    response = client.post(
        f"/api/v1/courses/{course_id}/tutor/practice-sessions",
        json={"provider": "local", "difficulty": "medium", "max_items": max_items},
    )
    assert response.status_code == 201
    return response.json()


def _evaluate(
    client: TestClient,
    course_id: str,
    session_id: str,
    practice_id: str,
    answer: str,
    *,
    generate_next: bool = True,
) -> dict:
    response = client.post(
        f"/api/v1/courses/{course_id}/tutor/practice/{practice_id}/evaluate",
        json={
            "student_answer": answer,
            "generate_next": generate_next,
            "grading_provider": "local",
            "session_id": session_id,
        },
    )
    assert response.status_code == 200
    return response.json()


def test_session_accumulates_attempt_history_and_recurring_mistakes(client: TestClient) -> None:
    course_id = _prepare_solution_course(client)
    session = _start_session(client, course_id)

    first = _evaluate(
        client,
        course_id,
        session["id"],
        session["current_practice"]["id"],
        "I do not know.",
    )
    assert first["next_practice"] is not None
    assert first["session_context"]["recent_attempt_count"] == 1

    second = _evaluate(
        client,
        course_id,
        session["id"],
        first["next_practice"]["id"],
        "I do not know.",
    )

    assert second["next_strategy"] == "remediate_pattern"
    assert second["session_context"]["recent_attempt_count"] == 2
    assert second["session_context"]["dominant_mistake_count"] >= 2
    assert second["session_context"]["focus_topic"] is not None

    summary = client.get(
        f"/api/v1/courses/{course_id}/tutor/practice-sessions/{session['id']}"
    )
    assert summary.status_code == 200
    payload = summary.json()
    assert payload["attempt_count"] == 2
    assert payload["item_count"] == 3
    assert payload["dominant_mistakes"]
    assert payload["dominant_mistakes"][0]["occurrences"] >= 2
    assert payload["topic_summaries"]


def test_session_hint_dependence_triggers_scaffolding_remediation(client: TestClient) -> None:
    course_id = _prepare_solution_course(client)
    session = _start_session(client, course_id)
    practice = session["current_practice"]
    for _ in range(2):
        hint = client.post(
            f"/api/v1/courses/{course_id}/tutor/practice/{practice['id']}/hint"
        )
        assert hint.status_code == 200

    result = _evaluate(
        client,
        course_id,
        session["id"],
        practice["id"],
        "I do not know.",
    )

    assert result["next_strategy"] in {"reduce_scaffolding", "reinforce"}
    assert result["session_context"]["recent_average_hints"] == 2.0
    assert result["next_practice"] is not None
    assert result["next_practice"]["difficulty"] == "easy"


def test_session_completes_at_item_limit(client: TestClient) -> None:
    course_id = _prepare_solution_course(client)
    session = _start_session(client, course_id, max_items=2)

    first = _evaluate(
        client,
        course_id,
        session["id"],
        session["current_practice"]["id"],
        "I do not know.",
    )
    assert first["next_practice"] is not None

    second = _evaluate(
        client,
        course_id,
        session["id"],
        first["next_practice"]["id"],
        "I do not know.",
    )
    assert second["next_strategy"] == "session_complete"
    assert second["next_practice"] is None

    summary = client.get(
        f"/api/v1/courses/{course_id}/tutor/practice-sessions/{session['id']}"
    )
    assert summary.status_code == 200
    assert summary.json()["status"] == "completed"
    assert summary.json()["item_count"] == 2
    assert summary.json()["attempt_count"] == 2


def test_session_rejects_practice_from_another_session_before_grading(client: TestClient) -> None:
    course_id = _prepare_solution_course(client)
    first_session = _start_session(client, course_id)
    second_session = _start_session(client, course_id)

    response = client.post(
        f"/api/v1/courses/{course_id}/tutor/practice/"
        f"{first_session['current_practice']['id']}/evaluate",
        json={
            "student_answer": "I do not know.",
            "generate_next": False,
            "grading_provider": "local",
            "session_id": second_session["id"],
        },
    )
    assert response.status_code == 409
    assert "does not belong" in response.json()["detail"].lower()

    summary = client.get(
        f"/api/v1/courses/{course_id}/tutor/practice-sessions/{first_session['id']}"
    )
    assert summary.status_code == 200
    assert summary.json()["attempt_count"] == 0
