from __future__ import annotations

from datetime import date, datetime

from pydantic import BaseModel, ConfigDict, Field, model_validator


class CourseCreate(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    exam_date: date | None = None
    target_grade: float | None = Field(default=None, ge=0)
    max_grade: float = Field(default=30.0, gt=0)

    @model_validator(mode="after")
    def validate_target_grade(self) -> CourseCreate:
        if self.target_grade is not None and self.target_grade > self.max_grade:
            raise ValueError("target_grade cannot be greater than max_grade")
        return self


class CourseUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=120)
    exam_date: date | None = None
    target_grade: float | None = Field(default=None, ge=0)
    max_grade: float | None = Field(default=None, gt=0)

    @model_validator(mode="after")
    def validate_target_grade(self) -> CourseUpdate:
        if (
            self.target_grade is not None
            and self.max_grade is not None
            and self.target_grade > self.max_grade
        ):
            raise ValueError("target_grade cannot be greater than max_grade")
        return self


class CourseRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    name: str
    exam_date: date | None
    target_grade: float | None
    max_grade: float
    created_at: datetime
