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


def _start_session(client: TestClient, course_id: str) -> dict:
    response = client.post(
        f"/api/v1/courses/{course_id}/tutor/practice-sessions",
        json={"provider": "local", "difficulty": "medium", "max_items": 6},
    )
    assert response.status_code == 201
    return response.json()


def _evaluate(
    client: TestClient,
    course_id: str,
    session_id: str,
    practice_id: str,
    answer: str,
) -> dict:
    response = client.post(
        f"/api/v1/courses/{course_id}/tutor/practice/{practice_id}/evaluate",
        json={
            "student_answer": answer,
            "generate_next": True,
            "grading_provider": "local",
            "session_id": session_id,
        },
    )
    assert response.status_code == 200
    return response.json()


def _correct_answer(question: str) -> str:
    if "momentum" in question.lower():
        return (
            "Solution: Momentum is conserved, so initial momentum equals final momentum. "
            "The final momentum is 20 kg m/s."
        )
    return (
        "Solution: Newton's second law says force equals mass times acceleration. "
        "The force is 10 N."
    )


def test_first_session_question_gets_baseline_teaching_plan(client: TestClient) -> None:
    course_id = _prepare_solution_course(client)
    session = _start_session(client, course_id)

    response = client.get(
        f"/api/v1/courses/{course_id}/tutor/practice-sessions/{session['id']}/teaching"
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["practice_id"] == session["current_practice"]["id"]
    assert payload["strategy"] == "baseline"
    assert payload["recent_attempt_count"] == 0
    assert payload["dominant_mistake"] is None
    assert len(payload["coaching_steps"]) == 3


def test_recurring_mistakes_change_teaching_intro_and_hidden_hints(client: TestClient) -> None:
    course_id = _prepare_solution_course(client)
    session = _start_session(client, course_id)

    first = _evaluate(
        client,
        course_id,
        session["id"],
        session["current_practice"]["id"],
        "I do not know.",
    )
    second = _evaluate(
        client,
        course_id,
        session["id"],
        first["next_practice"]["id"],
        "I do not know.",
    )
    assert second["next_practice"] is not None

    teaching = client.get(
        f"/api/v1/courses/{course_id}/tutor/practice-sessions/{session['id']}/teaching"
    )
    assert teaching.status_code == 200
    payload = teaching.json()
    assert payload["strategy"] == "remediate_pattern"
    assert payload["dominant_mistake"] is not None
    assert payload["dominant_mistake_count"] >= 2
    assert payload["coaching_steps"][0]

    hint = client.post(
        f"/api/v1/courses/{course_id}/tutor/practice-sessions/{session['id']}/practice/"
        f"{second['next_practice']['id']}/hint"
    )
    assert hint.status_code == 200
    hint_payload = hint.json()
    assert hint_payload["strategy"] == "remediate_pattern"
    assert hint_payload["dominant_mistake"] == payload["dominant_mistake"]
    assert hint_payload["hint"].startswith(payload["coaching_steps"][0])
    assert hint_payload["level"] == 1


def test_two_strong_unassisted_answers_switch_teaching_to_challenge(client: TestClient) -> None:
    course_id = _prepare_solution_course(client)
    session = _start_session(client, course_id)

    first_practice = session["current_practice"]
    first = _evaluate(
        client,
        course_id,
        session["id"],
        first_practice["id"],
        _correct_answer(first_practice["question"]),
    )
    second_practice = first["next_practice"]
    second = _evaluate(
        client,
        course_id,
        session["id"],
        second_practice["id"],
        _correct_answer(second_practice["question"]),
    )
    assert second["next_practice"] is not None

    teaching = client.get(
        f"/api/v1/courses/{course_id}/tutor/practice-sessions/{session['id']}/teaching"
    )
    assert teaching.status_code == 200
    payload = teaching.json()
    assert payload["strategy"] == "challenge"
    assert payload["dominant_mistake"] is None
    assert "without hints" in payload["teaching_intro"].lower()


def test_teaching_hint_rejects_practice_from_another_session(client: TestClient) -> None:
    course_id = _prepare_solution_course(client)
    first = _start_session(client, course_id)
    second = _start_session(client, course_id)

    response = client.post(
        f"/api/v1/courses/{course_id}/tutor/practice-sessions/{second['id']}/practice/"
        f"{first['current_practice']['id']}/hint"
    )

    assert response.status_code == 409
    assert "does not belong" in response.json()["detail"].lower()
