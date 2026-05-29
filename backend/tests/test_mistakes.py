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
                "lecture.txt",
                (
                    b"Newton's Laws\n"
                    b"Newton's second law relates force, mass, and acceleration.\n\n"
                    b"Momentum\n"
                    b"Momentum is conserved in isolated collisions."
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
                "2025-exam.txt",
                (
                    b"Physics I Written Exam\n"
                    b"Question 1 (10 marks)\n"
                    b"Use Newton's second law to calculate force and acceleration.\n\n"
                    b"Question 2 (10 marks)\n"
                    b"Use conservation of momentum to solve the collision."
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


def _start_question(client: TestClient, course_id: str) -> tuple[str, dict]:
    session = client.post(
        f"/api/v1/courses/{course_id}/diagnostics",
        json={"question_count": 1},
    )
    assert session.status_code == 201
    session_id = session.json()["id"]
    next_question = client.get(
        f"/api/v1/courses/{course_id}/diagnostics/{session_id}/next"
    )
    assert next_question.status_code == 200
    return session_id, next_question.json()["question"]


def test_response_stores_answer_feedback_and_mistake_labels(client: TestClient) -> None:
    course_id = _prepare_course(client)
    session_id, question = _start_question(client, course_id)

    response = client.post(
        f"/api/v1/courses/{course_id}/diagnostics/{session_id}/responses",
        json={
            "diagnostic_question_id": question["id"],
            "score": 0.25,
            "confidence": 0.9,
            "grading_source": "manual",
            "student_answer": "F = m / a, then I got 4 N.",
            "reference_answer": "Use F = ma and keep SI units.",
            "feedback": "Correct setup idea, but wrong algebra and units.",
            "mistakes": [
                {
                    "category": "algebra",
                    "severity": 0.8,
                    "source": "manual",
                    "note": "Rearranged the formula incorrectly.",
                },
                {
                    "category": "units",
                    "severity": 0.4,
                    "source": "manual",
                },
            ],
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["answer"]["student_answer"].startswith("F = m / a")
    assert payload["answer"]["reference_answer"].startswith("Use F = ma")
    assert {item["category"] for item in payload["mistakes"]} == {"algebra", "units"}


def test_course_mistake_intelligence_aggregates_lost_marks(client: TestClient) -> None:
    course_id = _prepare_course(client)
    session_id, question = _start_question(client, course_id)

    scored = client.post(
        f"/api/v1/courses/{course_id}/diagnostics/{session_id}/responses",
        json={
            "diagnostic_question_id": question["id"],
            "score": 0.4,
            "mistakes": [
                {"category": "concept", "severity": 1.0},
                {"category": "algebra", "severity": 0.5},
            ],
        },
    )
    assert scored.status_code == 200

    response = client.get(f"/api/v1/courses/{course_id}/mistakes")
    assert response.status_code == 200
    payload = response.json()
    assert payload["response_count"] == 1
    assert payload["responses_with_mistakes"] == 1
    assert payload["lost_score_total"] == 0.6
    assert payload["classification_coverage"] == 1.0
    assert {item["category"] for item in payload["categories"]} == {
        "concept",
        "algebra",
    }
    assert payload["topics"]
    assert payload["topics"][0]["mistake_burden"] > 0


def test_classified_mistakes_feed_study_plan_focus(client: TestClient) -> None:
    course_id = _prepare_course(client)
    session_id, question = _start_question(client, course_id)

    scored = client.post(
        f"/api/v1/courses/{course_id}/diagnostics/{session_id}/responses",
        json={
            "diagnostic_question_id": question["id"],
            "score": 0.3,
            "mistakes": [{"category": "sign", "severity": 1.0}],
        },
    )
    assert scored.status_code == 200

    plan = client.post(
        f"/api/v1/courses/{course_id}/study-plan",
        json={"available_hours": 4, "baseline_mastery": 0.5},
    )
    assert plan.status_code == 200
    payload = plan.json()
    assert payload["planning_model"] == "heuristic-v4"
    assert any(item["mistake_burden"] > 0 for item in payload["allocations"])
    assert any("sign" in item["mistake_focus"] for item in payload["allocations"])
    assert any("mistake patterns adjust study priority" in item for item in payload["assumptions"])


def test_duplicate_mistake_categories_are_rejected(client: TestClient) -> None:
    course_id = _prepare_course(client)
    session_id, question = _start_question(client, course_id)

    response = client.post(
        f"/api/v1/courses/{course_id}/diagnostics/{session_id}/responses",
        json={
            "diagnostic_question_id": question["id"],
            "score": 0.5,
            "mistakes": [
                {"category": "units"},
                {"category": "units"},
            ],
        },
    )

    assert response.status_code == 422
