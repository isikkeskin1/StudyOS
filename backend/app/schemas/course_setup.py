from __future__ import annotations

from datetime import date
from typing import Literal

from pydantic import BaseModel


class CourseSetupRead(BaseModel):
    course_id: str
    course_name: str
    exam_date: date | None
    target_grade: float | None
    max_grade: float
    document_count: int
    processed_document_count: int
    failed_document_count: int
    course_analyzed: bool
    ready_for_planning: bool
    next_step: Literal["upload_documents", "process_documents", "analyze_course", "ready"]
