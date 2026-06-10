from __future__ import annotations

from fastapi.testclient import TestClient

from app.models.diagnostics import TopicMastery


def _create_course(client: TestClient, name: str = "Physics I") -> str:
    response = client.post(
        "/api/v1/courses",
        json={"name": name, "target_grade": 25, "max_grade": 30},
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


def _prepare_course(client: TestClient, name: str = "Physics I") -> str:
    course_id = _create_course(client, name)
    _upload_and_process(
        client,
        course_id,
        "lecture-mechanics.txt",
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
    assert client.post(f"/api/v1/courses/{course_id}/analyze").status_code == 200
    assert (
        client.post(f"/api/v1/courses/{course_id}/exam-intelligence/analyze").status_code
        == 200
    )
    return course_id


def _create_schedule(client: TestClient, course_id: str, hours: float = 2) -> dict:
    response = client.post(
        f"/api/v1/courses/{course_id}/emergency-schedules",
        json={
            "available_hours": hours,
            "hours_until_exam": 12,
            "block_minutes": 30,
            "baseline_mastery": 0.4,
        },
    )
    assert response.status_code == 201
    return response.json()


def _current_blocks(body: dict) -> list[dict]:
    revision = body["current_revision"]
    return next(item["blocks"] for item in body["revisions"] if item["revision"] == revision)


def test_emergency_schedule_persists_initial_plan(client: TestClient) -> None:
    course_id = _prepare_course(client)
    body = _create_schedule(client, course_id, hours=2)

    assert body["status"] == "active"
    assert body["current_revision"] == 1
    assert body["initial_available_minutes"] == 120
    assert body["remaining_available_minutes"] == 120
    assert body["completed_study_minutes"] == 0
    assert body["lost_minutes"] == 0
    assert len(body["revisions"]) == 1
    assert body["revisions"][0]["reason"] == "initial"
    assert sum(block["planned_minutes"] for block in _current_blocks(body)) == 120
    assert body["next_block_id"] == _current_blocks(body)[0]["id"]

    fetched = client.get(
        f"/api/v1/courses/{course_id}/emergency-schedules/{body['id']}"
    )
    assert fetched.status_code == 200
    assert fetched.json()["id"] == body["id"]

    listed = client.get(f"/api/v1/courses/{course_id}/emergency-schedules")
    assert listed.status_code == 200
    assert [item["id"] for item in listed.json()] == [body["id"]]


def test_completing_early_preserves_time_and_creates_projected_revision(
    client: TestClient,
) -> None:
    course_id = _prepare_course(client)
    created = _create_schedule(client, course_id, hours=2)
    schedule_id = created["id"]
    block = _current_blocks(created)[0]

    started = client.post(
        f"/api/v1/courses/{course_id}/emergency-schedules/{schedule_id}"
        f"/blocks/{block['id']}/start"
    )
    assert started.status_code == 200
    assert _current_blocks(started.json())[0]["status"] == "in_progress"

    completed = client.post(
        f"/api/v1/courses/{course_id}/emergency-schedules/{schedule_id}"
        f"/blocks/{block['id']}/complete",
        json={"actual_minutes": 15, "note": "Finished the review early"},
    )
    assert completed.status_code == 200
    body = completed.json()
    assert body["current_revision"] == 2
    assert body["completed_study_minutes"] == 15
    assert body["remaining_available_minutes"] == 105
    assert len(body["revisions"]) == 2
    assert body["revisions"][1]["reason"] == "completed_early"
    assert (
        body["revisions"][1]["mastery_basis"]
        == "current-evidence+completed-study-projection-v1"
    )
    assert sum(block["planned_minutes"] for block in _current_blocks(body)) == 105

    old = body["revisions"][0]["blocks"]
    completed_old = next(item for item in old if item["id"] == block["id"])
    assert completed_old["status"] == "completed"
    assert completed_old["actual_minutes"] == 15
    assert all(item["status"] in {"completed", "superseded"} for item in old)


def test_skipping_block_loses_time_and_reallocates_remaining_budget(
    client: TestClient,
) -> None:
    course_id = _prepare_course(client)
    created = _create_schedule(client, course_id, hours=4)
    schedule_id = created["id"]
    block = _current_blocks(created)[0]

    response = client.post(
        f"/api/v1/courses/{course_id}/emergency-schedules/{schedule_id}"
        f"/blocks/{block['id']}/skip",
        json={"note": "Missed because of another commitment"},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["lost_minutes"] == block["planned_minutes"]
    assert body["remaining_available_minutes"] == 240 - block["planned_minutes"]
    assert body["current_revision"] == 2
    assert body["revisions"][1]["reason"] == "missed_block"


def test_manual_reschedule_can_reduce_but_not_increase_remaining_budget(
    client: TestClient,
) -> None:
    course_id = _prepare_course(client)
    created = _create_schedule(client, course_id, hours=2)
    schedule_id = created["id"]

    reduced = client.post(
        f"/api/v1/courses/{course_id}/emergency-schedules/{schedule_id}/reschedule",
        json={"remaining_available_minutes": 60},
    )
    assert reduced.status_code == 200
    body = reduced.json()
    assert body["current_revision"] == 2
    assert body["remaining_available_minutes"] == 60
    assert body["lost_minutes"] == 60
    assert sum(block["planned_minutes"] for block in _current_blocks(body)) == 60

    increased = client.post(
        f"/api/v1/courses/{course_id}/emergency-schedules/{schedule_id}/reschedule",
        json={"remaining_available_minutes": 90},
    )
    assert increased.status_code == 409


def test_manual_refresh_uses_new_measured_mastery(client: TestClient) -> None:
    course_id = _prepare_course(client)
    created = _create_schedule(client, course_id, hours=2)
    schedule_id = created["id"]
    original_first_topic = _current_blocks(created)[0]["topic_id"]
    assert original_first_topic is not None

    with client.app.state.session_factory() as db:
        db.add(
            TopicMastery(
                course_id=course_id,
                topic_id=original_first_topic,
                mastery=0.99,
                confidence=0.9,
                evidence_weight=5.0,
                response_count=5,
            )
        )
        db.commit()

    refreshed = client.post(
        f"/api/v1/courses/{course_id}/emergency-schedules/{schedule_id}/reschedule",
        json={},
    )
    assert refreshed.status_code == 200
    body = refreshed.json()
    assert body["current_revision"] == 2
    assert body["revisions"][1]["reason"] == "manual_refresh"
    assert body["revisions"][1]["mastery_basis"] == "current-evidence-v1"
    assert _current_blocks(body)[0]["topic_id"] != original_first_topic


def test_schedule_blocks_are_course_and_revision_isolated(client: TestClient) -> None:
    course_id = _prepare_course(client)
    other_course_id = _prepare_course(client, "Other Physics")
    created = _create_schedule(client, course_id, hours=2)
    schedule_id = created["id"]
    old_block_id = _current_blocks(created)[0]["id"]

    wrong_course = client.get(
        f"/api/v1/courses/{other_course_id}/emergency-schedules/{schedule_id}"
    )
    assert wrong_course.status_code == 404

    completed = client.post(
        f"/api/v1/courses/{course_id}/emergency-schedules/{schedule_id}"
        f"/blocks/{old_block_id}/complete",
        json={"actual_minutes": 15},
    )
    assert completed.status_code == 200
    assert completed.json()["current_revision"] == 2

    stale_block = client.post(
        f"/api/v1/courses/{course_id}/emergency-schedules/{schedule_id}"
        f"/blocks/{old_block_id}/start"
    )
    assert stale_block.status_code == 404
