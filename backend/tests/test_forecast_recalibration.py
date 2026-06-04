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


def _record_biased_outcome(client: TestClient, course_id: str, index: int) -> dict:
    snapshot_response = client.post(
        f"/api/v1/courses/{course_id}/forecast-snapshots",
        json={
            "label": f"Training exam {index}",
            "apply_recalibration": False,
            "forecast": {"study_hours": 8, "target_grade": 25},
        },
    )
    assert snapshot_response.status_code == 201
    snapshot = snapshot_response.json()
    actual = max(0.0, snapshot["expected_grade"] - 3.0)
    outcome = client.post(
        f"/api/v1/courses/{course_id}/forecast-snapshots/{snapshot['id']}/outcome",
        json={"actual_grade": actual},
    )
    assert outcome.status_code == 201
    return snapshot


def test_calibrated_forecast_is_unchanged_before_activation(client: TestClient) -> None:
    course_id = _prepare_course(client)

    response = client.post(
        f"/api/v1/courses/{course_id}/grade-forecast/calibrated",
        json={"study_hours": 8, "target_grade": 25, "thresholds": [18, 25]},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["recalibration"]["active"] is False
    assert payload["recalibration"]["paired_outcome_count"] == 0
    assert payload["expected_grade"] == payload["raw_forecast"]["expected_grade"]
    assert payload["standard_deviation"] == payload["raw_forecast"]["standard_deviation"]
    assert payload["target_probability"] == payload["raw_forecast"]["target_probability"]


def test_five_outcomes_activate_confidence_shrunk_bias_correction(
    client: TestClient,
) -> None:
    course_id = _prepare_course(client)
    for index in range(5):
        _record_biased_outcome(client, course_id, index)

    response = client.post(
        f"/api/v1/courses/{course_id}/grade-forecast/calibrated",
        json={"study_hours": 8, "target_grade": 25},
    )

    assert response.status_code == 200
    payload = response.json()
    recalibration = payload["recalibration"]
    assert recalibration["active"] is True
    assert recalibration["calibration_status"] == "guarded"
    assert recalibration["paired_outcome_count"] == 5
    assert 0 < recalibration["shrinkage_weight"] < 1
    assert recalibration["raw_bias_marks"] < 0
    assert recalibration["applied_bias_marks"] < 0
    assert abs(recalibration["applied_bias_marks"]) < abs(recalibration["raw_bias_marks"])
    assert payload["expected_grade"] < payload["raw_forecast"]["expected_grade"]


def test_recalibrated_snapshot_preserves_raw_forecast_artifact(client: TestClient) -> None:
    course_id = _prepare_course(client)
    for index in range(5):
        _record_biased_outcome(client, course_id, index)

    response = client.post(
        f"/api/v1/courses/{course_id}/forecast-snapshots",
        json={
            "label": "Adjusted final",
            "apply_recalibration": True,
            "forecast": {"study_hours": 8, "target_grade": 25, "thresholds": [18, 25]},
        },
    )

    assert response.status_code == 201
    payload = response.json()
    artifact = payload["recalibration_artifact"]
    assert artifact is not None
    assert artifact["recalibration"]["active"] is True
    assert artifact["raw_forecast_model"] == "probabilistic-v1"
    assert artifact["raw_expected_grade"] > payload["expected_grade"]
    assert artifact["raw_thresholds"]

    listing = client.get(f"/api/v1/courses/{course_id}/forecast-snapshots").json()
    adjusted = next(item for item in listing if item["id"] == payload["id"])
    assert adjusted["recalibration_artifact"] == artifact


def test_calibration_endpoint_exposes_current_empirical_adjustment(client: TestClient) -> None:
    course_id = _prepare_course(client)
    for index in range(5):
        _record_biased_outcome(client, course_id, index)

    response = client.get(f"/api/v1/courses/{course_id}/forecast-calibration")

    assert response.status_code == 200
    payload = response.json()
    recalibration = payload["empirical_recalibration"]
    assert payload["paired_forecast_count"] == 5
    assert recalibration["active"] is True
    assert recalibration["paired_outcome_count"] == 5
    assert recalibration["applied_bias_marks"] < 0
