from __future__ import annotations

from pydantic import BaseModel, Field, model_validator


class ExamQuestionTopicRead(BaseModel):
    topic_id: str
    topic_name: str
    relevance_score: float
    allocated_marks: float | None


class ExamQuestionRead(BaseModel):
    id: str
    document_id: str
    question_index: int
    question_label: str
    source_label: str
    text: str
    marks: float | None
    automatic_grading_available: bool = False
    topics: list[ExamQuestionTopicRead]


class ExamTopicStatRead(BaseModel):
    topic_id: str
    topic_name: str
    question_count: int
    known_marks: float
    question_share: float
    mark_share: float
    exam_weight: float


class ExamIntelligenceRead(BaseModel):
    course_id: str
    exam_document_count: int
    question_count: int
    marked_question_count: int
    total_known_marks: float
    questions: list[ExamQuestionRead]
    topics: list[ExamTopicStatRead]


class StudyPlanRequest(BaseModel):
    target_grade: float | None = Field(default=None, ge=0)
    available_hours: float | None = Field(default=None, ge=0, le=500)
    baseline_mastery: float = Field(default=0.5, ge=0, le=1)
    topic_mastery: dict[str, float] = Field(default_factory=dict)
    use_stored_mastery: bool = True

    @model_validator(mode="after")
    def validate_topic_mastery(self) -> StudyPlanRequest:
        invalid = [key for key, value in self.topic_mastery.items() if not 0 <= value <= 1]
        if invalid:
            raise ValueError("topic_mastery values must be between 0 and 1")
        return self


class TopicStudyAllocationRead(BaseModel):
    topic_id: str
    topic_name: str
    exam_weight: float
    current_mastery: float
    mastery_source: str
    raw_mastery: float | None = None
    forgetting_loss: float = 0.0
    forgetting_risk: str | None = None
    days_since_evidence: float | None = None
    retention_half_life_days: float | None = None
    projected_mastery: float
    recommended_hours: float
    priority_score: float
    mistake_burden: float = 0.0
    mistake_focus: list[str] = Field(default_factory=list)
    learning_rate_multiplier: float = 1.0
    learning_scale_hours: float = 2.8
    learning_calibration_confidence: str = "low"
    retention_calibration_confidence: str = "low"
    calibration_source: str = "heuristic"


class GradeScenarioRead(BaseModel):
    study_hours: float
    projected_grade: float
    projected_ratio: float


class StudyPlanRead(BaseModel):
    course_id: str
    planning_model: str
    confidence: str
    target_grade: float
    max_grade: float
    current_estimated_grade: float
    estimated_hours_to_target: float | None
    available_hours: float | None
    projected_grade_with_available_hours: float | None
    target_reachable_with_available_time: bool | None
    calibrated_learning_topic_count: int = 0
    calibrated_retention_topic_count: int = 0
    allocations: list[TopicStudyAllocationRead]
    scenarios: list[GradeScenarioRead]
    assumptions: list[str]
