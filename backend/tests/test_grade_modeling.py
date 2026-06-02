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
                "mechanics-lecture.txt",
                (
                    b"Momentum\nMomentum is conserved in isolated collisions. "
                    b"Impulse changes momentum and momentum is a vector.\n\n"
                    b"Force\nNewton's second law relates force, mass, and acceleration."
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
                "2025-mechanics-exam.txt",
                (
                    b"Physics I Written Exam\n"
                    b"Question 1 (10 marks)\n"
                    b"Use conservation of momentum to solve the collision.\n\n"
                    b"Question 2 (10 marks)\n"
                    b"Use Newton's second law to calculate the net force.\n\n"
                    b"Question 3 (10 marks)\n"
                    b"Calculate impulse and explain its relation to momentum."
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


def _answer_one(client: TestClient, course_id: str, score: float = 0.8) -> None:
    session = client.post(
        f"/api/v1/courses/{course_id}/diagnostics",
        json={"question_count": 1},
    )
    assert session.status_code == 201
    session_id = session.json()["id"]
    question = client.get(
        f"/api/v1/courses/{course_id}/diagnostics/{session_id}/next"
    ).json()["question"]
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


def test_grade_forecast_returns_ranges_and_monotonic_threshold_probabilities(
    client: TestClient,
) -> None:
    course_id = _prepare_course(client)

    response = client.post(
        f"/api/v1/courses/{course_id}/grade-forecast",
        json={"study_hours": 10, "thresholds": [18, 21, 25]},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["forecast_model"] == "probabilistic-v1"
    assert payload["probability_status"] == "provisional"
    assert payload["likely_range_low"] <= payload["expected_grade"]
    assert payload["expected_grade"] <= payload["likely_range_high"]
    assert payload["standard_deviation"] > 0
    probabilities = {
        item["grade"]: item["probability_at_or_above"]
        for item in payload["thresholds"]
    }
    assert probabilities[18.0] >= probabilities[21.0] >= probabilities[25.0]
    assert payload["target_probability"] == probabilities[25.0]
    assert payload["scenarios"]
    assert payload["assumptions"]


def test_more_study_increases_expected_grade_and_target_probability(
    client: TestClient,
) -> None:
    course_id = _prepare_course(client)

    current = client.post(
        f"/api/v1/courses/{course_id}/grade-forecast",
        json={"study_hours": 0},
    ).json()
    studied = client.post(
        f"/api/v1/courses/{course_id}/grade-forecast",
        json={"study_hours": 12},
    ).json()

    assert studied["expected_grade"] > current["expected_grade"]
    assert studied["target_probability"] > current["target_probability"]


def test_diagnostic_evidence_contracts_forecast_uncertainty(client: TestClient) -> None:
    course_id = _prepare_course(client)
    baseline = client.post(
        f"/api/v1/courses/{course_id}/grade-forecast",
        json={"study_hours": 0},
    ).json()

    _answer_one(client, course_id, 0.8)
    measured = client.post(
        f"/api/v1/courses/{course_id}/grade-forecast",
        json={"study_hours": 0},
    ).json()

    assert measured["evidence_quality"] > baseline["evidence_quality"]
    assert measured["standard_deviation"] < baseline["standard_deviation"]


def test_required_hours_for_probability_returns_sensitivity_band(client: TestClient) -> None:
    course_id = _prepare_course(client)

    response = client.post(
        f"/api/v1/courses/{course_id}/grade-forecast",
        json={
            "study_hours": 0,
            "target_grade": 18,
            "desired_probability": 0.8,
        },
    )

    assert response.status_code == 200
    required = response.json()["required_hours"]
    assert required["achievable_under_model"] is True
    assert required["estimated_hours"] is not None
    assert required["optimistic_hours"] <= required["estimated_hours"]
    assert required["estimated_hours"] <= required["conservative_hours"]


def test_forecast_rejects_threshold_above_course_maximum(client: TestClient) -> None:
    course_id = _prepare_course(client)

    response = client.post(
        f"/api/v1/courses/{course_id}/grade-forecast",
        json={"study_hours": 5, "thresholds": [31]},
    )

    assert response.status_code == 409
