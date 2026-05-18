from __future__ import annotations

from fastapi.testclient import TestClient


def _create_course(client: TestClient) -> str:
    response = client.post("/api/v1/courses", json={"name": "Physics I"})
    assert response.status_code == 201
    return response.json()["id"]


def _upload_and_process(
    client: TestClient,
    course_id: str,
    filename: str,
    content: bytes,
) -> str:
    upload = client.post(
        f"/api/v1/courses/{course_id}/documents",
        files={"file": (filename, content, "text/plain")},
    )
    assert upload.status_code == 201
    document_id = upload.json()["id"]

    process = client.post(f"/api/v1/courses/{course_id}/documents/{document_id}/process")
    assert process.status_code == 200
    return document_id


def test_course_analysis_builds_topics_evidence_and_relationships(client: TestClient) -> None:
    course_id = _create_course(client)

    _upload_and_process(
        client,
        course_id,
        "lecture-mechanics.txt",
        (
            b"Newton's Laws\n"
            b"Newton's laws describe motion and forces. "
            b"Newton's second law relates force, mass, and acceleration.\n\n"
            b"Momentum\n"
            b"Momentum is conserved in isolated systems. "
            b"Newton's laws are used together with momentum in collision problems."
        ),
    )
    _upload_and_process(
        client,
        course_id,
        "2025-written-exam.txt",
        (
            b"Physics I Written Exam\n"
            b"Newton's Laws\n"
            b"Question 1 asks about Newton's second law and force.\n\n"
            b"Momentum\n"
            b"Question 2 asks about conservation of momentum in a collision."
        ),
    )

    response = client.post(f"/api/v1/courses/{course_id}/analyze")

    assert response.status_code == 200
    intelligence = response.json()
    assert intelligence["analysis"]["analyzed_document_count"] == 2
    assert intelligence["analysis"]["topic_count"] > 0

    topics = {topic["normalized_name"]: topic for topic in intelligence["topics"]}
    assert "momentum" in topics
    assert topics["momentum"]["exam_mention_count"] > 0
    assert topics["momentum"]["lecture_mention_count"] > 0
    assert topics["momentum"]["evidence"]

    newton_topics = [
        topic for name, topic in topics.items() if "newton" in name and "law" in name
    ]
    assert newton_topics
    assert any(topic["exam_mention_count"] > 0 for topic in newton_topics)

    assert intelligence["relationships"]


def test_get_intelligence_requires_analysis(client: TestClient) -> None:
    course_id = _create_course(client)

    response = client.get(f"/api/v1/courses/{course_id}/intelligence")

    assert response.status_code == 409


def test_analysis_requires_processed_documents(client: TestClient) -> None:
    course_id = _create_course(client)
    upload = client.post(
        f"/api/v1/courses/{course_id}/documents",
        files={"file": ("notes.txt", b"Momentum", "text/plain")},
    )
    assert upload.status_code == 201

    response = client.post(f"/api/v1/courses/{course_id}/analyze")

    assert response.status_code == 409


def test_reanalysis_replaces_previous_topic_graph(client: TestClient) -> None:
    course_id = _create_course(client)
    _upload_and_process(
        client,
        course_id,
        "lecture.txt",
        b"Momentum\nMomentum and impulse are related. Momentum is conserved.",
    )

    first = client.post(f"/api/v1/courses/{course_id}/analyze")
    second = client.post(f"/api/v1/courses/{course_id}/analyze")

    assert first.status_code == 200
    assert second.status_code == 200
    assert first.json()["analysis"]["topic_count"] == second.json()["analysis"]["topic_count"]
    assert len(first.json()["topics"]) == len(second.json()["topics"])
