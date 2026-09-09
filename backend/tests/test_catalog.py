from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient

from app.core.config import Settings
from app.main import create_app


def _app(tmp_path: Path):
    return create_app(
        Settings(
            environment="test",
            database_url=f"sqlite:///{tmp_path / 'catalog.db'}",
            data_dir=tmp_path / "uploads",
            max_upload_mb=2,
            admin_emails=("admin@studyos.local",),
        )
    )


def test_admin_can_publish_polito_course_and_user_can_enroll(tmp_path: Path) -> None:
    app = _app(tmp_path)

    with TestClient(app) as admin, TestClient(app) as student:
        registered = admin.post(
            "/api/v1/auth/register",
            json={
                "email": "admin@studyos.local",
                "password": "admin-password-123",
            },
        )
        assert registered.status_code == 201
        assert registered.json()["user"]["is_admin"] is True

        created = admin.post(
            "/api/v1/admin/catalog/courses",
            json={
                "name": "Physics I",
                "institution_name": "Politecnico di Torino",
                "institution_code": "POLITO",
                "course_code": "Physics-I",
                "academic_year": "2026/27",
                "language": "English",
                "description": "Curated Physics I course built from official teaching material.",
                "max_grade": 30,
            },
        )
        assert created.status_code == 201
        catalog = created.json()
        source_course_id = catalog["source_course_id"]
        assert catalog["published"] is False

        uploaded = admin.post(
            f"/api/v1/courses/{source_course_id}/documents",
            files={
                "file": (
                    "physics-lecture.txt",
                    (
                        b"Newton's Laws\n"
                        b"Newton's second law relates force, mass, and acceleration.\n\n"
                        b"Momentum\n"
                        b"Momentum is conserved in isolated systems and impulse changes momentum."
                    ),
                    "text/plain",
                )
            },
        )
        assert uploaded.status_code == 201
        document_id = uploaded.json()["id"]

        processed = admin.post(
            f"/api/v1/courses/{source_course_id}/documents/{document_id}/process"
        )
        assert processed.status_code == 200
        analyzed = admin.post(f"/api/v1/courses/{source_course_id}/analyze")
        assert analyzed.status_code == 200

        published = admin.post(
            f"/api/v1/admin/catalog/courses/{catalog['id']}/publish"
        )
        assert published.status_code == 200
        assert published.json()["published"] is True
        assert published.json()["document_count"] == 1

        student_registered = student.post(
            "/api/v1/auth/register",
            json={
                "email": "student@example.com",
                "password": "student-password-123",
            },
        )
        assert student_registered.status_code == 201
        assert student_registered.json()["user"]["is_admin"] is False

        visible = student.get("/api/v1/catalog/courses")
        assert visible.status_code == 200
        assert len(visible.json()) == 1
        assert visible.json()[0]["institution_name"] == "Politecnico di Torino"
        assert visible.json()[0]["name"] == "Physics I"

        enrolled = student.post(
            f"/api/v1/catalog/courses/{catalog['id']}/enroll"
        )
        assert enrolled.status_code == 201
        personal_course = enrolled.json()
        assert personal_course["name"] == "Physics I"

        documents = student.get(
            f"/api/v1/courses/{personal_course['id']}/documents"
        )
        assert documents.status_code == 200
        assert len(documents.json()) == 1
        assert documents.json()[0]["status"] == "processed"

        intelligence = student.get(
            f"/api/v1/courses/{personal_course['id']}/intelligence"
        )
        assert intelligence.status_code == 200


def test_non_admin_cannot_create_catalog_course(tmp_path: Path) -> None:
    app = _app(tmp_path)

    with TestClient(app) as client:
        assert client.post(
            "/api/v1/auth/register",
            json={
                "email": "student@example.com",
                "password": "student-password-123",
            },
        ).status_code == 201

        response = client.post(
            "/api/v1/admin/catalog/courses",
            json={
                "name": "Physics I",
                "institution_name": "Politecnico di Torino",
            },
        )
        assert response.status_code == 403
