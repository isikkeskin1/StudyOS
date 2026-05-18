from __future__ import annotations

from fastapi.testclient import TestClient


def test_create_and_list_course(client: TestClient) -> None:
    response = client.post(
        "/api/v1/courses",
        json={
            "name": "Physics I",
            "exam_date": "2026-09-14",
            "target_grade": 25,
            "max_grade": 30,
        },
    )

    assert response.status_code == 201
    created = response.json()
    assert created["name"] == "Physics I"
    assert created["target_grade"] == 25

    list_response = client.get("/api/v1/courses")
    assert list_response.status_code == 200
    assert [course["id"] for course in list_response.json()] == [created["id"]]


def test_target_grade_cannot_exceed_max_grade(client: TestClient) -> None:
    response = client.post(
        "/api/v1/courses",
        json={"name": "Impossible Course", "target_grade": 31, "max_grade": 30},
    )

    assert response.status_code == 422


def test_missing_course_returns_404(client: TestClient) -> None:
    response = client.get("/api/v1/courses/not-a-real-course")

    assert response.status_code == 404
