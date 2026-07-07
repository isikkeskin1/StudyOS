from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient

from app.core.config import Settings
from app.main import create_app


def _app(tmp_path: Path):
    settings = Settings(
        database_url=f"sqlite:///{tmp_path / 'auth.db'}",
        data_dir=tmp_path / "uploads",
        max_upload_mb=1,
    )
    return create_app(settings)


def test_register_login_me_and_logout(tmp_path: Path) -> None:
    app = _app(tmp_path)
    with TestClient(app) as client:
        register = client.post(
            "/api/v1/auth/register",
            json={"email": "Student@Example.com", "password": "secure-pass-123"},
        )
        assert register.status_code == 201
        assert register.json()["user"]["email"] == "student@example.com"
        assert "studyos_session" in client.cookies

        me = client.get("/api/v1/auth/me")
        assert me.status_code == 200
        assert me.json()["email"] == "student@example.com"

        logout = client.post("/api/v1/auth/logout")
        assert logout.status_code == 204
        assert client.get("/api/v1/auth/me").status_code == 401

        login = client.post(
            "/api/v1/auth/login",
            json={"email": "student@example.com", "password": "secure-pass-123"},
        )
        assert login.status_code == 200
        assert client.get("/api/v1/auth/me").status_code == 200


def test_duplicate_registration_and_bad_password_are_rejected(tmp_path: Path) -> None:
    app = _app(tmp_path)
    with TestClient(app) as client:
        payload = {"email": "student@example.com", "password": "secure-pass-123"}
        assert client.post("/api/v1/auth/register", json=payload).status_code == 201
        assert client.post("/api/v1/auth/register", json=payload).status_code == 409

        client.cookies.clear()
        bad = client.post(
            "/api/v1/auth/login",
            json={"email": payload["email"], "password": "wrong-password"},
        )
        assert bad.status_code == 401


def test_courses_are_strictly_isolated_between_accounts(tmp_path: Path) -> None:
    app = _app(tmp_path)
    with TestClient(app) as first, TestClient(app) as second:
        assert first.post(
            "/api/v1/auth/register",
            json={"email": "first@example.com", "password": "first-password"},
        ).status_code == 201
        first_course = first.post(
            "/api/v1/courses",
            json={"name": "First Physics", "target_grade": 25, "max_grade": 30},
        )
        assert first_course.status_code == 201
        first_course_id = first_course.json()["id"]

        assert second.post(
            "/api/v1/auth/register",
            json={"email": "second@example.com", "password": "second-password"},
        ).status_code == 201
        second_course = second.post(
            "/api/v1/courses",
            json={"name": "Second Chemistry", "target_grade": 26, "max_grade": 30},
        )
        assert second_course.status_code == 201
        second_course_id = second_course.json()["id"]

        first_list = first.get("/api/v1/courses")
        second_list = second.get("/api/v1/courses")
        assert [item["id"] for item in first_list.json()] == [first_course_id]
        assert [item["id"] for item in second_list.json()] == [second_course_id]

        assert first.get(f"/api/v1/courses/{second_course_id}").status_code == 404
        assert second.get(f"/api/v1/courses/{first_course_id}").status_code == 404


def test_protected_api_requires_authentication(tmp_path: Path) -> None:
    app = _app(tmp_path)
    with TestClient(app) as client:
        assert client.get("/api/v1/courses").status_code == 401
        assert client.get("/api/v1/semester/dashboard").status_code == 401


def test_nested_documents_are_isolated_between_accounts(tmp_path: Path) -> None:
    app = _app(tmp_path)
    with TestClient(app) as first, TestClient(app) as second:
        assert first.post(
            "/api/v1/auth/register",
            json={"email": "owner@example.com", "password": "owner-password"},
        ).status_code == 201
        course = first.post(
            "/api/v1/courses",
            json={"name": "Private Physics", "target_grade": 25, "max_grade": 30},
        ).json()
        uploaded = first.post(
            f"/api/v1/courses/{course['id']}/documents",
            files={"file": ("notes.txt", b"private mechanics notes", "text/plain")},
        )
        assert uploaded.status_code == 201
        document_id = uploaded.json()["id"]

        assert second.post(
            "/api/v1/auth/register",
            json={"email": "intruder@example.com", "password": "intruder-password"},
        ).status_code == 201

        base = f"/api/v1/courses/{course['id']}/documents/{document_id}"
        assert second.get(base).status_code == 404
        assert second.get(f"{base}/content").status_code == 404
        assert second.post(f"{base}/process").status_code == 404
        assert second.delete(base).status_code == 404

        assert first.get(base).status_code == 200


def test_account_export_is_scoped_and_redacts_credentials(tmp_path: Path) -> None:
    app = _app(tmp_path)
    with TestClient(app) as client:
        assert client.post(
            "/api/v1/auth/register",
            json={"email": "export@example.com", "password": "export-password"},
        ).status_code == 201
        course = client.post(
            "/api/v1/courses",
            json={"name": "Export Physics", "target_grade": 25, "max_grade": 30},
        )
        assert course.status_code == 201

        exported = client.get("/api/v1/auth/export")
        assert exported.status_code == 200
        payload = exported.json()
        assert payload["format"] == "studyos-account-export-v1"
        assert payload["account"]["email"] == "export@example.com"
        assert payload["source_files_included"] is False
        assert payload["tables"]["courses"][0]["name"] == "Export Physics"

        serialized = str(payload).lower()
        assert "password_hash" not in serialized
        assert "token_hash" not in serialized
        assert "storage_path" not in serialized


def test_account_deletion_removes_login_and_uploaded_files(tmp_path: Path) -> None:
    app = _app(tmp_path)
    with TestClient(app) as client:
        credentials = {
            "email": "delete@example.com",
            "password": "delete-password",
        }
        assert client.post("/api/v1/auth/register", json=credentials).status_code == 201
        course = client.post(
            "/api/v1/courses",
            json={"name": "Delete Physics", "target_grade": 25, "max_grade": 30},
        ).json()
        uploaded = client.post(
            f"/api/v1/courses/{course['id']}/documents",
            files={"file": ("delete.txt", b"delete me", "text/plain")},
        )
        assert uploaded.status_code == 201

        stored_files = list((tmp_path / "uploads" / course["id"]).iterdir())
        assert len(stored_files) == 1
        assert stored_files[0].exists()

        wrong = client.request(
            "DELETE",
            "/api/v1/auth/account",
            json={"password": "wrong-password", "confirmation": "DELETE"},
        )
        assert wrong.status_code == 403
        assert client.get("/api/v1/auth/me").status_code == 200

        deleted = client.request(
            "DELETE",
            "/api/v1/auth/account",
            json={"password": credentials["password"], "confirmation": "DELETE"},
        )
        assert deleted.status_code == 204
        assert not stored_files[0].exists()
        assert client.get("/api/v1/auth/me").status_code == 401

        login = client.post("/api/v1/auth/login", json=credentials)
        assert login.status_code == 401
