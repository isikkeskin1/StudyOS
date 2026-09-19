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


def _fake_fetch(
    _client,
    url: str,
    *,
    allowed_hosts: set[str],
    max_bytes: int = 25 * 1024 * 1024,
):
    del allowed_hosts, max_bytes
    pages = {
        "https://didattica.polito.test/physics": FetchedSource(
            url=url,
            content=(
                b"<html><head><title>Physics I - Politecnico di Torino</title></head>"
                b"<body>"
                b"<a href='/files/lecture-notes.txt'>Lecture slides</a>"
                b"<a href='/files/exercises.txt'>Exercises</a>"
                b"<a href='/files/2025-written-exam.txt'>Past exam</a>"
                b"</body></html>"
            ),
            content_type="text/html",
        ),
        "https://didattica.polito.test/files/lecture-notes.txt": FetchedSource(
            url=url,
            content=(
                b"Newton's Laws\n"
                b"Newton's second law relates force, mass, and acceleration.\n\n"
                b"Momentum\n"
                b"Momentum is conserved in isolated systems."
            ),
            content_type="text/plain",
        ),
        "https://didattica.polito.test/files/exercises.txt": FetchedSource(
            url=url,
            content=(
                b"Physics I Exercises\n"
                b"Exercise 1: calculate force using Newton's second law.\n"
                b"Exercise 2: determine momentum after a collision."
            ),
            content_type="text/plain",
        ),
        "https://didattica.polito.test/files/2025-written-exam.txt": FetchedSource(
            url=url,
            content=(
                b"Physics I Written Exam\n"
                b"Question 1 (10 marks)\n"
                b"Calculate the net force using Newton's second law.\n\n"
                b"Question 2 (10 marks)\n"
                b"Use conservation of momentum to solve the collision."
            ),
            content_type="text/plain",
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

        importable = [
            item
            for item in source_payload
            if item["source_kind"] in {"lecture", "exercise", "past_exam"}
        ]
        assert len(importable) == 3
        for source in importable:
            approved = client.patch(
                (
                    f"/api/v1/admin/catalog/courses/{catalog_id}/sources/"
                    f"{source['id']}"
                ),
                json={"status": "approved"},
            )
            assert approved.status_code == 200
            assert approved.json()["status"] == "approved"

        imported = client.post(
            f"/api/v1/admin/catalog/courses/{catalog_id}/import-approved"
        )
        assert imported.status_code == 200
        assert len(imported.json()) == 3

        refreshed = client.get(
            f"/api/v1/admin/catalog/courses/{catalog_id}/sources"
        ).json()
        assert sum(item["status"] == "imported" for item in refreshed) == 3

        master_course_id = created.json()["source_course_id"]
        intelligence = client.get(
            f"/api/v1/courses/{master_course_id}/intelligence"
        )
        assert intelligence.status_code == 200

        exam_intelligence = client.get(
            f"/api/v1/courses/{master_course_id}/exam-intelligence"
        )
        assert exam_intelligence.status_code == 200
        assert exam_intelligence.json()["question_count"] == 2


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
