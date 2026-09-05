from __future__ import annotations

from collections import Counter, defaultdict
from dataclasses import dataclass
from uuid import uuid4

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.course_intelligence import CourseTopic
from app.models.diagnostics import DiagnosticQuestion, DiagnosticResponse, DiagnosticSession
from app.models.exam_intelligence import ExamQuestionTopic
from app.models.mistakes import DiagnosticAnswerArtifact, DiagnosticMistake
from app.models.tutor_practice import (
    TutorPracticeAttempt,
    TutorPracticeItem,
    TutorPracticeMistake,
)


@dataclass(frozen=True)
class MistakeInput:
    category: str
    severity: float
    source: str
    note: str | None


@dataclass(frozen=True)
class MistakeCategorySummary:
    category: str
    occurrences: int
    weighted_lost_score: float
    share_of_classified_loss: float


@dataclass(frozen=True)
class TopicMistakeSummary:
    topic_id: str
    topic_name: str
    mistake_burden: float
    dominant_categories: list[str]


@dataclass(frozen=True)
class CourseMistakeSummary:
    response_count: int
    responses_with_mistakes: int
    lost_score_total: float
    classified_loss_total: float
    classification_coverage: float
    categories: list[MistakeCategorySummary]
    topics: list[TopicMistakeSummary]


def store_response_details(
    db: Session,
    response_id: str,
    *,
    student_answer: str | None,
    reference_answer: str | None,
    feedback: str | None,
    mistakes: list[MistakeInput],
) -> None:
    if student_answer is not None or reference_answer is not None or feedback is not None:
        db.add(
            DiagnosticAnswerArtifact(
                id=str(uuid4()),
                response_id=response_id,
                student_answer=student_answer,
                reference_answer=reference_answer,
                feedback=feedback,
            )
        )

    for mistake in mistakes:
        db.add(
            DiagnosticMistake(
                id=str(uuid4()),
                response_id=response_id,
                category=mistake.category,
                severity=mistake.severity,
                source=mistake.source,
                note=mistake.note,
            )
        )


def get_response_answer(
    db: Session,
    response_id: str,
) -> DiagnosticAnswerArtifact | None:
    return db.scalar(
        select(DiagnosticAnswerArtifact).where(
            DiagnosticAnswerArtifact.response_id == response_id
        )
    )


def get_response_mistakes(db: Session, response_id: str) -> list[DiagnosticMistake]:
    return list(
        db.scalars(
            select(DiagnosticMistake)
            .where(DiagnosticMistake.response_id == response_id)
            .order_by(DiagnosticMistake.severity.desc(), DiagnosticMistake.category)
        ).all()
    )


def _course_rows(
    db: Session,
    course_id: str,
) -> tuple[
    list[DiagnosticResponse],
    dict[str, DiagnosticQuestion],
    dict[str, list[ExamQuestionTopic]],
]:
    session_ids = list(
        db.scalars(
            select(DiagnosticSession.id).where(DiagnosticSession.course_id == course_id)
        ).all()
    )
    if not session_ids:
        return [], {}, {}

    questions = list(
        db.scalars(
            select(DiagnosticQuestion).where(DiagnosticQuestion.session_id.in_(session_ids))
        ).all()
    )
    question_by_id = {question.id: question for question in questions}
    responses = list(
        db.scalars(
            select(DiagnosticResponse).where(DiagnosticResponse.session_id.in_(session_ids))
        ).all()
    )

    exam_question_ids = list({question.exam_question_id for question in questions})
    mappings: dict[str, list[ExamQuestionTopic]] = defaultdict(list)
    if exam_question_ids:
        for mapping in db.scalars(
            select(ExamQuestionTopic).where(
                ExamQuestionTopic.question_id.in_(exam_question_ids)
            )
        ).all():
            mappings[mapping.question_id].append(mapping)

    return responses, question_by_id, mappings


def _severity_total(mistakes: list) -> float:
    return sum(max(item.severity, 0.01) for item in mistakes)


def summarize_course_mistakes(db: Session, course_id: str) -> CourseMistakeSummary:
    responses, question_by_id, mappings_by_question = _course_rows(db, course_id)
    practice_rows = db.execute(
        select(TutorPracticeAttempt, TutorPracticeItem)
        .join(TutorPracticeItem, TutorPracticeItem.id == TutorPracticeAttempt.practice_id)
        .where(TutorPracticeAttempt.course_id == course_id)
    ).all()
    if not responses and not practice_rows:
        return CourseMistakeSummary(0, 0, 0.0, 0.0, 0.0, [], [])

    response_ids = [response.id for response in responses]
    mistakes_by_response: dict[str, list[DiagnosticMistake]] = defaultdict(list)
    if response_ids:
        for mistake in db.scalars(
            select(DiagnosticMistake).where(DiagnosticMistake.response_id.in_(response_ids))
        ).all():
            mistakes_by_response[mistake.response_id].append(mistake)

    attempt_ids = [attempt.id for attempt, _ in practice_rows]
    mistakes_by_attempt: dict[str, list[TutorPracticeMistake]] = defaultdict(list)
    if attempt_ids:
        for mistake in db.scalars(
            select(TutorPracticeMistake).where(TutorPracticeMistake.attempt_id.in_(attempt_ids))
        ).all():
            mistakes_by_attempt[mistake.attempt_id].append(mistake)

    category_loss: Counter[str] = Counter()
    category_occurrences: Counter[str] = Counter()
    topic_exposure: Counter[str] = Counter()
    topic_loss: Counter[str] = Counter()
    topic_category_loss: dict[str, Counter[str]] = defaultdict(Counter)

    lost_score_total = 0.0
    classified_loss_total = 0.0
    responses_with_mistakes = 0

    for response in responses:
        loss = max(0.0, 1.0 - response.score)
        lost_score_total += loss
        response_mistakes = mistakes_by_response.get(response.id, [])
        if response_mistakes:
            responses_with_mistakes += 1
            classified_loss_total += loss
            severity_total = _severity_total(response_mistakes)
            for item in response_mistakes:
                fraction = max(item.severity, 0.01) / severity_total
                category_loss[item.category] += loss * fraction
                category_occurrences[item.category] += 1

        question = question_by_id.get(response.diagnostic_question_id)
        if question is None:
            continue
        mappings = mappings_by_question.get(question.exam_question_id, [])
        relevance_total = sum(max(item.relevance_score, 0.01) for item in mappings)
        if not response_mistakes or relevance_total <= 0:
            continue

        severity_total = _severity_total(response_mistakes)
        for mapping in mappings:
            relevance = max(mapping.relevance_score, 0.01)
            topic_exposure[mapping.topic_id] += relevance
            topic_loss[mapping.topic_id] += loss * relevance
            for item in response_mistakes:
                mistake_fraction = max(item.severity, 0.01) / severity_total
                topic_category_loss[mapping.topic_id][item.category] += (
                    loss * relevance / relevance_total * mistake_fraction
                )

    for attempt, practice in practice_rows:
        loss = max(0.0, 1.0 - attempt.score)
        lost_score_total += loss
        attempt_mistakes = mistakes_by_attempt.get(attempt.id, [])
        if not attempt_mistakes:
            continue

        responses_with_mistakes += 1
        classified_loss_total += loss
        severity_total = _severity_total(attempt_mistakes)
        for item in attempt_mistakes:
            fraction = max(item.severity, 0.01) / severity_total
            category_loss[item.category] += loss * fraction
            category_occurrences[item.category] += 1

        if practice.topic_id is None:
            continue
        topic_exposure[practice.topic_id] += 1.0
        topic_loss[practice.topic_id] += loss
        for item in attempt_mistakes:
            mistake_fraction = max(item.severity, 0.01) / severity_total
            topic_category_loss[practice.topic_id][item.category] += loss * mistake_fraction

    categories = [
        MistakeCategorySummary(
            category=category,
            occurrences=category_occurrences[category],
            weighted_lost_score=round(weighted_loss, 4),
            share_of_classified_loss=round(
                weighted_loss / classified_loss_total if classified_loss_total else 0.0,
                4,
            ),
        )
        for category, weighted_loss in category_loss.most_common()
    ]

    topic_names = {
        topic.id: topic.name
        for topic in db.scalars(
            select(CourseTopic).where(CourseTopic.course_id == course_id)
        ).all()
    }
    topics: list[TopicMistakeSummary] = []
    for topic_id, exposure in topic_exposure.items():
        if topic_id not in topic_names or exposure <= 0:
            continue
        dominant = [
            category
            for category, _ in topic_category_loss[topic_id].most_common(3)
        ]
        topics.append(
            TopicMistakeSummary(
                topic_id=topic_id,
                topic_name=topic_names[topic_id],
                mistake_burden=round(min(1.0, topic_loss[topic_id] / exposure), 4),
                dominant_categories=dominant,
            )
        )
    topics.sort(key=lambda item: item.mistake_burden, reverse=True)

    return CourseMistakeSummary(
        response_count=len(responses) + len(practice_rows),
        responses_with_mistakes=responses_with_mistakes,
        lost_score_total=round(lost_score_total, 4),
        classified_loss_total=round(classified_loss_total, 4),
        classification_coverage=round(
            classified_loss_total / lost_score_total if lost_score_total else 0.0,
            4,
        ),
        categories=categories,
        topics=topics,
    )


def topic_mistake_signals(
    db: Session,
    course_id: str,
) -> dict[str, tuple[float, list[str]]]:
    summary = summarize_course_mistakes(db, course_id)
    return {
        topic.topic_id: (topic.mistake_burden, topic.dominant_categories)
        for topic in summary.topics
    }
