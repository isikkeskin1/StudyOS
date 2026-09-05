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


def _create_practice(client: TestClient, course_id: str, difficulty: str = "medium") -> dict:
    response = client.post(
        f"/api/v1/courses/{course_id}/tutor/practice",
        json={"provider": "local", "difficulty": difficulty},
    )
    assert response.status_code == 201
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


def _evaluate(
    client: TestClient,
    course_id: str,
    practice: dict,
    answer: str,
    *,
    generate_next: bool = False,
) -> dict:
    response = client.post(
        f"/api/v1/courses/{course_id}/tutor/practice/{practice['id']}/evaluate",
        json={
            "student_answer": answer,
            "duration_seconds": 75,
            "generate_next": generate_next,
        },
    )
    assert response.status_code == 200
    return response.json()


def test_practice_evaluation_updates_mastery_and_generates_harder_followup(
    client: TestClient,
) -> None:
    course_id = _prepare_solution_course(client)
    practice = _create_practice(client, course_id, "medium")

    result = _evaluate(
        client,
        course_id,
        practice,
        _correct_answer(practice["question"]),
        generate_next=True,
    )

    assert result["score"] >= 0.85
    assert result["hints_used"] == 0
    assert result["mastery_weight"] > 0
    assert result["mastery_after"] is not None
    assert result["mastery_after"]["response_count"] == 1
    assert result["next_strategy"] in {"increase_difficulty", "reoptimize"}
    assert result["next_practice"] is not None
    assert result["next_practice"]["difficulty"] == "hard"

    mastery = client.get(f"/api/v1/courses/{course_id}/mastery")
    assert mastery.status_code == 200
    assert any(item["response_count"] == 1 for item in mastery.json())


def test_hints_reduce_mastery_weight_without_changing_correctness(client: TestClient) -> None:
    clean_course = _prepare_solution_course(client)
    clean_practice = _create_practice(client, clean_course)
    clean = _evaluate(
        client,
        clean_course,
        clean_practice,
        _correct_answer(clean_practice["question"]),
    )

    hinted_course = _prepare_solution_course(client)
    hinted_practice = _create_practice(client, hinted_course)
    for _ in range(2):
        hint = client.post(
            f"/api/v1/courses/{hinted_course}/tutor/practice/{hinted_practice['id']}/hint"
        )
        assert hint.status_code == 200
    hinted = _evaluate(
        client,
        hinted_course,
        hinted_practice,
        _correct_answer(hinted_practice["question"]),
    )

    assert hinted["score"] == clean["score"]
    assert hinted["hints_used"] == 2
    assert hinted["mastery_weight"] < clean["mastery_weight"]


def test_revealed_solution_cannot_be_submitted_as_mastery_evidence(client: TestClient) -> None:
    course_id = _prepare_solution_course(client)
    practice = _create_practice(client, course_id)
    revealed = client.get(
        f"/api/v1/courses/{course_id}/tutor/practice/{practice['id']}/solution"
    )
    assert revealed.status_code == 200

    response = client.post(
        f"/api/v1/courses/{course_id}/tutor/practice/{practice['id']}/evaluate",
        json={"student_answer": revealed.json()["solution"]},
    )

    assert response.status_code == 409
    assert "revealed" in response.json()["detail"].lower()


def test_practice_evaluation_is_idempotent_per_item(client: TestClient) -> None:
    course_id = _prepare_solution_course(client)
    practice = _create_practice(client, course_id)
    answer = _correct_answer(practice["question"])
    first = client.post(
        f"/api/v1/courses/{course_id}/tutor/practice/{practice['id']}/evaluate",
        json={"student_answer": answer, "generate_next": False},
    )
    second = client.post(
        f"/api/v1/courses/{course_id}/tutor/practice/{practice['id']}/evaluate",
        json={"student_answer": answer, "generate_next": False},
    )

    assert first.status_code == 200
    assert second.status_code == 409
    assert "already been evaluated" in second.json()["detail"].lower()


def test_weak_hint_dependent_attempt_reinforces_and_updates_mistakes(
    client: TestClient,
) -> None:
    course_id = _prepare_solution_course(client)
    practice = _create_practice(client, course_id, "medium")
    for _ in range(2):
        hint = client.post(
            f"/api/v1/courses/{course_id}/tutor/practice/{practice['id']}/hint"
        )
        assert hint.status_code == 200

    result = _evaluate(
        client,
        course_id,
        practice,
        "I do not know.",
        generate_next=True,
    )

    assert result["score"] < 0.55
    assert result["next_strategy"] == "reinforce"
    assert result["next_practice"] is not None
    assert result["next_practice"]["difficulty"] == "easy"
    assert "concept" in {item["category"] for item in result["mistakes"]}

    mistakes = client.get(f"/api/v1/courses/{course_id}/mistakes")
    assert mistakes.status_code == 200
    payload = mistakes.json()
    assert payload["response_count"] == 1
    assert payload["responses_with_mistakes"] == 1
    assert "concept" in {item["category"] for item in payload["categories"]}
    assert payload["topics"]
    assert payload["topics"][0]["mistake_burden"] > 0

    plan = client.post(
        f"/api/v1/courses/{course_id}/study-plan",
        json={"available_hours": 4, "baseline_mastery": 0.5},
    )
    assert plan.status_code == 200
    assert any(item["mistake_burden"] > 0 for item in plan.json()["allocations"])
