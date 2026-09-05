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
            b"Momentum is conserved in collisions. Momentum equals mass times velocity. "
            b"Momentum is a vector quantity."
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
    course_analysis = client.post(f"/api/v1/courses/{course_id}/analyze")
    assert course_analysis.status_code == 200
    exam_analysis = client.post(f"/api/v1/courses/{course_id}/exam-intelligence/analyze")
    assert exam_analysis.status_code == 200
    return course_id


def test_solution_text_is_hidden_and_automatic_grading_is_available(
    client: TestClient,
) -> None:
    course_id = _prepare_solution_course(client)
    intelligence = client.get(f"/api/v1/courses/{course_id}/exam-intelligence")
    assert intelligence.status_code == 200
    first_exam_question = intelligence.json()["questions"][0]
    assert first_exam_question["automatic_grading_available"] is True
    assert "10 N" not in first_exam_question["text"]
    assert "Solution" not in first_exam_question["text"]

    start = client.post(
        f"/api/v1/courses/{course_id}/diagnostics",
        json={"question_count": 1},
    )
    assert start.status_code == 201
    session_id = start.json()["id"]
    next_question = client.get(
        f"/api/v1/courses/{course_id}/diagnostics/{session_id}/next"
    )
    assert next_question.status_code == 200
    question = next_question.json()["question"]
    assert question["automatic_grading_available"] is True
    assert "10 N" not in question["text"]


def test_automatic_grading_records_solution_feedback_and_mastery(
    client: TestClient,
) -> None:
    course_id = _prepare_solution_course(client)
    start = client.post(
        f"/api/v1/courses/{course_id}/diagnostics",
        json={"question_count": 1},
    )
    session_id = start.json()["id"]
    question = client.get(
        f"/api/v1/courses/{course_id}/diagnostics/{session_id}/next"
    ).json()["question"]

    graded = client.post(
        f"/api/v1/courses/{course_id}/diagnostics/{session_id}/grade",
        json={
            "diagnostic_question_id": question["id"],
            "student_answer": (
                "Newton's second law says force equals mass times acceleration. "
                "The force is 10 N."
            ),
            "confidence": 0.8,
            "duration_seconds": 150,
        },
    )

    assert graded.status_code == 200
    payload = graded.json()
    assert payload["grading_source"] == "automatic"
    assert payload["score"] >= 0.8
    assert payload["grading"]["grader_name"] == "deterministic-solution-v1"
    assert payload["grading"]["grader_confidence"] < 0.8
    assert payload["answer"]["reference_answer"]
    assert "provisional" in payload["answer"]["feedback"]
    assert payload["mastery"]


def test_weak_automatic_answer_creates_mistake_evidence(client: TestClient) -> None:
    course_id = _prepare_solution_course(client)
    start = client.post(
        f"/api/v1/courses/{course_id}/diagnostics",
        json={"question_count": 1},
    )
    session_id = start.json()["id"]
    question = client.get(
        f"/api/v1/courses/{course_id}/diagnostics/{session_id}/next"
    ).json()["question"]

    graded = client.post(
        f"/api/v1/courses/{course_id}/diagnostics/{session_id}/grade",
        json={
            "diagnostic_question_id": question["id"],
            "student_answer": "Velocity probably stays unchanged.",
        },
    )
    assert graded.status_code == 200
    payload = graded.json()
    assert payload["score"] < 0.5
    categories = {item["category"] for item in payload["mistakes"]}
    assert "concept" in categories or "incomplete_reasoning" in categories

    summary = client.get(f"/api/v1/courses/{course_id}/mistakes")
    assert summary.status_code == 200
    assert summary.json()["responses_with_mistakes"] == 1
    assert summary.json()["classification_coverage"] > 0


def test_automatic_grading_requires_extracted_reference_solution(
    client: TestClient,
) -> None:
    course_id = _create_course(client)
    _upload_and_process(
        client,
        course_id,
        "lecture-momentum.txt",
        b"Momentum\nMomentum is conserved. Momentum equals mass times velocity. Momentum is vector.",
    )
    _upload_and_process(
        client,
        course_id,
        "2025-written-exam.txt",
        b"Physics I Written Exam\nQuestion 1 (10 marks)\nCalculate momentum using mass and velocity.",
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
    assert question["automatic_grading_available"] is False

    graded = client.post(
        f"/api/v1/courses/{course_id}/diagnostics/{session_id}/grade",
        json={
            "diagnostic_question_id": question["id"],
            "student_answer": "Momentum is mass times velocity.",
        },
    )
    assert graded.status_code == 409
