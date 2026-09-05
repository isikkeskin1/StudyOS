export type TargetStatus = "unconfigured" | "unmeasured" | "below_target" | "at_target";
export type Confidence = "low" | "medium" | "high";

export type AnalyticsActivityDay = {
  date: string;
  focus_minutes: number;
  focus_sessions_completed: number;
  focus_sessions_skipped: number;
  diagnostic_responses: number;
  practice_attempts: number;
  mastery_updates: number;
  forecast_snapshots: number;
};

export type AnalyticsMistakeCategory = {
  category: string;
  occurrences: number;
  weighted_lost_score: number;
  share_of_classified_loss: number;
};

export type AnalyticsTopicRisk = {
  topic_id: string;
  topic_name: string;
  mistake_burden: number;
  dominant_categories: string[];
};

export type AnalyticsCourse = {
  course_id: string;
  course_name: string;
  target_grade: number | null;
  max_grade: number;
  current_estimated_grade: number | null;
  normalized_current_grade: number | null;
  normalized_target_grade: number | null;
  normalized_target_gap: number | null;
  target_status: TargetStatus;
  confidence: Confidence;
  topic_count: number;
  measured_topic_count: number;
  current_mean_mastery: number | null;
  diagnostic_mastery_delta: number | null;
  focus_minutes: number;
  focus_sessions_completed: number;
  focus_sessions_skipped: number;
  focus_completion_rate: number | null;
  answer_count: number;
  average_answer_score: number | null;
  forecast_count: number;
  latest_forecast_grade: number | null;
  latest_target_probability: number | null;
  normalized_forecast_delta: number | null;
  mistake_classification_coverage: number;
  top_mistakes: AnalyticsMistakeCategory[];
  highest_risk_topics: AnalyticsTopicRisk[];
};

export type AnalyticsDashboard = {
  generated_at: string;
  window_days: number;
  timezone: string;
  window_start: string;
  window_end: string;
  course_filter: string | null;
  summary: {
    course_count: number;
    at_target_count: number;
    below_target_count: number;
    unmeasured_count: number;
    focus_minutes: number;
    focus_sessions_completed: number;
    focus_sessions_skipped: number;
    focus_completion_rate: number | null;
    answer_count: number;
    average_answer_score: number | null;
    mastery_updates: number;
    forecast_snapshots: number;
  };
  courses: AnalyticsCourse[];
  activity: AnalyticsActivityDay[];
  assumptions: string[];
};

export type SemesterQueueBlock = {
  id: string;
  revision: number;
  sequence: number;
  course_id: string | null;
  course_name: string;
  topic_id: string | null;
  topic_name: string;
  status: "planned" | "in_progress" | "completed" | "skipped" | "superseded";
  planned_minutes: number;
  actual_minutes: number | null;
  expected_mark_gain: number;
  normalized_target_gap_reduction: number;
  utility_score: number;
  note: string | null;
  started_at: string | null;
  completed_at: string | null;
};

export type SemesterDashboard = {
  generated_at: string;
  course_count: number;
  upcoming_exam_count: number;
  below_target_count: number;
  unmeasured_course_count: number;
  due_review_count: number;
  courses: Array<{
    course_id: string;
    course_name: string;
    exam_date: string | null;
    days_until_exam: number | null;
    deadline_pressure: "unknown" | "past" | "today" | "soon" | "upcoming" | "later";
    target_grade: number | null;
    max_grade: number;
    current_estimated_grade: number | null;
    target_gap: number | null;
    normalized_target_gap: number | null;
    target_status: TargetStatus;
    confidence: string;
    topic_count: number;
    measured_topic_count: number;
    due_review_count: number;
  }>;
  queues: Array<{
    queue_id: string;
    status: string;
    revision: number;
    remaining_available_minutes: number;
    completed_study_minutes: number;
    needs_refresh: boolean;
    refresh_reasons: string[];
    planned_minutes: number;
  }>;
  selected_queue_id: string | null;
  next_action: SemesterQueueBlock | null;
  assumptions: string[];
};

export type FocusSession = {
  id: string;
  queue_id: string;
  block_id: string;
  queue_revision: number;
  status: "active" | "completed" | "skipped";
  planned_minutes: number;
  started_at: string;
  target_end_at: string;
  completed_at: string | null;
  actual_minutes: number | null;
  note: string | null;
};

export type FocusAction = {
  session: FocusSession;
};
