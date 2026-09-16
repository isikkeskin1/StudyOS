from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient

from app.core.config import Settings
from app.main import create_app
from app.services import catalog_discovery
from app.services.catalog_discovery import FetchedSource


def _app(tmp_path: Path):
    return create_app(
        Settings(
            environment="test",
            database_url=f"sqlite:///{tmp_path / 'discovery.db'}",
            data_dir=tmp_path / "uploads",
            max_upload_mb=2,
            admin_emails=("admin@studyos.local",),
        )
    )


def _fake_fetch(_client, url: str, *, allowed_hosts: set[str], max_bytes: int):
    del allowed_hosts, max_bytes
    pages = {
        "https://didattica.polito.test/physics": FetchedSource(
            url=url,
            content=(
                b"<html><head><title>Physics I - Politecnico di Torino</title></head>"
                b"<body>"
                b"<a href='/files/lecture.pdf'>Lecture slides</a>"
                b"<a href='/files/exercises.pdf'>Exercises</a>"
                b"<a href='/files/2025-written-exam.pdf'>Past exam</a>"
                b"</body></html>"
            ),
            content_type="text/html",
        ),
        "https://didattica.polito.test/files/lecture.pdf": FetchedSource(
            url=url,
            content=b"fake lecture pdf bytes",
            content_type="application/pdf",
        ),
        "https://didattica.polito.test/files/exercises.pdf": FetchedSource(
            url=url,
            content=b"fake exercise pdf bytes",
            content_type="application/pdf",
        ),
        "https://didattica.polito.test/files/2025-written-exam.pdf": FetchedSource(
            url=url,
            content=b"fake exam pdf bytes",
            content_type="application/pdf",
        ),
    }
    return pages[url]


def test_admin_discovers_reviews_and_imports_public_course_sources(
    tmp_path: Path,
    monkeypatch,
) -> None:
    monkeypatch.setattr(
        catalog_discovery,
        "_validate_public_url",
        lambda url, _allowed=None: catalog_discovery._normalize_url(url),
    )
    monkeypatch.setattr(catalog_discovery, "_fetch_public", _fake_fetch)

    app = _app(tmp_path)
    with TestClient(app) as client:
        registered = client.post(
            "/api/v1/auth/register",
            json={
                "email": "admin@studyos.local",
                "password": "admin-password-123",
            },
        )
        assert registered.status_code == 201

        created = client.post(
            "/api/v1/admin/catalog/courses",
            json={
                "name": "Physics I",
                "institution_name": "Politecnico di Torino",
                "institution_code": "POLITO",
                "course_code": "PHYSICS-I",
            },
        )
        assert created.status_code == 201
        catalog_id = created.json()["id"]

        discovered = client.post(
            f"/api/v1/admin/catalog/courses/{catalog_id}/discover",
            json={
                "seed_urls": ["https://didattica.polito.test/physics"],
                "max_depth": 1,
                "max_sources": 20,
            },
        )
        assert discovered.status_code == 200
        payload = discovered.json()
        assert len(payload) == 4

        sources = client.get(
            f"/api/v1/admin/catalog/courses/{catalog_id}/sources"
        )
        assert sources.status_code == 200
        source_payload = sources.json()
        kinds = {item["source_kind"] for item in source_payload}
        assert "lecture" in kinds
        assert "exercise" in kinds
        assert "past_exam" in kinds
        assert "web_page" in kinds

        lecture = next(
            item for item in source_payload if item["source_kind"] == "lecture"
        )
        approved = client.patch(
            f"/api/v1/admin/catalog/courses/{catalog_id}/sources/{lecture['id']}",
            json={"status": "approved"},
        )
        assert approved.status_code == 200
        assert approved.json()["status"] == "approved"


def test_discovery_rejects_private_network_resolution(monkeypatch) -> None:
    monkeypatch.setattr(
        catalog_discovery.socket,
        "getaddrinfo",
        lambda *_args, **_kwargs: [
            (None, None, None, None, ("127.0.0.1", 443))
        ],
    )

    try:
        catalog_discovery._validate_public_url("https://internal.example/course")
    except catalog_discovery.DiscoveryError as exc:
        assert "non-public" in str(exc)
    else:
        raise AssertionError("Private-network source URL was accepted")
