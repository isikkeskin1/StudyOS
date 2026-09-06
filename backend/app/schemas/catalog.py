from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class CatalogCourseCreate(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    institution_name: str = Field(min_length=2, max_length=180)
    institution_code: str | None = Field(default=None, max_length=40)
    course_code: str | None = Field(default=None, max_length=80)
    academic_year: str | None = Field(default=None, max_length=32)
    language: str | None = Field(default=None, max_length=40)
    description: str | None = Field(default=None, max_length=4000)
    max_grade: float = Field(default=30.0, gt=0)


class CatalogCourseRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    source_course_id: str
    institution_name: str
    institution_code: str | None
    course_code: str | None
    academic_year: str | None
    language: str | None
    description: str | None
    published: bool
    created_at: datetime
    updated_at: datetime
    name: str
    document_count: int
