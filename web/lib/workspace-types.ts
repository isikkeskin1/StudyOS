import type { Course, CourseDocument, CourseSetup } from "@/lib/setup-types";

export type TopicEvidence = {
  document_id: string;
  chunk_id: string;
  source_label: string;
  snippet: string;
  evidence_score: number;
};

export type CourseTopic = {
  id: string;
  name: string;
  normalized_name: string;
  importance_score: number;
  mention_count: number;
  document_count: number;
  exam_mention_count: number;
  lecture_mention_count: number;
  evidence: TopicEvidence[];
};

export type CourseIntelligence = {
  analysis: {
    course_id: string;
    analyzed_document_count: number;
    topic_count: number;
    relationship_count: number;
    generated_at: string;
  };
  topics: CourseTopic[];
  relationships: Array<{
    source_topic_id: string;
    source_topic_name: string;
    target_topic_id: string;
    target_topic_name: string;
    cooccurrence_count: number;
    weight: number;
  }>;
};

export type TopicMastery = {
  topic_id: string;
  topic_name: string;
  mastery: number;
  confidence: number;
  evidence_weight: number;
  response_count: number;
  updated_at: string;
};

export type MistakeIntel = {
  course_id: string;
  response_count: number;
  responses_with_mistakes: number;
  lost_score_total: number;
  classified_loss_total: number;
  classification_coverage: number;
  categories: Array<{
    category: string;
    occurrences: number;
    weighted_lost_score: number;
    share_of_classified_loss: number;
  }>;
  topics: Array<{
    topic_id: string;
    topic_name: string;
    mistake_burden: number;
    dominant_categories: string[];
  }>;
};

export type ForecastSnapshot = {
  id: string;
  label: string | null;
  exam_date: string | null;
  expected_grade: number;
  max_grade: number;
  target_grade: number;
  target_probability: number;
  likely_range_low: number;
  likely_range_high: number;
  evidence_confidence: string;
  created_at: string;
};

export type CheatSheet = {
  id: string;
  title: string;
  topic_count: number;
  item_count: number;
  source_count: number;
  generated_at: string;
  sections: Array<{
    topic_id: string;
    topic_name: string;
    priority_score: number;
    mastery: number | null;
    mistake_burden: number;
    items: Array<{
      kind: "formula" | "method" | "key_point";
      text: string;
      confidence: number;
      citations: Array<{
        source_label: string;
        filename: string;
        quote: string;
      }>;
    }>;
    mistake_warnings: Array<{
      category: string;
      mistake_burden: number;
    }>;
  }>;
};

export type TutorAnswer = {
  answer: string;
  grounding_status: "supported" | "insufficient_evidence";
  citation_coverage: number;
  grounding_score: number;
  citations: Array<{
    source_reference: string;
    document_name: string;
    source_label: string;
    excerpt: string;
    relevance_score: number;
  }>;
  note: string;
};

export type PracticeItem = {
  id: string;
  topic: string;
  difficulty: "easy" | "medium" | "hard";
  marks: number;
  question: string;
  hint_count: number;
  hints_revealed: number;
  solution_revealed: boolean;
  source_references: string[];
};

export type PracticeEvaluation = {
  score: number;
  feedback: string;
  mistakes: Array<{ category: string; severity: number; note: string | null }>;
  next_strategy: string;
  next_reason: string;
};

export type WorkspaceData = {
  course: Course;
  setup: CourseSetup;
  documents: CourseDocument[];
  intelligence: CourseIntelligence | null;
  mastery: TopicMastery[];
  mistakes: MistakeIntel;
  forecasts: ForecastSnapshot[];
  cheatSheets: CheatSheet[];
};


export type DiagnosticSession = {
  id: string;
  course_id: string;
  status: string;
  requested_question_count: number;
  selected_question_count: number;
  answered_question_count: number;
  created_at: string;
  completed_at: string | null;
};

export type DiagnosticQuestion = {
  id: string;
  exam_question_id: string;
  sequence: number;
  question_label: string;
  source_label: string;
  text: string;
  marks: number | null;
  difficulty: number;
  primary_topic_id: string;
  primary_topic_name: string;
  automatic_grading_available: boolean;
  topics: Array<{
    topic_id: string;
    topic_name: string;
    relevance_score: number;
  }>;
};

export type DiagnosticNext = {
  session: DiagnosticSession;
  question: DiagnosticQuestion | null;
};

export type DiagnosticResponse = {
  id: string;
  diagnostic_question_id: string;
  score: number;
  confidence: number;
  grading_source: string;
  duration_seconds: number | null;
  created_at: string;
  answer: {
    student_answer: string | null;
    reference_answer: string | null;
    feedback: string | null;
  } | null;
  mistakes: Array<{
    category: string;
    severity: number;
    source: string;
    note: string | null;
  }>;
  session: DiagnosticSession;
  mastery: TopicMastery[];
};

export type DiagnosticSummary = {
  session_id: string;
  course_id: string;
  status: string;
  answered_question_count: number;
  average_score: number | null;
  average_confidence: number | null;
  total_duration_seconds: number;
  automatic_grade_count: number;
  self_grade_count: number;
  topic_summaries: Array<{
    topic_id: string;
    topic_name: string;
    question_count: number;
    average_score: number;
  }>;
  mistakes: Array<{
    category: string;
    occurrences: number;
    average_severity: number;
  }>;
};
