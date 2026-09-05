from __future__ import annotations

from datetime import UTC, datetime, timedelta
from uuid import uuid4

from fastapi.testclient import TestClient

from app.models.calendar_focus import FocusSession
from app.models.course_intelligence import CourseTopic
from app.models.diagnostics import TopicMastery
from app.models.forecast_tracking import GradeForecastSnapshot
from app.models.semester_queue import SemesterStudyQueue, SemesterStudyQueueBlock
from app.models.tutor_practice import (
    TutorPracticeAttempt,
    TutorPracticeItem,
    TutorPracticeMistake,
)


def _create_course(client: TestClient, name: str = "Physics") -> str:
    response = client.post(
        "/api/v1/courses",
        json={"name": name, "target_grade": 24, "max_grade": 30},
    )
    assert response.status_code == 201
    return response.json()["id"]


def _forecast(course_id: str, expected: float, probability: float, created_at: datetime):
    return GradeForecastSnapshot(
        course_id=course_id,
        label=None,
        exam_date=None,
        forecast_model="probabilistic-v1",
        probability_status="estimated",
        max_grade=30,
        study_hours=2,
        target_grade=24,
        expected_grade=expected,
        standard_deviation=2,
        interval_probability=0.8,
        likely_range_low=max(0, expected - 3),
        likely_range_high=min(30, expected + 3),
        target_probability=probability,
        evidence_quality=0.8,
        evidence_confidence="high",
        request_payload="{}",
        thresholds_payload="{}",
        assumptions_payload="[]",
        created_at=created_at,
    )


def _seed_analytics(client: TestClient, course_id: str) -> None:
    now = datetime.now(UTC)
    with client.app.state.session_factory() as db:
        topic = CourseTopic(
            course_id=course_id,
            name="Mechanics",
            normalized_name="mechanics",
            importance_score=0.9,
            mention_count=10,
            document_count=2,
            exam_mention_count=4,
            lecture_mention_count=6,
        )
        db.add(topic)
        db.flush()
        db.add(
            TopicMastery(
                course_id=course_id,
                topic_id=topic.id,
                mastery=0.5,
                confidence=0.8,
                evidence_weight=2,
                response_count=2,
                updated_at=now,
            )
        )

        queue = SemesterStudyQueue(
            status="active",
            initial_available_minutes=60,
            remaining_available_minutes=35,
            lost_minutes=0,
            block_minutes=30,
            course_configs=[],
            current_revision=1,
            created_at=now - timedelta(hours=1),
            updated_at=now,
        )
        db.add(queue)
        db.flush()
        completed_block = SemesterStudyQueueBlock(
            queue_id=queue.id,
            course_id=course_id,
            course_name="Physics",
            topic_id=topic.id,
            topic_name="Mechanics",
            revision=1,
            sequence=1,
            status="completed",
            planned_minutes=30,
            actual_minutes=25,
            expected_mark_gain=2,
            normalized_target_gap_reduction=0.05,
            utility_score=0.05,
            created_at=now - timedelta(hours=1),
            started_at=now - timedelta(minutes=30),
            completed_at=now - timedelta(minutes=5),
        )
        skipped_block = SemesterStudyQueueBlock(
            queue_id=queue.id,
            course_id=course_id,
            course_name="Physics",
            topic_id=topic.id,
            topic_name="Mechanics",
            revision=1,
            sequence=2,
            status="skipped",
            planned_minutes=30,
            actual_minutes=0,
            expected_mark_gain=2,
            normalized_target_gap_reduction=0.05,
            utility_score=0.05,
            created_at=now - timedelta(hours=1),
            completed_at=now - timedelta(minutes=2),
        )
        db.add_all([completed_block, skipped_block])
        db.flush()
        db.add_all(
            [
                FocusSession(
                    queue_id=queue.id,
                    block_id=completed_block.id,
                    queue_revision=1,
                    status="completed",
                    active_key=None,
                    planned_minutes=30,
                    started_at=now - timedelta(minutes=30),
                    target_end_at=now,
                    completed_at=now - timedelta(minutes=5),
                    actual_minutes=25,
                    note=None,
                ),
                FocusSession(
                    queue_id=queue.id,
                    block_id=skipped_block.id,
                    queue_revision=1,
                    status="skipped",
                    active_key=None,
                    planned_minutes=30,
                    started_at=now - timedelta(minutes=3),
                    target_end_at=now + timedelta(minutes=27),
                    completed_at=now - timedelta(minutes=2),
                    actual_minutes=0,
                    note="Interrupted",
                ),
            ]
        )

        practice = TutorPracticeItem(
            id=str(uuid4()),
            course_id=course_id,
            topic_id=topic.id,
            topic_name="Mechanics",
            topic_selection="requested",
            difficulty="medium",
            marks=4,
            provider_requested="local",
            generation_provider="local",
            generation_mode="grounded",
            retrieval_model=None,
            question="State Newton's second law.",
            hints=[],
            solution="F = ma",
            hints_revealed=0,
            solution_revealed=False,
            created_at=now - timedelta(minutes=15),
        )
        old_practice = TutorPracticeItem(
            id=str(uuid4()),
            course_id=course_id,
            topic_id=topic.id,
            topic_name="Mechanics",
            topic_selection="requested",
            difficulty="medium",
            marks=4,
            provider_requested="local",
            generation_provider="local",
            generation_mode="grounded",
            retrieval_model=None,
            question="Old question",
            hints=[],
            solution="Old solution",
            hints_revealed=0,
            solution_revealed=False,
            created_at=now - timedelta(days=45),
        )
        db.add_all([practice, old_practice])
        db.flush()
        attempt = TutorPracticeAttempt(
            id=str(uuid4()),
            practice_id=practice.id,
            course_id=course_id,
            student_answer="Force equals mass times acceleration.",
            score=0.75,
            grader_name="local",
            grader_confidence=0.9,
            evidence_coverage=1,
            mastery_weight=1,
            hints_used=0,
            duration_seconds=90,
            feedback="Mostly correct",
            created_at=now - timedelta(minutes=10),
        )
        old_attempt = TutorPracticeAttempt(
            id=str(uuid4()),
            practice_id=old_practice.id,
            course_id=course_id,
            student_answer="Old answer",
            score=0.25,
            grader_name="local",
            grader_confidence=0.9,
            evidence_coverage=1,
            mastery_weight=1,
            hints_used=0,
            duration_seconds=90,
            feedback="Old feedback",
            created_at=now - timedelta(days=45),
        )
        db.add_all([attempt, old_attempt])
        db.flush()
        db.add(
            TutorPracticeMistake(
                attempt_id=attempt.id,
                category="conceptual",
                severity=1,
                source="grader",
                note="Missed direction",
            )
        )
        db.add_all(
            [
                _forecast(course_id, 18, 0.2, now - timedelta(days=10)),
                _forecast(course_id, 21, 0.45, now - timedelta(days=1)),
            ]
        )
        db.commit()


def test_analytics_empty_state(client: TestClient) -> None:
    response = client.get("/api/v1/analytics?days=7")
    assert response.status_code == 200
    body = response.json()
    assert body["window_days"] == 7
    assert body["summary"]["course_count"] == 0
    assert body["summary"]["focus_minutes"] == 0
    assert len(body["activity"]) == 7


def test_analytics_aggregates_persisted_learning_signals(client: TestClient) -> None:
    course_id = _create_course(client)
    _seed_analytics(client, course_id)

    response = client.get("/api/v1/analytics?days=30&timezone=Europe/Rome")
    assert response.status_code == 200
    body = response.json()
    assert body["timezone"] == "Europe/Rome"
    assert body["summary"]["course_count"] == 1
    assert body["summary"]["focus_minutes"] == 25
    assert body["summary"]["focus_sessions_completed"] == 1
    assert body["summary"]["focus_sessions_skipped"] == 1
    assert body["summary"]["focus_completion_rate"] == 0.5
    assert body["summary"]["answer_count"] == 1
    assert body["summary"]["average_answer_score"] == 0.75
    assert body["summary"]["forecast_snapshots"] == 2

    course = body["courses"][0]
    assert course["course_id"] == course_id
    assert course["target_status"] == "below_target"
    assert course["current_mean_mastery"] == 0.5
    assert course["focus_minutes"] == 25
    assert course["normalized_forecast_delta"] == 0.1
    assert course["latest_forecast_grade"] == 21
    assert course["latest_target_probability"] == 0.45
    assert course["top_mistakes"][0]["category"] == "conceptual"
    assert sum(day["focus_minutes"] for day in body["activity"]) == 25
    assert sum(day["practice_attempts"] for day in body["activity"]) == 1


def test_analytics_course_filter_and_window(client: TestClient) -> None:
    physics = _create_course(client, "Physics")
    chemistry = _create_course(client, "Chemistry")
    _seed_analytics(client, physics)

    response = client.get(f"/api/v1/analytics?days=30&course_id={physics}")
    assert response.status_code == 200
    body = response.json()
    assert body["course_filter"] == physics
    assert [course["course_id"] for course in body["courses"]] == [physics]
    assert body["summary"]["answer_count"] == 1

    chemistry_only = client.get(f"/api/v1/analytics?days=30&course_id={chemistry}")
    assert chemistry_only.status_code == 200
    assert chemistry_only.json()["summary"]["answer_count"] == 0


def test_analytics_rejects_unknown_course_and_timezone(client: TestClient) -> None:
    missing = client.get(f"/api/v1/analytics?course_id={uuid4()}")
    assert missing.status_code == 404

    invalid_timezone = client.get("/api/v1/analytics?timezone=Definitely/Not_A_Zone")
    assert invalid_timezone.status_code == 422
