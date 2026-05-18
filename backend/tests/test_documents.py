from __future__ import annotations

import hashlib

from fastapi.testclient import TestClient


def create_course(client: TestClient) -> str:
    response = client.post("/api/v1/courses", json={"name": "Physics I"})
    assert response.status_code == 201
    return response.json()["id"]


def test_upload_document_and_list_metadata(client: TestClient) -> None:
    course_id = create_course(client)
    content = b"Newton's second law: F = ma"

    response = client.post(
        f"/api/v1/courses/{course_id}/documents",
        files={"file": ("lecture-01.txt", content, "text/plain")},
    )

    assert response.status_code == 201
    document = response.json()
    assert document["original_filename"] == "lecture-01.txt"
    assert document["extension"] == ".txt"
    assert document["size_bytes"] == len(content)
    assert document["sha256"] == hashlib.sha256(content).hexdigest()
    assert document["status"] == "uploaded"
    assert "storage_path" not in document

    list_response = client.get(f"/api/v1/courses/{course_id}/documents")
    assert list_response.status_code == 200
    assert list_response.json() == [document]


def test_duplicate_document_is_rejected(client: TestClient) -> None:
    course_id = create_course(client)
    payload = b"same file"

    first = client.post(
        f"/api/v1/courses/{course_id}/documents",
        files={"file": ("notes.txt", payload, "text/plain")},
    )
    second = client.post(
        f"/api/v1/courses/{course_id}/documents",
        files={"file": ("notes-copy.txt", payload, "text/plain")},
    )

    assert first.status_code == 201
    assert second.status_code == 409


def test_unsupported_document_type_is_rejected(client: TestClient) -> None:
    course_id = create_course(client)

    response = client.post(
        f"/api/v1/courses/{course_id}/documents",
        files={"file": ("malware.exe", b"nope", "application/octet-stream")},
    )

    assert response.status_code == 415


def test_upload_to_missing_course_returns_404(client: TestClient) -> None:
    response = client.post(
        "/api/v1/courses/missing/documents",
        files={"file": ("notes.txt", b"hello", "text/plain")},
    )

    assert response.status_code == 404


def test_oversized_document_is_rejected(client: TestClient) -> None:
    course_id = create_course(client)
    payload = b"x" * (1024 * 1024 + 1)

    response = client.post(
        f"/api/v1/courses/{course_id}/documents",
        files={"file": ("huge.txt", payload, "text/plain")},
    )

    assert response.status_code == 413
