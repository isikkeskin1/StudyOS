from __future__ import annotations

from datetime import UTC, datetime, timedelta

from fastapi.testclient import TestClient

from app.models.semester_queue import SemesterStudyQueue, SemesterStudyQueueBlock


def _seed_queue(client: TestClient) -> str:
    user_id = client.get("/api/v1/auth/me").json()["id"]
    now = datetime.now(UTC)
    with client.app.state.session_factory() as db:
        queue = SemesterStudyQueue(
            user_id=user_id,
            status="active",
            initial_available_minutes=60,
            remaining_available_minutes=60,
            lost_minutes=0,
            block_minutes=30,
            course_configs=[],
            current_revision=1,
            created_at=now,
            updated_at=now,
        )
        db.add(queue)
        db.flush()
        for sequence, topic in enumerate(("Momentum", "Oscillations"), start=1):
            db.add(
                SemesterStudyQueueBlock(
                    queue_id=queue.id,
                    course_id=None,
                    course_name="Physics I",
                    topic_id=None,
                    topic_name=topic,
                    revision=1,
                    sequence=sequence,
                    status="planned",
                    planned_minutes=30,
                    expected_mark_gain=1.5,
                    normalized_target_gap_reduction=0.05,
                    utility_score=0.05,
                    created_at=now,
                )
            )
        db.commit()
        return queue.id


def test_push_subscription_lifecycle_and_disabled_config(client: TestClient) -> None:
    config = client.get("/api/v1/notifications/config")
    assert config.status_code == 200
    assert config.json() == {"enabled": False, "public_key": None}

    created = client.post(
        "/api/v1/notifications/subscriptions",
        json={
            "endpoint": "https://example.test/device",
            "keys": {"p256dh": "key-material", "auth": "auth-material"},
        },
    )
    assert created.status_code == 201
    subscription_id = created.json()["id"]

    listed = client.get("/api/v1/notifications/subscriptions")
    assert listed.status_code == 200
    assert [row["id"] for row in listed.json()] == [subscription_id]

    assert client.post("/api/v1/notifications/test").status_code == 409

    deleted = client.delete(
        f"/api/v1/notifications/subscriptions/{subscription_id}"
    )
    assert deleted.status_code == 204
    assert client.get("/api/v1/notifications/subscriptions").json() == []


def test_calendar_subscription_feed_is_secret_live_and_revocable(
    client: TestClient,
) -> None:
    queue_id = _seed_queue(client)
    created = client.post(
        f"/api/v1/semester-queues/{queue_id}/calendar-subscriptions",
        json={
            "start_at": (datetime.now(UTC) + timedelta(minutes=10)).isoformat(),
            "timezone": "Europe/Rome",
            "break_minutes": 5,
        },
    )
    assert created.status_code == 201
    body = created.json()
    assert body["queue_id"] == queue_id
    assert body["active"] is True
    assert body["feed_path"].startswith("/calendar/")
    assert body["feed_path"].endswith(".ics")

    session_cookie = client.cookies.get("studyos_session")
    feed_path = body["feed_path"]
    client.cookies.clear()
    feed = client.get(feed_path)
    assert feed.status_code == 200
    assert feed.headers["content-type"].startswith("text/calendar")
    assert "X-WR-CALNAME:StudyOS Live Study Plan" in feed.text
    assert feed.text.count("BEGIN:VEVENT") == 2
    assert "Momentum" in feed.text
    assert "Oscillations" in feed.text
    assert client.get("/calendar/not-a-real-token.ics").status_code == 404

    assert session_cookie is not None
    client.cookies.set("studyos_session", session_cookie)
    revoked = client.delete(
        f"/api/v1/semester-queues/{queue_id}/calendar-subscriptions/{body['id']}"
    )
    assert revoked.status_code == 204

    client.cookies.clear()
    assert client.get(feed_path).status_code == 404
