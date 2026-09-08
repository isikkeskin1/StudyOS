from __future__ import annotations

import io
import zipfile
from pathlib import Path

from fastapi.testclient import TestClient

from app.core.config import Settings
from app.main import create_app


def _app(tmp_path: Path):
    return create_app(
        Settings(
            environment="test",
            database_url=f"sqlite:///{tmp_path / 'catalog-library.db'}",
            data_dir=tmp_path / "uploads",
            max_upload_mb=2,
            admin_emails=("admin@studyos.local",),
        )
    )


def _register(client: TestClient, email: str, password: str) -> None:
    response = client.post(
        "/api/v1/auth/register",
        json={"email": email, "password": password},
    )
    assert response.status_code == 201


def test_admin_builds_nested_library_and_student_downloads_pack(tmp_path: Path) -> None:
    app = _app(tmp_path)

    with TestClient(app) as admin, TestClient(app) as student:
        _register(admin, "admin@studyos.local", "admin-password-123")
        created = admin.post(
            "/api/v1/admin/catalog/courses",
            json={
                "name": "Physics I",
                "institution_name": "Politecnico di Torino",
                "institution_code": "POLITO",
                "course_code": "02KPN",
                "academic_year": "2026/27",
                "language": "English",
                "max_grade": 30,
            },
        )
        assert created.status_code == 201
        catalog = created.json()
        catalog_id = catalog["id"]

        lectures = admin.post(
            f"/api/v1/admin/catalog/courses/{catalog_id}/folders",
            json={"name": "Lectures", "parent_id": None},
        )
        assert lectures.status_code == 201
        lectures_id = lectures.json()["id"]

        week_one = admin.post(
            f"/api/v1/admin/catalog/courses/{catalog_id}/folders",
            json={"name": "Week 01", "parent_id": lectures_id},
        )
        assert week_one.status_code == 201
        week_one_id = week_one.json()["id"]

        uploaded = admin.post(
            (
                f"/api/v1/admin/catalog/courses/{catalog_id}/documents"
                f"?folder_id={week_one_id}"
            ),
            files={
                "file": (
                    "newton.txt",
                    (
                        b"Newton's Laws\n"
                        b"Force equals mass times acceleration.\n\n"
                        b"Momentum\n"
                        b"Impulse changes momentum in a collision."
                    ),
                    "text/plain",
                )
            },
        )
        assert uploaded.status_code == 201
        document_id = uploaded.json()["id"]
        assert uploaded.json()["folder_id"] == week_one_id
        assert uploaded.json()["status"] == "processed"

        published = admin.post(
            f"/api/v1/admin/catalog/courses/{catalog_id}/publish"
        )
        assert published.status_code == 200
        assert published.json()["published"] is True

        _register(student, "student@example.com", "student-password-123")

        root = student.get(f"/api/v1/catalog/courses/{catalog_id}/library")
        assert root.status_code == 200
        assert root.headers["x-frame-options"] == "DENY"
        assert [folder["name"] for folder in root.json()["folders"]] == ["Lectures"]
        assert root.json()["documents"] == []

        lectures_view = student.get(
            f"/api/v1/catalog/courses/{catalog_id}/library?folder_id={lectures_id}"
        )
        assert lectures_view.status_code == 200
        assert [folder["name"] for folder in lectures_view.json()["folders"]] == [
            "Week 01"
        ]
        assert [entry["name"] for entry in lectures_view.json()["breadcrumbs"]] == [
            "Lectures"
        ]

        week_view = student.get(
            f"/api/v1/catalog/courses/{catalog_id}/library?folder_id={week_one_id}"
        )
        assert week_view.status_code == 200
        assert [entry["name"] for entry in week_view.json()["breadcrumbs"]] == [
            "Lectures",
            "Week 01",
        ]
        assert [document["id"] for document in week_view.json()["documents"]] == [
            document_id
        ]

        file_response = student.get(
            f"/api/v1/catalog/courses/{catalog_id}/documents/{document_id}/file"
        )
        assert file_response.status_code == 200
        assert file_response.headers["x-frame-options"] == "SAMEORIGIN"
        assert b"Force equals mass times acceleration" in file_response.content
        assert "inline" in file_response.headers["content-disposition"]

        pack = student.post(
            f"/api/v1/catalog/courses/{catalog_id}/download-pack",
            json={"document_ids": [document_id]},
        )
        assert pack.status_code == 200
        assert pack.headers["content-type"].startswith("application/zip")
        with zipfile.ZipFile(io.BytesIO(pack.content)) as archive:
            assert archive.namelist() == ["Lectures/Week 01/newton.txt"]
            assert b"Impulse changes momentum" in archive.read(
                "Lectures/Week 01/newton.txt"
            )


def test_non_admin_cannot_mutate_institutional_library(tmp_path: Path) -> None:
    app = _app(tmp_path)

    with TestClient(app) as admin, TestClient(app) as student:
        _register(admin, "admin@studyos.local", "admin-password-123")
        created = admin.post(
            "/api/v1/admin/catalog/courses",
            json={
                "name": "Programming Techniques",
                "institution_name": "Politecnico di Torino",
                "institution_code": "POLITO",
            },
        )
        assert created.status_code == 201
        catalog_id = created.json()["id"]

        _register(student, "student@example.com", "student-password-123")
        forbidden = student.post(
            f"/api/v1/admin/catalog/courses/{catalog_id}/folders",
            json={"name": "Private", "parent_id": None},
        )
        assert forbidden.status_code == 403
