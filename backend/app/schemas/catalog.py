from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field, field_validator


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


class CatalogDiscoveryRequest(BaseModel):
    seed_urls: list[str] = Field(min_length=1, max_length=12)
    max_depth: int = Field(default=2, ge=0, le=3)
    max_sources: int = Field(default=80, ge=1, le=250)


class CatalogSourceRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    catalog_course_id: str
    url: str
    discovered_from_url: str | None
    title: str | None
    source_kind: str
    content_type: str | None
    extension: str | None
    status: str
    depth: int
    sha256: str | None
    imported_document_id: str | None
    discovery_note: str | None
    created_at: datetime
    updated_at: datetime


class CatalogSourceStatusUpdate(BaseModel):
    status: str = Field(pattern="^(approved|rejected|candidate)$")


class CatalogAssignmentRequest(BaseModel):
    email: str = Field(min_length=5, max_length=320)

    @field_validator("email")
    @classmethod
    def normalize_email(cls, value: str) -> str:
        normalized = value.strip().lower()
        if "@" not in normalized:
            raise ValueError("Enter a valid account email")
        return normalized


class CatalogSeedSuggestionRequest(BaseModel):
    program_code: str | None = Field(default=None, max_length=20)
    cohort_year: int | None = Field(default=None, ge=2000, le=2100)


class CatalogSeedSuggestionRead(BaseModel):
    institution_code: str
    urls: list[str]
    notes: list[str]
