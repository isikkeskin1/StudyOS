from __future__ import annotations

from fastapi.testclient import TestClient

from app.models.diagnostics import TopicMastery


def _prepare_course(client: TestClient, name: str, max_grade: float = 30) -> str:
    created = client.post(
        "/api/v1/courses",
        json={"name": name, "target_grade": max_grade * 0.85, "max_grade": max_grade},
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


def _create_queue(client: TestClient, course_ids: list[str], hours: float = 2) -> dict:
    response = client.post(
        "/api/v1/semester-queues",
        json={
            "available_hours": hours,
            "block_minutes": 30,
            "courses": [
                {"course_id": course_id, "baseline_mastery": 0.35}
                for course_id in course_ids
            ],
        },
    )
    assert response.status_code == 201
    return response.json()


def _current_blocks(body: dict) -> list[dict]:
    return next(
        revision["blocks"]
        for revision in body["revisions"]
        if revision["revision"] == body["current_revision"]
    )


def test_semester_queue_persists_cross_course_plan(client: TestClient) -> None:
    physics = _prepare_course(client, "Physics", 30)
    programming = _prepare_course(client, "Programming", 100)

    body = _create_queue(client, [physics, programming], hours=4)

    assert body["status"] == "active"
    assert body["current_revision"] == 1
    assert body["revisions"][0]["optimization_model"] == (
        "normalized-target-utility-greedy-v1"
    )
    assert len(body["revisions"][0]["courses"]) == 2
    assert body["remaining_available_minutes"] == 240
    assert set(body["course_ids"]) == {physics, programming}
    blocks = _current_blocks(body)
    assert sum(block["planned_minutes"] for block in blocks) == 240
    assert {block["course_id"] for block in blocks} == {physics, programming}
    assert body["next_block_id"] == blocks[0]["id"]

    fetched = client.get(f"/api/v1/semester-queues/{body['id']}")
    assert fetched.status_code == 200
    listed = client.get("/api/v1/semester-queues")
    assert listed.status_code == 200
    assert listed.json()[0]["id"] == body["id"]


def test_completion_replans_all_courses_with_actual_time(client: TestClient) -> None:
    physics = _prepare_course(client, "Physics")
    programming = _prepare_course(client, "Programming")
    created = _create_queue(client, [physics, programming])
    first = _current_blocks(created)[0]

    started = client.post(
        f"/api/v1/semester-queues/{created['id']}/blocks/{first['id']}/start"
    )
    assert started.status_code == 200
    completed = client.post(
        f"/api/v1/semester-queues/{created['id']}/blocks/{first['id']}/complete",
        json={"actual_minutes": 15, "note": "Finished early"},
    )
    assert completed.status_code == 200
    body = completed.json()
    assert body["current_revision"] == 2
    assert body["completed_study_minutes"] == 15
    assert body["remaining_available_minutes"] == 105
    assert body["revisions"][1]["reason"] == "completed_early"
    assert sum(block["planned_minutes"] for block in _current_blocks(body)) == 105
    old = body["revisions"][0]["blocks"]
    assert next(block for block in old if block["id"] == first["id"])["status"] == "completed"
    assert all(block["status"] in {"completed", "superseded"} for block in old)


def test_queue_enforces_order_and_skip_reallocates_budget(client: TestClient) -> None:
    course = _prepare_course(client, "Physics")
    created = _create_queue(client, [course], hours=2)
    blocks = _current_blocks(created)

    out_of_order = client.post(
        f"/api/v1/semester-queues/{created['id']}/blocks/{blocks[1]['id']}/start"
    )
    assert out_of_order.status_code == 409

    skipped = client.post(
        f"/api/v1/semester-queues/{created['id']}/blocks/{blocks[0]['id']}/skip",
        json={"note": "Missed block"},
    )
    assert skipped.status_code == 200
    body = skipped.json()
    assert body["lost_minutes"] == 30
    assert body["remaining_available_minutes"] == 90
    assert body["current_revision"] == 2
    assert body["revisions"][1]["reason"] == "missed_block"


def test_get_automatically_replans_after_measured_mastery_changes(
    client: TestClient,
) -> None:
    course = _prepare_course(client, "Physics")
    created = _create_queue(client, [course])
    first_topic = _current_blocks(created)[0]["topic_id"]
    assert first_topic is not None

    with client.app.state.session_factory() as db:
        db.add(
            TopicMastery(
                course_id=course,
                topic_id=first_topic,
                mastery=0.99,
                confidence=0.9,
                evidence_weight=5,
                response_count=5,
            )
        )
        db.commit()

    refreshed = client.get(f"/api/v1/semester-queues/{created['id']}")
    assert refreshed.status_code == 200
    body = refreshed.json()
    assert body["current_revision"] == 2
    assert body["revisions"][1]["reason"] == "source_change"
    assert _current_blocks(body)[0]["topic_id"] != first_topic


def test_manual_refresh_can_reduce_but_not_increase_budget(client: TestClient) -> None:
    course = _prepare_course(client, "Physics")
    created = _create_queue(client, [course])

    reduced = client.post(
        f"/api/v1/semester-queues/{created['id']}/refresh",
        json={"remaining_available_minutes": 60},
    )
    assert reduced.status_code == 200
    assert reduced.json()["remaining_available_minutes"] == 60
    assert reduced.json()["lost_minutes"] == 60

    increased = client.post(
        f"/api/v1/semester-queues/{created['id']}/refresh",
        json={"remaining_available_minutes": 90},
    )
    assert increased.status_code == 409
