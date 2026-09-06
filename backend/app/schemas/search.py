from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

SearchKind = Literal[
    "course",
    "topic",
    "source",
    "practice",
    "mistake",
    "cheat_sheet",
    "forecast",
]


class GlobalSearchResultRead(BaseModel):
    kind: SearchKind
    id: str
    course_id: str
    course_name: str
    title: str
    subtitle: str | None = None
    excerpt: str | None = None
    score: float = Field(ge=0)
    href: str


class GlobalSearchRead(BaseModel):
    query: str
    result_count: int
    results: list[GlobalSearchResultRead]
