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
    processed = client.post(f"/api/v1/courses/{course_id}/documents/{document_id}/process")
    assert processed.status_code == 200


def _prepare_course(client: TestClient) -> str:
    course_id = _create_course(client)
    _upload_and_process(
        client,
        course_id,
        "lecture-mechanics.txt",
        (
            b"Newton's Laws\n"
            b"Force mass acceleration dynamics Newton second law. "
            b"Free body diagrams resolve forces before acceleration.\n\n"
            b"Momentum\n"
            b"Momentum conservation collisions impulse momentum vector. "
            b"Impulse changes momentum during collisions.\n\n"
            b"Oscillations\n"
            b"Simple harmonic motion period frequency spring oscillation amplitude."
        ),
    )
    _upload_and_process(
        client,
        course_id,
        "2026-written-exam.txt",
        (
            b"Physics I Written Exam\n"
            b"Question 1 (12 marks)\n"
            b"Use conservation of momentum and impulse to solve the collision.\n\n"
            b"Question 2 (8 marks)\n"
            b"Use Newton's second law to find force and acceleration.\n\n"
            b"Question 3 (2 marks)\n"
            b"State the period relation for a simple harmonic oscillator."
        ),
    )
    analyzed = client.post(f"/api/v1/courses/{course_id}/analyze")
    assert analyzed.status_code == 200
    exams = client.post(f"/api/v1/courses/{course_id}/exam-intelligence/analyze")
    assert exams.status_code == 200
    return course_id


def test_emergency_plan_exposes_expected_marks_and_ordered_schedule(client: TestClient) -> None:
    course_id = _prepare_course(client)
    response = client.post(
        f"/api/v1/courses/{course_id}/emergency-plan",
        json={
            "available_hours": 4,
            "hours_until_exam": 10,
            "block_minutes": 30,
            "baseline_mastery": 0.5,
        },
    )

    assert response.status_code == 200
    body = response.json()
    assert body["optimization_model"] == "expected-marks-greedy-v1"
    assert body["urgency"] == "critical"
    assert body["current_estimated_grade"] == 15
    assert body["projected_grade"] > body["current_estimated_grade"]
    assert body["expected_mark_gain"] > 0
    assert abs(
        body["expected_mark_gain"]
        - (body["projected_grade"] - body["current_estimated_grade"])
    ) < 0.02
    assert sum(block["duration_minutes"] for block in body["schedule"]) == 240
    assert body["next_action"]["topic_id"] == body["schedule"][0]["topic_id"]
    assert all(block["expected_marks_per_hour"] > 0 for block in body["schedule"])
    assert body["topics"]
    assert any(topic["decision"] == "study" for topic in body["topics"])


def test_emergency_plan_uses_diminishing_returns_across_topics(client: TestClient) -> None:
    course_id = _prepare_course(client)
    response = client.post(
        f"/api/v1/courses/{course_id}/emergency-plan",
        json={"available_hours": 12, "block_minutes": 30, "baseline_mastery": 0.35},
    )

    assert response.status_code == 200
    studied = [topic for topic in response.json()["topics"] if topic["allocated_hours"] > 0]
    assert len(studied) >= 2
    assert all(topic["expected_mark_gain"] > 0 for topic in studied)
    assert all(
        topic["post_plan_marginal_marks_per_hour"] <= topic["initial_marks_per_hour"] + 1e-3
        for topic in studied
    )


def test_emergency_plan_surfaces_skip_decisions_for_low_return_topics(client: TestClient) -> None:
    course_id = _prepare_course(client)
    response = client.post(
        f"/api/v1/courses/{course_id}/emergency-plan",
        json={
            "available_hours": 0.5,
            "block_minutes": 30,
            "baseline_mastery": 0.5,
            "skip_threshold_marks_per_hour": 0.5,
        },
    )

    assert response.status_code == 200
    body = response.json()
    skipped = [topic for topic in body["topics"] if topic["decision"] == "skip"]
    assert skipped
    assert all(topic["allocated_hours"] == 0 for topic in skipped)
    assert all(
        topic["initial_marks_per_hour"] < body["emergency_skip_cutoff_marks_per_hour"] + 1e-3
        for topic in skipped
    )


def test_emergency_plan_reports_target_already_reached(client: TestClient) -> None:
    course_id = _prepare_course(client)
    response = client.post(
        f"/api/v1/courses/{course_id}/emergency-plan",
        json={"available_hours": 1, "target_grade": 14, "baseline_mastery": 0.5},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["estimated_hours_to_target"] == 0
    assert body["target_gap_before"] == 0
    assert body["target_reachable_with_available_time"] is True


def test_emergency_plan_validates_clock_time_and_requires_course_analysis(
    client: TestClient,
) -> None:
    course_id = _create_course(client)

    invalid = client.post(
        f"/api/v1/courses/{course_id}/emergency-plan",
        json={"available_hours": 6, "hours_until_exam": 4},
    )
    assert invalid.status_code == 422

    unavailable = client.post(
        f"/api/v1/courses/{course_id}/emergency-plan",
        json={"available_hours": 2},
    )
    assert unavailable.status_code == 409
