from __future__ import annotations

import json
from types import SimpleNamespace

from fastapi.testclient import TestClient

from app.schemas.tutor import TutorCitationRead
from app.services.tutor_practice import OpenAIPracticeProvider


def _create_course(client: TestClient, name: str = "Physics I") -> str:
    response = client.post(
        "/api/v1/courses",
        json={"name": name, "target_grade": 25, "max_grade": 30},
    )
    assert response.status_code == 201
    return response.json()["id"]


def _upload_and_process(
    client: TestClient,
    course_id: str,
    filename: str,
    content: bytes,
) -> None:
    upload = client.post(
        f"/api/v1/courses/{course_id}/documents",
        files={"file": (filename, content, "text/plain")},
    )
    assert upload.status_code == 201
    document_id = upload.json()["id"]
    assert (
        client.post(f"/api/v1/courses/{course_id}/documents/{document_id}/process").status_code
        == 200
    )


def _prepare_solution_course(client: TestClient) -> str:
    course_id = _create_course(client)
    _upload_and_process(
        client,
        course_id,
        "lecture-mechanics.txt",
        (
            b"Force\n"
            b"Force depends on mass and acceleration. Force is measured in newtons. "
            b"Force and acceleration are central to Newton's second law.\n\n"
            b"Momentum\n"
            b"Momentum is conserved in collisions. Momentum equals mass times velocity."
        ),
    )
    _upload_and_process(
        client,
        course_id,
        "2025-written-exam-solutions.txt",
        (
            b"Physics I Written Exam Solutions\n"
            b"Question 1 (8 marks)\n"
            b"State Newton's second law and calculate the force.\n"
            b"Solution: Newton's second law says force equals mass times acceleration. "
            b"The force is 10 N.\n\n"
            b"Question 2 (12 marks)\n"
            b"Use conservation of momentum to determine the final momentum.\n"
            b"Solution: Momentum is conserved, so initial momentum equals final momentum. "
            b"The final momentum is 20 kg m/s."
        ),
    )
    assert client.post(f"/api/v1/courses/{course_id}/analyze").status_code == 200
    assert (
        client.post(f"/api/v1/courses/{course_id}/exam-intelligence/analyze").status_code
        == 200
    )
    return course_id


def test_local_practice_hides_solution_and_reveals_hints_progressively(
    client: TestClient,
) -> None:
    course_id = _prepare_solution_course(client)

    created = client.post(
        f"/api/v1/courses/{course_id}/tutor/practice",
        json={"provider": "local", "difficulty": "medium"},
    )

    assert created.status_code == 201
    body = created.json()
    assert body["generation_mode"] == "past-exam-reuse-v1"
    assert body["generation_provider"] == "local-past-exam-v1"
    assert body["hint_count"] == 3
    assert body["hints_revealed"] == 0
    assert body["solution_revealed"] is False
    assert "solution" not in body
    practice_id = body["id"]

    first = client.post(f"/api/v1/courses/{course_id}/tutor/practice/{practice_id}/hint")
    second = client.post(f"/api/v1/courses/{course_id}/tutor/practice/{practice_id}/hint")
    third = client.post(f"/api/v1/courses/{course_id}/tutor/practice/{practice_id}/hint")
    exhausted = client.post(
        f"/api/v1/courses/{course_id}/tutor/practice/{practice_id}/hint"
    )

    assert [first.json()["level"], second.json()["level"], third.json()["level"]] == [1, 2, 3]
    assert first.json()["remaining_hints"] == 2
    assert third.json()["remaining_hints"] == 0
    assert exhausted.status_code == 409


def test_practice_solution_is_revealed_separately_with_sources(client: TestClient) -> None:
    course_id = _prepare_solution_course(client)
    created = client.post(
        f"/api/v1/courses/{course_id}/tutor/practice",
        json={"provider": "local"},
    )
    practice_id = created.json()["id"]

    solution = client.get(
        f"/api/v1/courses/{course_id}/tutor/practice/{practice_id}/solution"
    )

    assert solution.status_code == 200
    body = solution.json()
    assert body["solution_revealed"] is True
    assert "force" in body["solution"].lower() or "momentum" in body["solution"].lower()
    assert body["sources"]
    assert {source["role"] for source in body["sources"]} >= {"question", "solution"}
    assert all(source["source_reference"] for source in body["sources"])


def test_local_practice_requires_reference_solution(client: TestClient) -> None:
    course_id = _create_course(client)
    _upload_and_process(
        client,
        course_id,
        "lecture.txt",
        (
            b"Momentum Conservation\n"
            b"Momentum conservation states that total momentum remains constant in an isolated "
            b"system. Momentum conservation is useful for collision problems. Momentum equals "
            b"mass times velocity and momentum is a central mechanics quantity."
        ),
    )
    assert client.post(f"/api/v1/courses/{course_id}/analyze").status_code == 200

    response = client.post(
        f"/api/v1/courses/{course_id}/tutor/practice",
        json={"provider": "local"},
    )

    assert response.status_code == 409
    assert "reference solution" in response.json()["detail"].lower()


def test_practice_items_are_course_isolated(client: TestClient) -> None:
    course_id = _prepare_solution_course(client)
    other_course = _create_course(client, "Other")
    created = client.post(
        f"/api/v1/courses/{course_id}/tutor/practice",
        json={"provider": "local"},
    )
    practice_id = created.json()["id"]

    response = client.get(
        f"/api/v1/courses/{other_course}/tutor/practice/{practice_id}/solution"
    )

    assert response.status_code == 404


class _FakeResponses:
    def create(self, **kwargs):
        del kwargs
        payload = {
            "question": "Explain how net force determines acceleration.",
            "hints": [
                "Identify the governing law.",
                "Relate net force, mass, and acceleration.",
                "Write the force-mass-acceleration relationship before substituting values.",
            ],
            "solution": "Net force equals mass times acceleration [1].",
        }
        return SimpleNamespace(output_text=json.dumps(payload))


class _FakeClient:
    def __init__(self) -> None:
        self.responses = _FakeResponses()


def test_openai_practice_provider_validates_structured_solution() -> None:
    citation = TutorCitationRead(
        rank=1,
        document_id="doc",
        document_name="lecture.pdf",
        document_type="lecture",
        chunk_id="chunk",
        source_label="page 2",
        locator_type="page",
        locator_index=2,
        source_reference="lecture.pdf — page 2",
        excerpt="Newton's second law states that net force equals mass times acceleration.",
        relevance_score=0.9,
        lexical_score=0.9,
        semantic_score=0.0,
        topic_affinity=0.0,
        term_coverage=1.0,
        matched_terms=["force", "acceleration"],
    )
    provider = OpenAIPracticeProvider(
        api_key="test-key",
        model="gpt-test",
        max_output_tokens=1200,
        client=_FakeClient(),
    )

    question, hints, solution = provider.generate("Newton's laws", "medium", 6, [citation])

    assert "net force" in question.lower()
    assert len(hints) == 3
    assert solution.endswith("[1].")
