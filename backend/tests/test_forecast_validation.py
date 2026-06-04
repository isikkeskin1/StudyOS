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


def _snapshot(
    client: TestClient,
    course_id: str,
    index: int,
    *,
    apply_recalibration: bool = False,
) -> dict:
    response = client.post(
        f"/api/v1/courses/{course_id}/forecast-snapshots",
        json={
            "label": f"Exam {index}",
            "apply_recalibration": apply_recalibration,
            "forecast": {
                "study_hours": 8,
                "target_grade": 25,
                "thresholds": [18, 25],
            },
        },
    )
    assert response.status_code == 201
    return response.json()


def _record_biased_pair(client: TestClient, course_id: str, index: int) -> dict:
    snapshot = _snapshot(client, course_id, index)
    actual = max(0.0, snapshot["expected_grade"] - 2.0)
    response = client.post(
        f"/api/v1/courses/{course_id}/forecast-snapshots/{snapshot['id']}/outcome",
        json={"actual_grade": actual},
    )
    assert response.status_code == 201
    return snapshot


def test_validation_is_empty_before_any_outcomes(client: TestClient) -> None:
    course_id = _prepare_course(client)

    response = client.get(f"/api/v1/courses/{course_id}/forecast-validation")

    assert response.status_code == 200
    payload = response.json()
    assert payload["completed_pair_count"] == 0
    assert payload["held_out_count"] == 0
    assert payload["validation_status"] == "insufficient_data"
    assert payload["verdict"] == "insufficient_data"
    assert len(payload["raw_reliability"]) == 5
    assert sum(bucket["count"] for bucket in payload["raw_reliability"]) == 0


def test_five_training_outcomes_do_not_create_a_held_out_claim(client: TestClient) -> None:
    course_id = _prepare_course(client)
    for index in range(1, 6):
        _record_biased_pair(client, course_id, index)

    payload = client.get(f"/api/v1/courses/{course_id}/forecast-validation").json()

    assert payload["completed_pair_count"] == 5
    assert payload["held_out_count"] == 0
    assert payload["raw_metrics"]["count"] == 0
    assert payload["recalibrated_metrics"]["count"] == 0


def test_rolling_validation_uses_only_prior_recorded_outcomes(client: TestClient) -> None:
    course_id = _prepare_course(client)
    for index in range(1, 9):
        _record_biased_pair(client, course_id, index)

    response = client.get(f"/api/v1/courses/{course_id}/forecast-validation")

    assert response.status_code == 200
    payload = response.json()
    assert payload["completed_pair_count"] == 8
    assert payload["held_out_count"] == 3
    assert payload["validation_status"] == "preliminary"
    assert [
        row["training_outcome_count"] for row in payload["held_out_forecasts"]
    ] == [5, 6, 7]
    assert payload["raw_metrics"]["mean_absolute_error"] == 2.0
    assert payload["recalibrated_metrics"]["mean_absolute_error"] < 2.0
    assert payload["deltas"]["mean_absolute_error"] < 0
    assert sum(bucket["count"] for bucket in payload["raw_reliability"]) == 8
    assert sum(
        bucket["count"] for bucket in payload["held_out_raw_reliability"]
    ) == 3
    assert sum(
        bucket["count"] for bucket in payload["held_out_recalibrated_reliability"]
    ) == 3


def test_validation_reads_raw_values_from_adjusted_snapshot_artifact(
    client: TestClient,
) -> None:
    course_id = _prepare_course(client)
    for index in range(1, 6):
        _record_biased_pair(client, course_id, index)

    adjusted = _snapshot(client, course_id, 6, apply_recalibration=True)
    artifact = adjusted["recalibration_artifact"]
    assert artifact is not None
    assert artifact["recalibration"]["active"] is True
    actual = max(0.0, artifact["raw_expected_grade"] - 2.0)
    outcome = client.post(
        f"/api/v1/courses/{course_id}/forecast-snapshots/{adjusted['id']}/outcome",
        json={"actual_grade": actual},
    )
    assert outcome.status_code == 201

    payload = client.get(f"/api/v1/courses/{course_id}/forecast-validation").json()

    assert payload["held_out_count"] == 1
    held_out = payload["held_out_forecasts"][0]
    assert held_out["forecast_snapshot_id"] == adjusted["id"]
    assert held_out["raw_expected_grade"] == artifact["raw_expected_grade"]
    assert held_out["recalibrated_expected_grade"] == adjusted["expected_grade"]
