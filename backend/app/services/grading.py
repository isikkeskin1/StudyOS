from __future__ import annotations

import math
import re
from dataclasses import dataclass
from difflib import SequenceMatcher
from uuid import uuid4

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.diagnostics import DiagnosticQuestion, DiagnosticResponse, DiagnosticSession
from app.models.exam_intelligence import ExamQuestion
from app.models.grading import DiagnosticGradeArtifact, ExamQuestionReference
from app.services.diagnostics import DiagnosticStateError, record_response
from app.services.mistake_intelligence import MistakeInput

_GRADER_NAME = "deterministic-solution-v1"
_TOKEN_RE = re.compile(r"[A-Za-z][A-Za-z0-9']*")
_NUMBER_RE = re.compile(r"(?<!\w)[+-]?\d+(?:[.,]\d+)?(?:e[+-]?\d+)?", re.IGNORECASE)
_UNIT_RE = re.compile(
    r"(?i)(?<![A-Za-z])(?:m/s(?:\^?2|²)?|kg|km|cm|mm|ms|mol|hz|pa|n|j|w|c|v|a|"
    r"ohm|Ω|m|s)(?![A-Za-z])"
)
_STOPWORDS = {
    "a",
    "an",
    "and",
    "are",
    "as",
    "at",
    "be",
    "by",
    "for",
    "from",
    "has",
    "have",
    "in",
    "is",
    "it",
    "of",
    "on",
    "or",
    "that",
    "the",
    "their",
    "then",
    "this",
    "to",
    "use",
    "using",
    "was",
    "with",
}


class ReferenceSolutionUnavailableError(RuntimeError):
    pass


@dataclass(frozen=True)
class AutomaticGradeResult:
    score: float
    grader_confidence: float
    evidence_coverage: float
    feedback: str
    mistakes: list[MistakeInput]


def _tokens(text: str) -> list[str]:
    return [
        token.lower()
        for token in _TOKEN_RE.findall(text)
        if token.lower() not in _STOPWORDS and len(token) > 1
    ]


def _numbers(text: str) -> list[float]:
    values: list[float] = []
    for raw in _NUMBER_RE.findall(text):
        try:
            values.append(float(raw.replace(",", ".")))
        except ValueError:
            continue
    return values


def _units(text: str) -> set[str]:
    return {match.group(0).lower() for match in _UNIT_RE.finditer(text)}


def _number_coverage(reference: list[float], student: list[float]) -> float:
    if not reference:
        return 1.0
    matched = 0
    unused = list(student)
    for expected in reference:
        for index, actual in enumerate(unused):
            if math.isclose(actual, expected, rel_tol=1e-3, abs_tol=1e-6):
                matched += 1
                unused.pop(index)
                break
    return matched / len(reference)


def _has_sign_mismatch(reference: list[float], student: list[float]) -> bool:
    for expected in reference:
        if expected >= 0:
            continue
        if any(
            actual > 0
            and math.isclose(actual, abs(expected), rel_tol=1e-3, abs_tol=1e-6)
            for actual in student
        ):
            return True
    return False


def _ordered_reference_terms(reference_text: str, question_text: str) -> list[str]:
    question_terms = set(_tokens(question_text))
    ordered: list[str] = []
    seen: set[str] = set()
    for token in _tokens(reference_text):
        if token in question_terms or token in seen:
            continue
        seen.add(token)
        ordered.append(token)
    if ordered:
        return ordered
    for token in _tokens(reference_text):
        if token not in seen:
            seen.add(token)
            ordered.append(token)
    return ordered


def grade_against_reference(
    question_text: str,
    reference_text: str,
    student_answer: str,
    *,
    reference_confidence: float,
) -> AutomaticGradeResult:
    reference_terms = _ordered_reference_terms(reference_text, question_text)
    student_terms = set(_tokens(student_answer))
    matched_terms = [term for term in reference_terms if term in student_terms]
    content_coverage = (
        len(matched_terms) / len(reference_terms)
        if reference_terms
        else SequenceMatcher(
            None,
            student_answer.strip().lower(),
            reference_text.strip().lower(),
        ).ratio()
    )

    reference_numbers = _numbers(reference_text)
    student_numbers = _numbers(student_answer)
    numeric_coverage = _number_coverage(reference_numbers, student_numbers)

    reference_units = _units(reference_text)
    student_units = _units(student_answer)
    unit_coverage = (
        len(reference_units & student_units) / len(reference_units)
        if reference_units
        else 1.0
    )

    components: list[tuple[float, float]] = [(content_coverage, 0.70)]
    if reference_numbers:
        components.append((numeric_coverage, 0.20))
    if reference_units:
        components.append((unit_coverage, 0.10))
    total_weight = sum(weight for _, weight in components)
    score = sum(value * weight for value, weight in components) / total_weight
    score = round(min(1.0, max(0.0, score)), 4)

    evidence_coverage = 0.70
    if reference_numbers:
        evidence_coverage += 0.20
    if reference_units:
        evidence_coverage += 0.10
    grader_confidence = min(
        0.78,
        0.42
        + 0.25 * max(0.0, min(1.0, reference_confidence))
        + 0.10 * evidence_coverage,
    )
    grader_confidence = round(grader_confidence, 4)

    missing_terms = [term for term in reference_terms if term not in student_terms][:5]
    feedback_parts: list[str] = []
    if score >= 0.85:
        feedback_parts.append("Strong match to the extracted reference solution.")
    elif score >= 0.60:
        feedback_parts.append("Partial match to the extracted reference solution.")
    else:
        feedback_parts.append("Weak match to the extracted reference solution.")
    if missing_terms:
        feedback_parts.append("Missing solution terms: " + ", ".join(missing_terms) + ".")
    if reference_numbers and numeric_coverage < 1.0:
        feedback_parts.append("One or more reference numerical results were not matched.")
    if reference_units and unit_coverage < 1.0:
        feedback_parts.append("One or more expected units were not matched.")
    feedback_parts.append(
        "This is a deterministic lexical/numeric grade and should be treated as provisional."
    )

    mistakes: list[MistakeInput] = []
    if score < 0.35 and content_coverage < 0.35:
        mistakes.append(
            MistakeInput(
                category="concept",
                severity=round(min(1.0, 0.55 + (0.35 - content_coverage)), 4),
                source="automatic",
                note="Answer has little overlap with the extracted solution concepts.",
            )
        )
    elif content_coverage < 0.75:
        mistakes.append(
            MistakeInput(
                category="incomplete_reasoning",
                severity=round(min(1.0, 1.0 - content_coverage), 4),
                source="automatic",
                note="Answer covers only part of the extracted solution evidence.",
            )
        )

    if reference_numbers and numeric_coverage < 1.0:
        category = "sign" if _has_sign_mismatch(reference_numbers, student_numbers) else "arithmetic"
        mistakes.append(
            MistakeInput(
                category=category,
                severity=round(min(1.0, 1.0 - numeric_coverage), 4),
                source="automatic",
                note="Numerical result differs from the extracted reference solution.",
            )
        )

    if reference_units and unit_coverage < 1.0:
        mistakes.append(
            MistakeInput(
                category="units",
                severity=round(min(1.0, 1.0 - unit_coverage), 4),
                source="automatic",
                note="Expected units are missing or differ from the reference solution.",
            )
        )

    return AutomaticGradeResult(
        score=score,
        grader_confidence=grader_confidence,
        evidence_coverage=round(evidence_coverage, 4),
        feedback=" ".join(feedback_parts),
        mistakes=mistakes,
    )


def get_question_reference(
    db: Session,
    exam_question_id: str,
) -> ExamQuestionReference | None:
    return db.scalar(
        select(ExamQuestionReference).where(
            ExamQuestionReference.question_id == exam_question_id
        )
    )


def get_grade_artifact(
    db: Session,
    response_id: str,
) -> DiagnosticGradeArtifact | None:
    return db.scalar(
        select(DiagnosticGradeArtifact).where(
            DiagnosticGradeArtifact.response_id == response_id
        )
    )


def grade_diagnostic_response(
    db: Session,
    session: DiagnosticSession,
    diagnostic_question_id: str,
    student_answer: str,
    *,
    confidence: float,
    duration_seconds: int | None,
) -> DiagnosticResponse:
    if session.status != "active":
        raise DiagnosticStateError("Diagnostic session is already completed")

    diagnostic_question = db.get(DiagnosticQuestion, diagnostic_question_id)
    if diagnostic_question is None or diagnostic_question.session_id != session.id:
        raise DiagnosticStateError("Diagnostic question does not belong to this session")

    exam_question = db.get(ExamQuestion, diagnostic_question.exam_question_id)
    if exam_question is None:
        raise DiagnosticStateError("Source exam question is no longer available")

    reference = get_question_reference(db, exam_question.id)
    if reference is None:
        raise ReferenceSolutionUnavailableError(
            "No extracted reference solution is available for this diagnostic question"
        )

    result = grade_against_reference(
        exam_question.text,
        reference.reference_text,
        student_answer,
        reference_confidence=reference.confidence,
    )
    response, _ = record_response(
        db,
        session,
        diagnostic_question_id,
        result.score,
        confidence,
        "automatic",
        duration_seconds,
        student_answer=student_answer,
        reference_answer=reference.reference_text,
        feedback=result.feedback,
        mistakes=result.mistakes,
    )

    db.add(
        DiagnosticGradeArtifact(
            id=str(uuid4()),
            response_id=response.id,
            grader_name=_GRADER_NAME,
            grader_confidence=result.grader_confidence,
            evidence_coverage=result.evidence_coverage,
            reference_source_label=reference.source_label,
            reference_extraction_method=reference.extraction_method,
        )
    )
    db.commit()
    return response
