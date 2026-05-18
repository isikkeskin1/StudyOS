from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict


class TopicEvidenceRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    document_id: str
    chunk_id: str
    source_label: str
    snippet: str
    evidence_score: float


class CourseTopicRead(BaseModel):
    id: str
    name: str
    normalized_name: str
    importance_score: float
    mention_count: int
    document_count: int
    exam_mention_count: int
    lecture_mention_count: int
    evidence: list[TopicEvidenceRead]


class TopicRelationshipRead(BaseModel):
    source_topic_id: str
    source_topic_name: str
    target_topic_id: str
    target_topic_name: str
    cooccurrence_count: int
    weight: float


class CourseAnalysisRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    course_id: str
    analyzed_document_count: int
    topic_count: int
    relationship_count: int
    generated_at: datetime


class CourseIntelligenceRead(BaseModel):
    analysis: CourseAnalysisRead
    topics: list[CourseTopicRead]
    relationships: list[TopicRelationshipRead]
