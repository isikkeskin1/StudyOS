from __future__ import annotations

from fastapi.testclient import TestClient


def _prepare(client: TestClient) -> str:
    course = client.post(
        "/api/v1/courses",
        json={"name": "Physics I", "target_grade": 25, "max_grade": 30},
    )
    assert course.status_code == 201
    course_id = course.json()["id"]

    for filename, content in [
        (
            "lecture.txt",
            b"Newton's laws relate force, mass, and acceleration. Momentum is conserved.",
        ),
        (
            "exam.txt",
            (
                b"Physics I Written Exam\n"
                b"Question 1 (8 marks)\n"
                b"Calculate force using Newton's second law.\n\n"
                b"Question 2 (12 marks)\n"
                b"Use conservation of momentum."
            ),
        ),
    ]:
        upload = client.post(
            f"/api/v1/courses/{course_id}/documents",
            files={"file": (filename, content, "text/plain")},
        )
        assert upload.status_code == 201
        process = client.post(
            f"/api/v1/courses/{course_id}/documents/{upload.json()['id']}/process"
        )
        assert process.status_code == 200

    assert client.post(f"/api/v1/courses/{course_id}/analyze").status_code == 200
    assert (
        client.post(f"/api/v1/courses/{course_id}/exam-intelligence/analyze").status_code
        == 200
    )
    return course_id


def test_exam_day_persists_answers_flags_and_submits(client: TestClient) -> None:
    course_id = _prepare(client)

    started = client.post(
        f"/api/v1/courses/{course_id}/exam-day",
        json={"duration_minutes": 90, "question_count": 2},
    )
    assert started.status_code == 201
    session = started.json()
    assert session["status"] == "active"
    assert session["question_count"] == 2
    assert session["remaining_seconds"] > 0

    first = session["questions"][0]
    saved = client.put(
        f"/api/v1/courses/{course_id}/exam-day/{session['id']}/questions/{first['id']}",
        json={
            "answer_text": "F = m a",
            "flagged": True,
            "self_score": 0.75,
            "confidence": 0.8,
        },
    )
    assert saved.status_code == 200
    body = saved.json()
    assert body["answered_count"] == 1
    assert body["flagged_count"] == 1
    assert body["questions"][0]["answer_text"] == "F = m a"

    recovered = client.get(
        f"/api/v1/courses/{course_id}/exam-day/{session['id']}"
    )
    assert recovered.status_code == 200
    assert recovered.json()["questions"][0]["flagged"] is True

    submitted = client.post(
        f"/api/v1/courses/{course_id}/exam-day/{session['id']}/submit"
    )
    assert submitted.status_code == 200
    result = submitted.json()
    assert result["status"] == "submitted"
    assert result["answered_count"] == 1
    assert result["question_count"] == 2
    assert result["average_score"] is not None
    assert result["topic_breakdown"]

    reread = client.get(
        f"/api/v1/courses/{course_id}/exam-day/{session['id']}/result"
    )
    assert reread.status_code == 200
    assert reread.json()["session_id"] == session["id"]

    mastery = client.get(f"/api/v1/courses/{course_id}/mastery")
    assert mastery.status_code == 200
    assert mastery.json()


def test_exam_day_requires_exam_intelligence(client: TestClient) -> None:
    course = client.post("/api/v1/courses", json={"name": "Physics I"})
    course_id = course.json()["id"]

    response = client.post(
        f"/api/v1/courses/{course_id}/exam-day",
        json={"duration_minutes": 60, "question_count": 5},
    )

    assert response.status_code == 409
