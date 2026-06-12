from datetime import UTC, datetime, timedelta

from sqlalchemy import select
from test_semester_queue import _create_queue, _current_blocks, _prepare_course

from app.models.course import Course
from app.models.diagnostics import TopicMastery
from app.models.semester_queue import SemesterStudyQueueRevision


def test_empty_dashboard_and_unknown_queue(client):
    response = client.get("/api/v1/semester/dashboard")
    assert response.status_code == 200
    body = response.json()
    assert body["courses"] == body["queues"] == []
    assert body["next_action"] is None
    assert body["course_count"] == body["due_review_count"] == 0
    assert client.get("/api/v1/semester/dashboard?queue_id=missing").status_code == 404


def test_unmeasured_course_has_no_fabricated_grade_and_date_only_urgency(client):
    course = _prepare_course(client, "Physics")
    with client.app.state.session_factory() as db:
        db.get(Course, course).exam_date = datetime.now(UTC).date() + timedelta(days=2)
        db.commit()
    body = client.get("/api/v1/semester/dashboard").json()
    row = body["courses"][0]
    assert row["current_estimated_grade"] is None
    assert row["target_status"] == "unmeasured"
    assert row["deadline_pressure"] == "soon"
    assert row["days_until_exam"] == 2
    assert body["upcoming_exam_count"] == body["unmeasured_course_count"] == 1


def test_measured_gap_matches_grade_scale_and_stale_read_does_not_write(client):
    course = _prepare_course(client, "Physics")
    queue = _create_queue(client, [course])
    topic = _current_blocks(queue)[0]["topic_id"]
    with client.app.state.session_factory() as db:
        db.add(
            TopicMastery(
                course_id=course,
                topic_id=topic,
                mastery=0.2,
                confidence=0.9,
                evidence_weight=5,
                response_count=5,
            )
        )
        db.commit()
    body = client.get("/api/v1/semester/dashboard").json()
    row = body["courses"][0]
    assert row["target_status"] == "below_target"
    assert row["measured_topic_count"] == 1
    assert abs(row["normalized_target_gap"] - row["target_gap"] / 30) < 0.001
    assert body["below_target_count"] == 1
    assert body["queues"][0]["needs_refresh"] is True
    assert body["next_action"] is None
    with client.app.state.session_factory() as db:
        assert len(db.scalars(select(SemesterStudyQueueRevision)).all()) == 1


def test_newest_queue_selected_without_adding_alternative_budgets(client):
    course = _prepare_course(client, "Physics")
    first = _create_queue(client, [course], hours=2)
    second = _create_queue(client, [course], hours=1)
    body = client.get("/api/v1/semester/dashboard").json()
    assert body["selected_queue_id"] == second["id"]
    assert body["next_action"]["id"] == second["next_block_id"]
    selected = client.get("/api/v1/semester/dashboard", params={"queue_id": first["id"]}).json()
    assert selected["next_action"]["id"] == first["next_block_id"]
    assert sorted(q["remaining_available_minutes"] for q in selected["queues"]) == [60, 120]


def test_in_progress_block_remains_visible_when_course_changes(client):
    course = _prepare_course(client, "Physics")
    queue = _create_queue(client, [course])
    block_id = queue["next_block_id"]
    assert (
        client.post(f"/api/v1/semester-queues/{queue['id']}/blocks/{block_id}/start").status_code
        == 200
    )
    with client.app.state.session_factory() as db:
        db.get(Course, course).target_grade = 28
        db.commit()
    body = client.get("/api/v1/semester/dashboard").json()
    assert body["queues"][0]["needs_refresh"]
    assert body["next_action"]["id"] == block_id
    assert body["next_action"]["status"] == "in_progress"


def test_completed_queue_is_not_automatically_selected(client):
    course = _prepare_course(client, "Physics")
    queue = _create_queue(client, [course], hours=0.5)
    completed = client.post(
        f"/api/v1/semester-queues/{queue['id']}/blocks/{queue['next_block_id']}/complete",
        json={"actual_minutes": 30},
    )
    assert completed.status_code == 200
    body = client.get("/api/v1/semester/dashboard").json()
    assert body["selected_queue_id"] is None
    assert body["next_action"] is None
    assert body["queues"][0]["completed_study_minutes"] == 30
