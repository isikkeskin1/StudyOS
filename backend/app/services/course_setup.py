from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models.course import Course
from app.models.course_intelligence import CourseAnalysis
from app.models.document import Document
from app.models.document_content import DocumentAnalysis


@dataclass(frozen=True)
class CourseSetupStatus:
    course_id: str
    course_name: str
    exam_date: object | None
    target_grade: float | None
    max_grade: float
    document_count: int
    processed_document_count: int
    failed_document_count: int
    course_analyzed: bool
    ready_for_planning: bool
    next_step: str


def course_setup_status(db: Session, course: Course) -> CourseSetupStatus:
    document_count = db.scalar(
        select(func.count(Document.id)).where(Document.course_id == course.id)
    ) or 0
    processed_document_count = db.scalar(
        select(func.count(DocumentAnalysis.document_id))
        .join(Document, Document.id == DocumentAnalysis.document_id)
        .where(Document.course_id == course.id)
    ) or 0
    failed_document_count = db.scalar(
        select(func.count(Document.id)).where(
            Document.course_id == course.id,
            Document.status == "failed",
        )
    ) or 0
    analyzed = db.get(CourseAnalysis, course.id) is not None

    if document_count == 0:
        next_step = "upload_documents"
    elif processed_document_count < document_count:
        next_step = "process_documents"
    elif not analyzed:
        next_step = "analyze_course"
    else:
        next_step = "ready"

    return CourseSetupStatus(
        course_id=course.id,
        course_name=course.name,
        exam_date=course.exam_date,
        target_grade=course.target_grade,
        max_grade=course.max_grade,
        document_count=document_count,
        processed_document_count=processed_document_count,
        failed_document_count=failed_document_count,
        course_analyzed=analyzed,
        ready_for_planning=next_step == "ready",
        next_step=next_step,
    )
