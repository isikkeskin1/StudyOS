from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from io import BytesIO
from pathlib import Path
from zipfile import ZipFile

from fastapi.testclient import TestClient
from sqlalchemy import select

from app.core.config import Settings
from app.main import create_app
from app.models.auth import AuthSession


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


def test_migration_bundle_includes_state_and_source_files(tmp_path: Path) -> None:
    app = _app(tmp_path)
    with TestClient(app) as client:
        assert client.post(
            "/api/v1/auth/register",
            json={"email": "migrate@example.com", "password": "migration-password"},
        ).status_code == 201
        course = client.post(
            "/api/v1/courses",
            json={"name": "Migration Physics", "target_grade": 25, "max_grade": 30},
        ).json()
        uploaded = client.post(
            f"/api/v1/courses/{course['id']}/documents",
            files={"file": ("migration-notes.txt", b"portable source notes", "text/plain")},
        )
        assert uploaded.status_code == 201
        document_id = uploaded.json()["id"]

        response = client.get("/api/v1/auth/migration-bundle")
        assert response.status_code == 200
        assert response.headers["content-type"] == "application/zip"
        assert "attachment;" in response.headers["content-disposition"]

        with ZipFile(BytesIO(response.content)) as bundle:
            names = set(bundle.namelist())
            assert "account.json" in names
            assert "manifest.json" in names
            assert f"files/{document_id}.txt" in names
            assert bundle.read(f"files/{document_id}.txt") == b"portable source notes"

            account = json.loads(bundle.read("account.json"))
            manifest = json.loads(bundle.read("manifest.json"))

        assert account["tables"]["courses"][0]["name"] == "Migration Physics"
        assert account["source_files_included"] is True
        assert manifest["format"] == "studyos-cloud-migration-v1"
        assert manifest["source_files"][0]["included"] is True

        serialized = response.content.lower()
        assert b"password_hash" not in serialized
        assert b"token_hash" not in serialized
        assert b"storage_path" not in serialized
        assert b"password_reset_codes" not in serialized
        assert b"email_verification_codes" not in serialized


def test_migration_bundle_round_trip_into_fresh_account(tmp_path: Path) -> None:
    source_app = _app(tmp_path / "source")
    with TestClient(source_app) as source:
        assert source.post(
            "/api/v1/auth/register",
            json={"email": "source@example.com", "password": "source-password"},
        ).status_code == 201
        course = source.post(
            "/api/v1/courses",
            json={"name": "Portable Physics", "target_grade": 27, "max_grade": 30},
        ).json()
        uploaded = source.post(
            f"/api/v1/courses/{course['id']}/documents",
            files={"file": ("portable.txt", b"migration round trip", "text/plain")},
        )
        assert uploaded.status_code == 201
        bundle = source.get("/api/v1/auth/migration-bundle").content

    target_app = _app(tmp_path / "target")
    with TestClient(target_app) as target:
        assert target.post(
            "/api/v1/auth/register",
            json={"email": "target@example.com", "password": "target-password"},
        ).status_code == 201
        imported = target.post(
            "/api/v1/auth/migration-bundle/import",
            files={"file": ("studyos-migration.zip", bundle, "application/zip")},
        )
        assert imported.status_code == 200
        assert imported.json()["courses"] == 1
        assert imported.json()["files"] == 1

        courses = target.get("/api/v1/courses")
        assert courses.status_code == 200
        assert len(courses.json()) == 1
        assert courses.json()[0]["name"] == "Portable Physics"
        assert courses.json()[0]["id"] != course["id"]

        documents = target.get(f"/api/v1/courses/{courses.json()[0]['id']}/documents")
        assert documents.status_code == 200
        assert len(documents.json()) == 1
        assert documents.json()[0]["original_filename"] == "portable.txt"


def test_migration_import_refuses_nonempty_cloud_account(tmp_path: Path) -> None:
    app = _app(tmp_path)
    with TestClient(app) as client:
        assert client.post(
            "/api/v1/auth/register",
            json={"email": "migration@example.com", "password": "migration-password"},
        ).status_code == 201
        assert client.post(
            "/api/v1/courses",
            json={"name": "Existing cloud course", "max_grade": 30},
        ).status_code == 201

        bundle = client.get("/api/v1/auth/migration-bundle").content
        response = client.post(
            "/api/v1/auth/migration-bundle/import",
            files={"file": ("studyos-migration.zip", bundle, "application/zip")},
        )
        assert response.status_code == 422
        assert "no courses" in response.json()["detail"]


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


def test_expired_session_is_removed_and_cookie_cleared(tmp_path: Path) -> None:
    app = _app(tmp_path)
    with TestClient(app) as client:
        assert client.post(
            "/api/v1/auth/register",
            json={"email": "expired@example.com", "password": "expired-password"},
        ).status_code == 201

        with app.state.session_factory() as db:
            session = db.scalar(select(AuthSession))
            assert session is not None
            session.expires_at = datetime.now(UTC) - timedelta(minutes=1)
            session_id = session.id
            db.commit()

        response = client.get("/api/v1/auth/me")
        assert response.status_code == 401
        assert "studyos_session" not in client.cookies

        with app.state.session_factory() as db:
            assert db.get(AuthSession, session_id) is None


def test_production_style_registration_requires_email_verification(
    tmp_path: Path,
    monkeypatch,
) -> None:
    sent: dict[str, str] = {}

    def fake_send(settings, *, recipient: str, code: str) -> None:
        sent["recipient"] = recipient
        sent["code"] = code

    monkeypatch.setattr("app.api.auth.send_email_verification_code", fake_send)
    settings = Settings(
        database_url=f"sqlite:///{tmp_path / 'verified-auth.db'}",
        data_dir=tmp_path / "uploads",
        max_upload_mb=1,
        require_email_verification=True,
        brevo_api_key="test-brevo-api-key",
        smtp_from_email="support@studyos.courses",
    )
    app = create_app(settings)

    with TestClient(app) as client:
        registered = client.post(
            "/api/v1/auth/register",
            json={"email": "verify@example.com", "password": "verify-password"},
        )
        assert registered.status_code == 201
        assert "studyos_session" not in client.cookies
        assert sent["recipient"] == "verify@example.com"
        assert len(sent["code"]) == 6

        blocked = client.post(
            "/api/v1/auth/login",
            json={"email": "verify@example.com", "password": "verify-password"},
        )
        assert blocked.status_code == 403
        assert blocked.json()["detail"] == "Email verification required"

        wrong = client.post(
            "/api/v1/auth/email-verification/confirm",
            json={"email": "verify@example.com", "code": "000000"},
        )
        assert wrong.status_code == 400

        verified = client.post(
            "/api/v1/auth/email-verification/confirm",
            json={"email": "verify@example.com", "code": sent["code"]},
        )
        assert verified.status_code == 200
        assert verified.json()["user"]["email_verified"] is True
        assert "studyos_session" in client.cookies
        assert client.get("/api/v1/auth/me").status_code == 200


def test_logout_all_revokes_every_session(tmp_path: Path) -> None:
    app = _app(tmp_path)
    credentials = {
        "email": "multi-device@example.com",
        "password": "multi-device-password",
    }

    with TestClient(app) as first, TestClient(app) as second:
        assert first.post("/api/v1/auth/register", json=credentials).status_code == 201
        assert second.post("/api/v1/auth/login", json=credentials).status_code == 200

        sessions = second.get("/api/v1/auth/sessions")
        assert sessions.status_code == 200
        assert len(sessions.json()) == 2
        assert sum(1 for item in sessions.json() if item["current"]) == 1

        logout_all = second.post("/api/v1/auth/logout-all")
        assert logout_all.status_code == 204
        assert first.get("/api/v1/auth/me").status_code == 401
        assert second.get("/api/v1/auth/me").status_code == 401
