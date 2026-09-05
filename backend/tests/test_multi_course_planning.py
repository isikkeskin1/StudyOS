from __future__ import annotations

from fastapi.testclient import TestClient
from sqlalchemy import select

from app.models.course_intelligence import CourseTopic
from app.models.diagnostics import TopicMastery


def _create_course(
    client: TestClient,
    *,
    name: str,
    target_grade: float,
    max_grade: float,
) -> str:
    response = client.post(
        "/api/v1/courses",
        json={
            "name": name,
            "target_grade": target_grade,
            "max_grade": max_grade,
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
    processed = client.post(f"/api/v1/courses/{course_id}/documents/{document_id}/process")
    assert processed.status_code == 200


def _prepare_course(
    client: TestClient,
    *,
    name: str,
    target_grade: float,
    max_grade: float,
) -> str:
    course_id = _create_course(
        client,
        name=name,
        target_grade=target_grade,
        max_grade=max_grade,
    )
    _upload_and_process(
        client,
        course_id,
        f"{name}-lecture.txt",
        (
            b"Newton's Laws\n"
            b"Force mass acceleration dynamics free body diagrams Newton second law.\n\n"
            b"Momentum\n"
            b"Momentum conservation collisions impulse vector momentum.\n\n"
            b"Oscillations\n"
            b"Simple harmonic motion period frequency spring amplitude oscillation."
        ),
    )
    _upload_and_process(
        client,
        course_id,
        f"{name}-exam.txt",
        (
            b"Written Exam\n"
            b"Question 1 (12 marks)\n"
            b"Use conservation of momentum and impulse to solve the collision.\n\n"
            b"Question 2 (8 marks)\n"
            b"Use Newton's second law to find force and acceleration.\n\n"
            b"Question 3 (2 marks)\n"
            b"State the period relation for a simple harmonic oscillator."
        ),
    )
    assert client.post(f"/api/v1/courses/{course_id}/analyze").status_code == 200
    assert (
        client.post(f"/api/v1/courses/{course_id}/exam-intelligence/analyze").status_code
        == 200
    )
    return course_id


def _plan(client: TestClient, *, available_hours: float, courses: list[dict]) -> dict:
    response = client.post(
        "/api/v1/multi-course-plan",
        json={
            "available_hours": available_hours,
            "block_minutes": 30,
            "courses": courses,
        },
    )
    assert response.status_code == 200
    return response.json()


def _course(body: dict, course_id: str) -> dict:
    return next(item for item in body["courses"] if item["course_id"] == course_id)


def test_multi_course_plan_normalizes_different_grade_scales(client: TestClient) -> None:
    physics = _prepare_course(
        client,
        name="Physics 30",
        target_grade=24,
        max_grade=30,
    )
    programming = _prepare_course(
        client,
        name="Programming 100",
        target_grade=80,
        max_grade=100,
    )

    body = _plan(
        client,
        available_hours=1,
        courses=[
            {"course_id": physics, "baseline_mastery": 0.4},
            {"course_id": programming, "baseline_mastery": 0.4},
        ],
    )

    assert body["optimization_model"] == "normalized-target-utility-greedy-v1"
    physics_row = _course(body, physics)
    programming_row = _course(body, programming)
    assert (
        programming_row["initial_best_block_expected_mark_gain"]
        > physics_row["initial_best_block_expected_mark_gain"] * 3
    )
    assert abs(
        programming_row["initial_best_block_normalized_target_reduction"]
        - physics_row["initial_best_block_normalized_target_reduction"]
    ) < 1e-4
    assert abs(
        programming_row["initial_utility_per_hour"]
        - physics_row["initial_utility_per_hour"]
    ) < 1e-4
    assert body["total_normalized_target_gap_after"] < body["total_normalized_target_gap_before"]


def test_multi_course_plan_prioritizes_nearer_exact_deadline(client: TestClient) -> None:
    relaxed = _prepare_course(
        client,
        name="Relaxed Physics",
        target_grade=25,
        max_grade=30,
    )
    urgent = _prepare_course(
        client,
        name="Urgent Physics",
        target_grade=25,
        max_grade=30,
    )

    body = _plan(
        client,
        available_hours=0.5,
        courses=[
            {
                "course_id": relaxed,
                "baseline_mastery": 0.4,
                "hours_until_exam": 72,
            },
            {
                "course_id": urgent,
                "baseline_mastery": 0.4,
                "hours_until_exam": 6,
            },
        ],
    )

    assert body["schedule"][0]["course_id"] == urgent
    assert _course(body, urgent)["initial_deadline_multiplier"] > _course(
        body, relaxed
    )["initial_deadline_multiplier"]


def test_multi_course_plan_stops_allocating_to_course_after_target_is_reached(
    client: TestClient,
) -> None:
    already_safe = _prepare_course(
        client,
        name="Already Safe",
        target_grade=20,
        max_grade=30,
    )
    needs_work = _prepare_course(
        client,
        name="Needs Work",
        target_grade=25,
        max_grade=30,
    )

    body = _plan(
        client,
        available_hours=1,
        courses=[
            {"course_id": already_safe, "baseline_mastery": 0.9},
            {"course_id": needs_work, "baseline_mastery": 0.4},
        ],
    )

    safe_row = _course(body, already_safe)
    assert safe_row["target_reached"] is True
    assert safe_row["allocated_hours"] == 0
    assert all(block["course_id"] == needs_work for block in body["schedule"])


def test_multi_course_plan_respects_exact_deadline_as_hard_cutoff(client: TestClient) -> None:
    expiring = _prepare_course(
        client,
        name="Exam Very Soon",
        target_grade=28,
        max_grade=30,
    )
    later = _prepare_course(
        client,
        name="Later Exam",
        target_grade=28,
        max_grade=30,
    )

    body = _plan(
        client,
        available_hours=2,
        courses=[
            {
                "course_id": later,
                "baseline_mastery": 0.3,
                "hours_until_exam": 48,
            },
            {
                "course_id": expiring,
                "baseline_mastery": 0.3,
                "hours_until_exam": 0.5,
            },
        ],
    )

    expiring_blocks = [block for block in body["schedule"] if block["course_id"] == expiring]
    assert len(expiring_blocks) <= 1
    assert _course(body, expiring)["allocated_hours"] <= 0.5
    if expiring_blocks:
        assert expiring_blocks[0]["sequence"] == 1


def test_multi_course_plan_reconsiders_courses_after_each_block(client: TestClient) -> None:
    first = _prepare_course(
        client,
        name="Course A",
        target_grade=29,
        max_grade=30,
    )
    second = _prepare_course(
        client,
        name="Course B",
        target_grade=29,
        max_grade=30,
    )

    body = _plan(
        client,
        available_hours=4,
        courses=[
            {"course_id": first, "baseline_mastery": 0.25},
            {"course_id": second, "baseline_mastery": 0.25},
        ],
    )

    assert _course(body, first)["allocated_hours"] > 0
    assert _course(body, second)["allocated_hours"] > 0
    assert len({block["course_id"] for block in body["schedule"]}) == 2


def test_multi_course_plan_conservatively_shrinks_low_confidence_gain(
    client: TestClient,
) -> None:
    low_confidence = _prepare_course(
        client,
        name="Low Confidence",
        target_grade=25,
        max_grade=30,
    )
    measured = _prepare_course(
        client,
        name="Measured",
        target_grade=25,
        max_grade=30,
    )

    with client.app.state.session_factory() as db:
        topics = list(
            db.scalars(
                select(CourseTopic).where(CourseTopic.course_id == measured)
            ).all()
        )
        for topic in topics:
            db.add(
                TopicMastery(
                    course_id=measured,
                    topic_id=topic.id,
                    mastery=0.4,
                    confidence=0.9,
                    evidence_weight=5.0,
                    response_count=5,
                )
            )
        db.commit()

    body = _plan(
        client,
        available_hours=0.5,
        courses=[
            {"course_id": low_confidence, "baseline_mastery": 0.4},
            {"course_id": measured, "baseline_mastery": 0.4},
        ],
    )

    low_row = _course(body, low_confidence)
    measured_row = _course(body, measured)
    assert low_row["plan_confidence"] == "low"
    assert measured_row["plan_confidence"] == "medium"
    assert measured_row["confidence_multiplier"] > low_row["confidence_multiplier"]
    assert body["schedule"][0]["course_id"] == measured


def test_multi_course_plan_validates_duplicates_and_missing_courses(client: TestClient) -> None:
    course_id = _prepare_course(
        client,
        name="Physics",
        target_grade=25,
        max_grade=30,
    )

    duplicate = client.post(
        "/api/v1/multi-course-plan",
        json={
            "available_hours": 1,
            "courses": [
                {"course_id": course_id},
                {"course_id": course_id},
            ],
        },
    )
    assert duplicate.status_code == 422

    missing = client.post(
        "/api/v1/multi-course-plan",
        json={
            "available_hours": 1,
            "courses": [{"course_id": "missing-course"}],
        },
    )
    assert missing.status_code == 404


def test_multi_course_plan_leaves_time_unallocated_when_all_targets_are_reached(
    client: TestClient,
) -> None:
    first = _prepare_course(
        client,
        name="Safe A",
        target_grade=18,
        max_grade=30,
    )
    second = _prepare_course(
        client,
        name="Safe B",
        target_grade=60,
        max_grade=100,
    )

    body = _plan(
        client,
        available_hours=3,
        courses=[
            {"course_id": first, "baseline_mastery": 0.9},
            {"course_id": second, "baseline_mastery": 0.9},
        ],
    )

    assert body["allocated_hours"] == 0
    assert body["unallocated_hours"] == 3
    assert body["schedule"] == []
    assert body["next_action"] is None
    assert all(course["target_reached"] for course in body["courses"])
