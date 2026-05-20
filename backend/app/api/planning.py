from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.models.course import Course
from app.models.course_intelligence import CourseTopic
from app.models.exam_intelligence import (
    ExamAnalysis,
    ExamQuestion,
    ExamQuestionTopic,
    ExamTopicStat,
)
from app.schemas.planning import (
    ExamIntelligenceRead,
    ExamQuestionRead,
    ExamQuestionTopicRead,
    ExamTopicStatRead,
    StudyPlanRead,
    StudyPlanRequest,
)
from app.services.exam_analysis import (
    CourseTopicsRequiredError,
    NoExamDocumentsError,
    analyze_exams,
)
from app.services.planning import StudyPlanUnavailableError, build_study_plan

router = APIRouter(prefix="/courses", tags=["exam intelligence", "planning"])


def _get_course(db: Session, course_id: str) -> Course:
    course = db.get(Course, course_id)
    if course is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Course not found")
    return course


def _exam_analysis_is_stale(db: Session, course_id: str) -> bool:
    stats = list(
        db.scalars(select(ExamTopicStat).where(ExamTopicStat.course_id == course_id)).all()
    )
    if not stats:
        return False
    current_topic_ids = set(
        db.scalars(select(CourseTopic.id).where(CourseTopic.course_id == course_id)).all()
    )
    return any(stat.topic_id not in current_topic_ids for stat in stats)


def _read_exam_intelligence(db: Session, course_id: str) -> ExamIntelligenceRead:
    analysis = db.get(ExamAnalysis, course_id)
    if analysis is None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Past exams have not been analyzed",
        )
    if _exam_analysis_is_stale(db, course_id):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Course topics changed; rerun past-exam analysis",
        )

    topics = list(
        db.scalars(select(CourseTopic).where(CourseTopic.course_id == course_id)).all()
    )
    topic_name_by_id = {topic.id: topic.name for topic in topics}
    questions = list(
        db.scalars(
            select(ExamQuestion)
            .where(ExamQuestion.course_id == course_id)
            .order_by(ExamQuestion.document_id, ExamQuestion.question_index)
        ).all()
    )
    question_ids = [question.id for question in questions]
    mappings_by_question: dict[str, list[ExamQuestionTopic]] = {
        question_id: [] for question_id in question_ids
    }
    if question_ids:
        for mapping in db.scalars(
            select(ExamQuestionTopic)
            .where(ExamQuestionTopic.question_id.in_(question_ids))
            .order_by(ExamQuestionTopic.relevance_score.desc())
        ).all():
            mappings_by_question[mapping.question_id].append(mapping)

    stats = list(
        db.scalars(
            select(ExamTopicStat)
            .where(ExamTopicStat.course_id == course_id)
            .order_by(ExamTopicStat.exam_weight.desc())
        ).all()
    )

    return ExamIntelligenceRead(
        course_id=course_id,
        exam_document_count=analysis.exam_document_count,
        question_count=analysis.question_count,
        marked_question_count=analysis.marked_question_count,
        total_known_marks=analysis.total_known_marks,
        questions=[
            ExamQuestionRead(
                id=question.id,
                document_id=question.document_id,
                question_index=question.question_index,
                question_label=question.question_label,
                source_label=question.source_label,
                text=question.text,
                marks=question.marks,
                topics=[
                    ExamQuestionTopicRead(
                        topic_id=mapping.topic_id,
                        topic_name=topic_name_by_id[mapping.topic_id],
                        relevance_score=mapping.relevance_score,
                        allocated_marks=mapping.allocated_marks,
                    )
                    for mapping in mappings_by_question[question.id]
                    if mapping.topic_id in topic_name_by_id
                ],
            )
            for question in questions
        ],
        topics=[
            ExamTopicStatRead(
                topic_id=stat.topic_id,
                topic_name=topic_name_by_id[stat.topic_id],
                question_count=stat.question_count,
                known_marks=stat.known_marks,
                question_share=stat.question_share,
                mark_share=stat.mark_share,
                exam_weight=stat.exam_weight,
            )
            for stat in stats
            if stat.topic_id in topic_name_by_id
        ],
    )


@router.post("/{course_id}/exam-intelligence/analyze", response_model=ExamIntelligenceRead)
def analyze_course_exams(
    course_id: str,
    db: Annotated[Session, Depends(get_db)],
) -> ExamIntelligenceRead:
    _get_course(db, course_id)
    try:
        analyze_exams(db, course_id)
    except (CourseTopicsRequiredError, NoExamDocumentsError) as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    return _read_exam_intelligence(db, course_id)


@router.get("/{course_id}/exam-intelligence", response_model=ExamIntelligenceRead)
def get_course_exam_intelligence(
    course_id: str,
    db: Annotated[Session, Depends(get_db)],
) -> ExamIntelligenceRead:
    _get_course(db, course_id)
    return _read_exam_intelligence(db, course_id)


@router.post("/{course_id}/study-plan", response_model=StudyPlanRead)
def generate_study_plan(
    course_id: str,
    payload: StudyPlanRequest,
    db: Annotated[Session, Depends(get_db)],
) -> StudyPlanRead:
    course = _get_course(db, course_id)

    exam_analysis = db.get(ExamAnalysis, course_id)
    if exam_analysis is None or _exam_analysis_is_stale(db, course_id):
        try:
            analyze_exams(db, course_id)
        except NoExamDocumentsError:
            pass
        except CourseTopicsRequiredError as exc:
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc

    try:
        return build_study_plan(db, course, payload)
    except StudyPlanUnavailableError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
