from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient

from app.core.config import Settings
from app.main import create_app


def _app(tmp_path: Path):
    return create_app(
        Settings(
            environment="test",
            database_url=f"sqlite:///{tmp_path / 'catalog-delete.db'}",
            data_dir=tmp_path / "uploads",
            max_upload_mb=2,
            admin_emails=("admin@studyos.local",),
        )
    )


def _register(client: TestClient, email: str) -> None:
    response = client.post(
        "/api/v1/auth/register",
        json={"email": email, "password": "studyos-delete-test-123"},
    )
    assert response.status_code == 201


def _create_catalog(admin: TestClient) -> dict:
    response = admin.post(
        "/api/v1/admin/catalog/courses",
        json={
            "name": "Physics I",
            "institution_name": "Politecnico di Torino",
            "institution_code": "POLITO",
            "course_code": "02KPN",
            "academic_year": "2026/27",
            "language": "English",
            "description": "Deletion test catalog.",
            "max_grade": 30,
        },
    )
    assert response.status_code == 201
    return response.json()


def _upload_library_document(admin: TestClient, catalog_id: str, name: str) -> dict:
    response = admin.post(
        f"/api/v1/admin/catalog/courses/{catalog_id}/documents",
        files={
            "file": (
                name,
                (
                    b"Newton's Laws\n"
                    b"Force equals mass times acceleration and momentum is conserved.\n\n"
                    b"Energy\n"
                    b"Kinetic and potential energy are used to solve mechanics problems.\n"
                ),
                "text/plain",
            )
        },
    )
    assert response.status_code == 201
    assert response.json()["status"] == "processed"
    return response.json()


def test_admin_can_delete_one_resource_then_delete_master_course(tmp_path: Path) -> None:
    app = _app(tmp_path)

    with TestClient(app) as admin, TestClient(app) as student:
        _register(admin, "admin@studyos.local")
        _register(student, "student@studyos.local")

        catalog = _create_catalog(admin)
        catalog_id = catalog["id"]
        source_course_id = catalog["source_course_id"]
        document = _upload_library_document(admin, catalog_id, "mechanics.txt")

        published = admin.post(f"/api/v1/admin/catalog/courses/{catalog_id}/publish")
        assert published.status_code == 200
        assert published.json()["published"] is True

        enrolled = student.post(f"/api/v1/catalog/courses/{catalog_id}/enroll")
        assert enrolled.status_code == 201
        personal_course_id = enrolled.json()["id"]
        personal_documents = student.get(
            f"/api/v1/courses/{personal_course_id}/documents"
        )
        assert personal_documents.status_code == 200
        assert len(personal_documents.json()) == 1

        deleted_resource = admin.delete(
            f"/api/v1/admin/catalog/courses/{catalog_id}/documents/{document['id']}"
        )
        assert deleted_resource.status_code == 204

        admin_courses = admin.get("/api/v1/admin/catalog/courses")
        assert admin_courses.status_code == 200
        remaining = next(row for row in admin_courses.json() if row["id"] == catalog_id)
        assert remaining["document_count"] == 0
        assert remaining["published"] is False

        library = admin.get(f"/api/v1/admin/catalog/courses/{catalog_id}/library")
        assert library.status_code == 200
        assert library.json()["documents"] == []

        source_dir = tmp_path / "uploads" / source_course_id
        assert not any(source_dir.glob("*"))

        # Removing a master resource never destroys copies students already enrolled in.
        personal_documents = student.get(
            f"/api/v1/courses/{personal_course_id}/documents"
        )
        assert personal_documents.status_code == 200
        assert len(personal_documents.json()) == 1

        _upload_library_document(admin, catalog_id, "replacement.txt")
        republished = admin.post(f"/api/v1/admin/catalog/courses/{catalog_id}/publish")
        assert republished.status_code == 200

        deleted_course = admin.delete(f"/api/v1/admin/catalog/courses/{catalog_id}")
        assert deleted_course.status_code == 204

        admin_courses = admin.get("/api/v1/admin/catalog/courses")
        assert admin_courses.status_code == 200
        assert all(row["id"] != catalog_id for row in admin_courses.json())

        owned_courses = admin.get("/api/v1/courses")
        assert owned_courses.status_code == 200
        assert all(row["id"] != source_course_id for row in owned_courses.json())
        assert not source_dir.exists() or not any(source_dir.glob("*"))

        personal_documents = student.get(
            f"/api/v1/courses/{personal_course_id}/documents"
        )
        assert personal_documents.status_code == 200
        assert len(personal_documents.json()) == 1


def test_non_admin_cannot_delete_catalog_data(tmp_path: Path) -> None:
    app = _app(tmp_path)

    with TestClient(app) as admin, TestClient(app) as student:
        _register(admin, "admin@studyos.local")
        _register(student, "student@studyos.local")
        catalog = _create_catalog(admin)
        document = _upload_library_document(admin, catalog["id"], "private.txt")

        assert student.delete(
            f"/api/v1/admin/catalog/courses/{catalog['id']}/documents/{document['id']}"
        ).status_code == 403
        assert student.delete(
            f"/api/v1/admin/catalog/courses/{catalog['id']}"
        ).status_code == 403
