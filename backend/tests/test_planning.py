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
    return course_id


def test_exam_intelligence_extracts_questions_marks_and_topic_weights(
    client: TestClient,
) -> None:
    course_id = _prepare_course(client)

    response = client.post(f"/api/v1/courses/{course_id}/exam-intelligence/analyze")

    assert response.status_code == 200
    payload = response.json()
    assert payload["exam_document_count"] == 1
    assert payload["question_count"] == 2
    assert payload["marked_question_count"] == 2
    assert payload["total_known_marks"] == 20
    assert [question["question_label"] for question in payload["questions"]] == ["Q1", "Q2"]
    assert all(question["topics"] for question in payload["questions"])
    assert payload["topics"]
    assert abs(sum(topic["exam_weight"] for topic in payload["topics"]) - 1.0) < 0.01


def test_study_plan_uses_target_available_hours_and_diminishing_returns(
    client: TestClient,
) -> None:
    course_id = _prepare_course(client)

    response = client.post(
        f"/api/v1/courses/{course_id}/study-plan",
        json={"baseline_mastery": 0.5, "available_hours": 20},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["planning_model"] == "heuristic-v5"
    assert payload["confidence"] == "low"
    assert payload["target_grade"] == 25
    assert payload["current_estimated_grade"] == 15
    assert payload["estimated_hours_to_target"] > 0
    assert payload["projected_grade_with_available_hours"] > payload["current_estimated_grade"]
    assert abs(sum(item["recommended_hours"] for item in payload["allocations"]) - 20) < 0.01
    assert all(item["mastery_source"] == "baseline" for item in payload["allocations"])
    assert all(item["mistake_burden"] == 0 for item in payload["allocations"])
    assert all(item["learning_scale_hours"] == 2.8 for item in payload["allocations"])
    assert payload["calibrated_learning_topic_count"] == 0
    assert payload["scenarios"]
    assert payload["assumptions"]


def test_study_plan_accepts_topic_mastery_overrides(client: TestClient) -> None:
    course_id = _prepare_course(client)
    intelligence = client.get(f"/api/v1/courses/{course_id}/intelligence").json()
    strongest_topic = intelligence["topics"][0]

    response = client.post(
        f"/api/v1/courses/{course_id}/study-plan",
        json={
            "baseline_mastery": 0.3,
            "available_hours": 8,
            "topic_mastery": {strongest_topic["id"]: 0.95},
        },
    )

    assert response.status_code == 200
    allocations = {item["topic_id"]: item for item in response.json()["allocations"]}
    if strongest_topic["id"] in allocations:
        assert allocations[strongest_topic["id"]]["current_mastery"] == 0.95
        assert allocations[strongest_topic["id"]]["mastery_source"] == "override"


def test_exam_analysis_requires_course_topics(client: TestClient) -> None:
    course_id = _create_course(client)
    _upload_and_process(
        client,
        course_id,
        "2025-written-exam.txt",
        b"Written Exam\nQuestion 1 (10 marks)\nCalculate momentum.",
    )

    response = client.post(f"/api/v1/courses/{course_id}/exam-intelligence/analyze")

    assert response.status_code == 409


def test_study_plan_requires_course_analysis(client: TestClient) -> None:
    course_id = _create_course(client)

    response = client.post(
        f"/api/v1/courses/{course_id}/study-plan",
        json={"baseline_mastery": 0.5},
    )

    assert response.status_code == 409
