from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field

CheatSheetItemKind = Literal["formula", "method", "key_point"]


class CheatSheetGenerateRequest(BaseModel):
    max_topics: int = Field(default=8, ge=1, le=20)
    max_items_per_topic: int = Field(default=3, ge=1, le=6)
    include_mistakes: bool = True
    title: str | None = Field(default=None, min_length=1, max_length=200)


class CheatSheetCitationRead(BaseModel):
    document_id: str
    chunk_id: str
    source_label: str
    filename: str
    quote: str


class CheatSheetItemRead(BaseModel):
    kind: CheatSheetItemKind
    text: str
    confidence: float
    citations: list[CheatSheetCitationRead]


class CheatSheetMistakeWarningRead(BaseModel):
    category: str
    mistake_burden: float
    source_label: str = "StudyOS graded practice history"


class CheatSheetSectionRead(BaseModel):
    topic_id: str
    topic_name: str
    priority_score: float
    importance_score: float
    exam_weight: float
    mastery: float | None
    mistake_burden: float
    items: list[CheatSheetItemRead]
    mistake_warnings: list[CheatSheetMistakeWarningRead]


class CheatSheetSourceRead(BaseModel):
    document_id: str
    filename: str
    source_labels: list[str]


class CheatSheetRead(BaseModel):
    id: str
    course_id: str
    title: str
    topic_count: int
    item_count: int
    source_count: int
    generation_config: dict
    sections: list[CheatSheetSectionRead]
    source_manifest: list[CheatSheetSourceRead]
    generated_at: datetime
