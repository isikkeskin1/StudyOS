from datetime import UTC, datetime, timedelta

from sqlalchemy import select
from test_tutor_practice_evaluation import _correct_answer, _prepare_solution_course

from app.models.course_intelligence import CourseTopic
from app.models.diagnostics import TopicMastery
from app.models.review_session import ReviewSession
from app.models.tutor_practice import TutorPracticeAttempt, TutorPracticeItem


def _due(client):
    course = _prepare_solution_course(client)
    with client.app.state.session_factory() as db:
        topics = db.scalars(select(CourseTopic).where(CourseTopic.course_id == course)).all()
        for topic in topics:
            db.add(
                TopicMastery(
                    course_id=course,
                    topic_id=topic.id,
                    mastery=0.7,
                    confidence=0.8,
                    evidence_weight=5,
                    response_count=5,
                    updated_at=datetime.now(UTC) - timedelta(days=30),
                )
            )
        db.commit()
    return course


def _start(client, course, **kwargs):
    return client.post(
        f"/api/v1/courses/{course}/review-sessions", json={"provider": "local", **kwargs}
    )


def test_review_selects_due_topic_and_resumes_without_duplicate_practice(client):
    course = _due(client)
    due = client.get(f"/api/v1/courses/{course}/reviews").json()["items"][0]
    first = _start(client, course)
    assert first.status_code == 201
    body = first.json()
    assert body["topic_id"] == due["topic_id"]
    assert body["status"] == "active"
    assert body["due_now"] is True
    assert body["selection_snapshot"]["review_priority"] == due["review_priority"]
    assert _start(client, course).json()["id"] == body["id"]
    with client.app.state.session_factory() as db:
        assert len(db.scalars(select(TutorPracticeItem)).all()) == 1
        assert len(db.scalars(select(ReviewSession)).all()) == 1
        assert len(db.scalars(select(TutorPracticeAttempt)).all()) == 0


def test_graded_review_updates_mastery_due_queue_and_rejects_duplicate(client):
    course = _due(client)
    review = _start(client, course).json()
    path = f"/api/v1/courses/{course}/review-sessions/{review['id']}"
    answer = {
        "student_answer": _correct_answer(review["practice"]["question"]),
        "grading_provider": "local",
        "duration_seconds": 90,
    }
    response = client.post(path + "/answer", json=answer)
    assert response.status_code == 200
    body = response.json()
    assert body["review"]["status"] == "completed"
    assert body["review"]["due_now"] is False
    assert body["evaluation"]["mastery_after"] is not None
    assert body["evaluation"]["next_practice"] is None
    assert client.get(path).json()["attempt_id"] == body["evaluation"]["attempt_id"]
    assert client.post(path + "/answer", json=answer).status_code == 409
    assert len(client.get(f"/api/v1/courses/{course}/review-sessions").json()) == 1
    assert _start(client, course, topic_id=review["topic_id"]).status_code == 409
    with client.app.state.session_factory() as db:
        assert len(db.scalars(select(TutorPracticeAttempt)).all()) == 1


def test_skip_is_idempotent_preserves_due_state_and_allows_retry(client):
    course = _due(client)
    review = _start(client, course).json()
    path = f"/api/v1/courses/{course}/review-sessions/{review['id']}"
    first = client.post(path + "/skip")
    assert first.status_code == 200
    assert first.json()["status"] == "skipped"
    assert first.json()["due_now"] is True
    assert client.post(path + "/skip").status_code == 200
    assert client.post(path + "/answer", json={"student_answer": "10 N"}).status_code == 409
    assert _start(client, course, topic_id=review["topic_id"]).json()["id"] != review["id"]
    with client.app.state.session_factory() as db:
        assert len(db.scalars(select(TutorPracticeAttempt)).all()) == 0


def test_revealed_solution_is_not_review_evidence(client):
    course = _due(client)
    review = _start(client, course).json()
    client.get(f"/api/v1/courses/{course}/tutor/practice/{review['practice']['id']}/solution")
    path = f"/api/v1/courses/{course}/review-sessions/{review['id']}"
    assert client.get(path).json()["status"] == "solution_revealed"
    assert client.post(path + "/answer", json={"student_answer": "10 N"}).status_code == 409
    assert _start(client, course).json()["id"] != review["id"]


def test_no_due_topics_and_cross_course_access(client):
    course = _prepare_solution_course(client)
    assert _start(client, course).status_code == 409
    other = _due(client)
    review = _start(client, other).json()
    assert client.get(f"/api/v1/courses/{course}/review-sessions/{review['id']}").status_code == 404
    assert _start(client, other, topic_id="missing").status_code == 409


def test_generation_failure_does_not_persist_partial_review(client, monkeypatch):
    from app.services.tutor_practice import TutorPracticeUnavailable

    course = _due(client)

    def fail(*args, **kwargs):
        raise TutorPracticeUnavailable("No question source available")

    monkeypatch.setattr("app.services.tutor_practice._local_exam_practice", fail)
    assert _start(client, course).status_code == 409
    with client.app.state.session_factory() as db:
        assert not db.scalars(select(ReviewSession)).all()
        assert not db.scalars(select(TutorPracticeItem)).all()
