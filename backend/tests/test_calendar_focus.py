from __future__ import annotations

from datetime import datetime, timedelta

from fastapi.testclient import TestClient


def _prepare_course(client: TestClient, name: str = "Physics") -> str:
    created = client.post(
        "/api/v1/courses",
        json={"name": name, "target_grade": 25, "max_grade": 30},
    )
    assert created.status_code == 201
    course_id = created.json()["id"]
    documents = [
        (
            f"{name}-notes.txt",
            b"Mechanics\nForce mass acceleration dynamics Newton law.\n\n"
            b"Momentum\nMomentum conservation collisions impulse.\n\n"
            b"Oscillations\nPeriod frequency spring amplitude.",
        ),
        (
            f"{name}-exam.txt",
            b"Written Exam\nQuestion 1 (12 marks)\nMomentum and impulse.\n\n"
            b"Question 2 (8 marks)\nForce and acceleration.\n\n"
            b"Question 3 (2 marks)\nOscillator period.",
        ),
    ]
    for filename, content in documents:
        uploaded = client.post(
            f"/api/v1/courses/{course_id}/documents",
            files={"file": (filename, content, "text/plain")},
        )
        assert uploaded.status_code == 201
        processed = client.post(
            f"/api/v1/courses/{course_id}/documents/{uploaded.json()['id']}/process"
        )
        assert processed.status_code == 200
    assert client.post(f"/api/v1/courses/{course_id}/analyze").status_code == 200
    assert (
        client.post(f"/api/v1/courses/{course_id}/exam-intelligence/analyze").status_code
        == 200
    )
    return course_id


def _create_queue(
    client: TestClient,
    course_id: str,
    *,
    hours: float = 2,
    hours_until_exam: float | None = None,
) -> dict:
    response = client.post(
        "/api/v1/semester-queues",
        json={
            "available_hours": hours,
            "block_minutes": 30,
            "courses": [
                {
                    "course_id": course_id,
                    "baseline_mastery": 0.35,
                    "hours_until_exam": hours_until_exam,
                }
            ],
        },
    )
    assert response.status_code == 201
    return response.json()


def _current_blocks(queue: dict) -> list[dict]:
    return next(
        revision["blocks"]
        for revision in queue["revisions"]
        if revision["revision"] == queue["current_revision"]
    )


def test_calendar_plan_persists_sequential_events_and_exports_ics(client: TestClient) -> None:
    course_id = _prepare_course(client)
    queue = _create_queue(client, course_id)
    start_at = datetime.fromisoformat(queue["created_at"]) + timedelta(hours=1)

    created = client.post(
        f"/api/v1/semester-queues/{queue['id']}/calendar-plans",
        json={
            "start_at": start_at.isoformat(),
            "timezone": "Europe/Rome",
            "break_minutes": 10,
        },
    )

    assert created.status_code == 201
    plan = created.json()
    blocks = _current_blocks(queue)
    assert plan["revision"] == queue["current_revision"]
    assert plan["status"] == "current"
    assert plan["event_count"] == len(blocks)
    assert [event["block_id"] for event in plan["events"]] == [block["id"] for block in blocks]

    first_end = datetime.fromisoformat(plan["events"][0]["ends_at"])
    second_start = datetime.fromisoformat(plan["events"][1]["starts_at"])
    assert second_start - first_end == timedelta(minutes=10)

    listed = client.get(f"/api/v1/semester-queues/{queue['id']}/calendar-plans")
    fetched = client.get(
        f"/api/v1/semester-queues/{queue['id']}/calendar-plans/{plan['id']}"
    )
    exported = client.get(
        f"/api/v1/semester-queues/{queue['id']}/calendar-plans/{plan['id']}/ics"
    )
    assert listed.status_code == 200
    assert listed.json()[0]["id"] == plan["id"]
    assert fetched.status_code == 200
    assert exported.status_code == 200
    assert exported.headers["content-type"].startswith("text/calendar")
    assert "BEGIN:VCALENDAR" in exported.text
    assert exported.text.count("BEGIN:VEVENT") == len(blocks)
    assert plan["events"][0]["uid"] in exported.text


def test_calendar_plan_rejects_blocks_after_exact_deadline(client: TestClient) -> None:
    course_id = _prepare_course(client)
    queue = _create_queue(client, course_id, hours=1, hours_until_exam=1.5)
    too_late = datetime.fromisoformat(queue["created_at"]) + timedelta(hours=2)

    response = client.post(
        f"/api/v1/semester-queues/{queue['id']}/calendar-plans",
        json={"start_at": too_late.isoformat(), "timezone": "UTC", "break_minutes": 0},
    )

    assert response.status_code == 409
    assert "after its exact exam deadline" in response.json()["detail"]


def test_focus_session_executes_next_block_and_stales_calendar_plan(client: TestClient) -> None:
    course_id = _prepare_course(client)
    queue = _create_queue(client, course_id)
    blocks = _current_blocks(queue)
    start_at = datetime.fromisoformat(queue["created_at"]) + timedelta(minutes=5)
    calendar = client.post(
        f"/api/v1/semester-queues/{queue['id']}/calendar-plans",
        json={"start_at": start_at.isoformat(), "timezone": "UTC", "break_minutes": 5},
    ).json()

    started = client.post(
        f"/api/v1/semester-queues/{queue['id']}/focus-sessions",
        json={"expected_block_id": blocks[0]["id"]},
    )
    assert started.status_code == 201
    focus = started.json()["session"]
    assert focus["status"] == "active"
    assert focus["block_id"] == blocks[0]["id"]
    assert started.json()["queue"]["next_block_id"] == blocks[0]["id"]
    current_block = _current_blocks(started.json()["queue"])[0]
    assert current_block["status"] == "in_progress"

    completed = client.post(
        f"/api/v1/semester-queues/{queue['id']}/focus-sessions/{focus['id']}/complete",
        json={"actual_minutes": 20, "note": "Focused cleanly"},
    )
    assert completed.status_code == 200
    body = completed.json()
    assert body["session"]["status"] == "completed"
    assert body["session"]["actual_minutes"] == 20
    assert body["queue"]["current_revision"] == 2
    assert body["queue"]["completed_study_minutes"] == 20

    old_calendar = client.get(
        f"/api/v1/semester-queues/{queue['id']}/calendar-plans/{calendar['id']}"
    )
    assert old_calendar.status_code == 200
    assert old_calendar.json()["status"] == "stale"
    assert old_calendar.json()["current_revision"] == 2

    next_focus = client.post(
        f"/api/v1/semester-queues/{queue['id']}/focus-sessions",
        json={},
    )
    assert next_focus.status_code == 201
    assert next_focus.json()["session"]["queue_revision"] == 2


def test_focus_session_rejects_stale_expected_block_and_skip_replans(client: TestClient) -> None:
    course_id = _prepare_course(client)
    queue = _create_queue(client, course_id)
    blocks = _current_blocks(queue)

    stale = client.post(
        f"/api/v1/semester-queues/{queue['id']}/focus-sessions",
        json={"expected_block_id": blocks[1]["id"]},
    )
    assert stale.status_code == 409

    started = client.post(
        f"/api/v1/semester-queues/{queue['id']}/focus-sessions",
        json={"expected_block_id": blocks[0]["id"]},
    )
    assert started.status_code == 201
    focus_id = started.json()["session"]["id"]

    skipped = client.post(
        f"/api/v1/semester-queues/{queue['id']}/focus-sessions/{focus_id}/skip",
        json={"lost_minutes": 10, "note": "Interrupted"},
    )
    assert skipped.status_code == 200
    body = skipped.json()
    assert body["session"]["status"] == "skipped"
    assert body["queue"]["current_revision"] == 2
    assert body["queue"]["lost_minutes"] == 10

    sessions = client.get(f"/api/v1/semester-queues/{queue['id']}/focus-sessions")
    assert sessions.status_code == 200
    assert sessions.json()[0]["id"] == focus_id
