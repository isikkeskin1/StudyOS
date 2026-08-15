from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict


class DocumentRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    course_id: str
    original_filename: str
    content_type: str | None
    extension: str
    size_bytes: int
    sha256: str
    status: str
    created_at: datetime


class DocumentAnalysisRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    document_id: str
    document_type: str
    classifier_confidence: float
    unit_count: int
    chunk_count: int
    extracted_characters: int
    needs_ocr: bool
    processed_at: datetime


class DocumentUnitRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    unit_index: int
    locator_type: str
    locator_index: int | None
    source_label: str
    text: str


class DocumentChunkRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    chunk_index: int
    unit_chunk_index: int
    source_label: str
    text: str
    character_count: int


class DocumentContentRead(BaseModel):
    document: DocumentRead
    analysis: DocumentAnalysisRead
    units: list[DocumentUnitRead]
    chunks: list[DocumentChunkRead]
