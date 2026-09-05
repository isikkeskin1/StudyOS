from __future__ import annotations

import json
from types import SimpleNamespace

import pytest

from app.services.practice_grading import (
    OpenAIRubricPracticeGrader,
    grade_practice_answer,
)
from app.services.tutor_provider import (
    TutorProviderConfig,
    TutorProviderFailure,
    TutorProviderUnavailable,
)


class _FakeResponses:
    def __init__(self, payload: dict) -> None:
        self.payload = payload

    def create(self, **kwargs):
        assert kwargs["store"] is False
        return SimpleNamespace(output_text=json.dumps(self.payload))


class _FakeClient:
    def __init__(self, payload: dict) -> None:
        self.responses = _FakeResponses(payload)


def _full_credit_payload() -> dict:
    return {
        "criteria": [
            {
                "criterion": "Identify the governing relationship",
                "max_points": 3,
                "awarded_points": 3,
                "rationale": (
                    "The answer states an equivalent force-mass-acceleration relationship."
                ),
                "mistake_category": None,
                "mistake_severity": None,
            },
            {
                "criterion": "Apply the relationship correctly",
                "max_points": 3,
                "awarded_points": 3,
                "rationale": "The rearrangement is mathematically equivalent to the reference.",
                "mistake_category": None,
                "mistake_severity": None,
            },
            {
                "criterion": "State the result with units",
                "max_points": 2,
                "awarded_points": 2,
                "rationale": "The final result and units are correct.",
                "mistake_category": None,
                "mistake_severity": None,
            },
        ],
        "confidence": 0.88,
        "feedback": "Correct method and result; the alternative wording is fully equivalent.",
    }


def test_rubric_grader_accepts_equivalent_free_response_without_lexical_scoring() -> None:
    grader = OpenAIRubricPracticeGrader(
        api_key="test-key",
        model="gpt-test",
        client=_FakeClient(_full_credit_payload()),
    )

    result = grader.grade(
        question="State Newton's second law and determine the force.",
        reference_solution="Use F = ma. The force is 10 N.",
        student_answer=(
            "The resultant interaction equals inertial mass times the rate of change of velocity. "
            "Applying that relation gives ten newtons."
        ),
        marks=8,
    )

    assert result.score == 1.0
    assert result.grading_mode == "rubric-ai-v1"
    assert result.total_awarded == 8
    assert result.total_possible == 8
    assert len(result.criteria) == 3
    assert result.mistakes == []


def test_rubric_grader_rejects_invalid_mark_total() -> None:
    payload = _full_credit_payload()
    payload["criteria"][-1]["max_points"] = 1
    payload["criteria"][-1]["awarded_points"] = 1
    grader = OpenAIRubricPracticeGrader(
        api_key="test-key",
        model="gpt-test",
        client=_FakeClient(payload),
    )

    with pytest.raises(TutorProviderFailure, match="item is worth 8"):
        grader.grade(
            question="Question",
            reference_solution="Reference",
            student_answer="Answer",
            marks=8,
        )


def test_rubric_mistakes_are_deduplicated_by_strongest_category() -> None:
    payload = {
        "criteria": [
            {
                "criterion": "Setup",
                "max_points": 4,
                "awarded_points": 2,
                "rationale": "The first rearrangement contains an algebra error.",
                "mistake_category": "algebra",
                "mistake_severity": 0.5,
            },
            {
                "criterion": "Calculation",
                "max_points": 4,
                "awarded_points": 1,
                "rationale": "The same algebra issue propagates into the final calculation.",
                "mistake_category": "algebra",
                "mistake_severity": 0.8,
            },
        ],
        "confidence": 0.8,
        "feedback": "The method is identifiable, but the algebra needs correction.",
    }
    grader = OpenAIRubricPracticeGrader(
        api_key="test-key",
        model="gpt-test",
        client=_FakeClient(payload),
    )

    result = grader.grade(
        question="Solve the problem.",
        reference_solution="Use the correct algebra.",
        student_answer="I rearranged the equation incorrectly.",
        marks=8,
    )

    assert result.score == 0.375
    assert len(result.mistakes) == 1
    assert result.mistakes[0].category == "algebra"
    assert result.mistakes[0].severity == 0.8


def test_auto_grading_falls_back_local_but_explicit_openai_requires_key() -> None:
    config = TutorProviderConfig(openai_api_key=None)
    local = grade_practice_answer(
        requested_provider="auto",
        config=config,
        question="State Newton's second law.",
        reference_solution="Force equals mass times acceleration.",
        student_answer="Force equals mass times acceleration.",
        marks=4,
        reference_confidence=0.9,
    )

    assert local.grading_mode == "deterministic-reference-v1"
    assert local.grader_name == "deterministic-practice-solution-v1"

    with pytest.raises(TutorProviderUnavailable, match="OPENAI_API_KEY"):
        grade_practice_answer(
            requested_provider="openai",
            config=config,
            question="State Newton's second law.",
            reference_solution="Force equals mass times acceleration.",
            student_answer="Force equals mass times acceleration.",
            marks=4,
            reference_confidence=0.9,
        )
