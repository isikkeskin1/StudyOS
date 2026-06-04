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
                "mechanics.txt",
                b"Momentum\nMomentum is conserved.\nForce\nNewton's second law is F = ma.",
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
                    b"Question 1 (15 marks)\nUse momentum conservation.\n\n"
                    b"Question 2 (15 marks)\nUse Newton's second law."
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


def _snapshot(client: TestClient, course_id: str, label: str = "Midterm") -> dict:
    response = client.post(
        f"/api/v1/courses/{course_id}/forecast-snapshots",
        json={
            "label": label,
            "exam_date": "2026-09-12",
            "forecast": {
                "study_hours": 8,
                "target_grade": 25,
                "thresholds": [18, 25],
            },
        },
    )
    assert response.status_code == 201
    return response.json()


def test_forecast_snapshot_is_persisted_with_original_prediction(client: TestClient) -> None:
    course_id = _prepare_course(client)
    snapshot = _snapshot(client, course_id)

    listing = client.get(f"/api/v1/courses/{course_id}/forecast-snapshots")

    assert listing.status_code == 200
    rows = listing.json()
    assert len(rows) == 1
    assert rows[0]["id"] == snapshot["id"]
    assert rows[0]["label"] == "Midterm"
    assert rows[0]["forecast_model"] == "probabilistic-v1"
    assert rows[0]["target_probability"] == snapshot["target_probability"]
    assert rows[0]["thresholds"] == snapshot["thresholds"]
    assert rows[0]["outcome"] is None


def test_recorded_outcome_produces_descriptive_calibration_metrics(
    client: TestClient,
) -> None:
    course_id = _prepare_course(client)
    snapshot = _snapshot(client, course_id)
    actual_grade = min(30.0, snapshot["expected_grade"] + 1.0)

    outcome = client.post(
        f"/api/v1/courses/{course_id}/forecast-snapshots/{snapshot['id']}/outcome",
        json={"actual_grade": actual_grade, "occurred_at": "2026-09-12"},
    )
    assert outcome.status_code == 201
    assert outcome.json()["outcome"]["actual_grade"] == actual_grade

    calibration = client.get(f"/api/v1/courses/{course_id}/forecast-calibration")
    assert calibration.status_code == 200
    payload = calibration.json()
    assert payload["paired_forecast_count"] == 1
    assert payload["calibration_status"] == "insufficient_data"
    assert payload["mean_absolute_error"] == 1.0
    assert payload["root_mean_squared_error"] == 1.0
    assert payload["brier_score"] is not None
    assert payload["log_loss"] is not None
    assert payload["uncertainty_direction"] == "insufficient_data"
    assert len(payload["evaluations"]) == 1


def test_duplicate_outcome_is_rejected(client: TestClient) -> None:
    course_id = _prepare_course(client)
    snapshot = _snapshot(client, course_id)
    endpoint = (
        f"/api/v1/courses/{course_id}/forecast-snapshots/{snapshot['id']}/outcome"
    )

    assert client.post(endpoint, json={"actual_grade": 24}).status_code == 201
    duplicate = client.post(endpoint, json={"actual_grade": 25})

    assert duplicate.status_code == 409


def test_outcome_above_saved_score_maximum_is_rejected(client: TestClient) -> None:
    course_id = _prepare_course(client)
    snapshot = _snapshot(client, course_id)

    response = client.post(
        f"/api/v1/courses/{course_id}/forecast-snapshots/{snapshot['id']}/outcome",
        json={"actual_grade": 31},
    )

    assert response.status_code == 409


def test_three_completed_forecasts_enable_preliminary_uncertainty_diagnostic(
    client: TestClient,
) -> None:
    course_id = _prepare_course(client)
    for index in range(3):
        snapshot = _snapshot(client, course_id, label=f"Exam {index + 1}")
        actual = snapshot["expected_grade"]
        response = client.post(
            f"/api/v1/courses/{course_id}/forecast-snapshots/{snapshot['id']}/outcome",
            json={"actual_grade": actual},
        )
        assert response.status_code == 201

    calibration = client.get(f"/api/v1/courses/{course_id}/forecast-calibration").json()

    assert calibration["paired_forecast_count"] == 3
    assert calibration["calibration_status"] == "preliminary"
    assert calibration["mean_absolute_error"] == 0.0
    assert calibration["interval_coverage"] == 1.0
    assert calibration["uncertainty_direction"] == "narrow"
