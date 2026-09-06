export type ExamDayQuestion = {
  id: string;
  sequence: number;
  question_label: string;
  source_label: string;
  text: string;
  marks: number | null;
  topic_name: string | null;
  automatic_grading_available: boolean;
  answer_text: string;
  flagged: boolean;
  self_score: number | null;
  confidence: number;
  score: number | null;
  grading_source: string | null;
  feedback: string | null;
};

export type ExamDaySession = {
  id: string;
  course_id: string;
  status: "active" | "submitted" | "expired";
  duration_minutes: number;
  question_count: number;
  total_known_marks: number;
  answered_count: number;
  flagged_count: number;
  started_at: string;
  submitted_at: string | null;
  expires_at: string;
  remaining_seconds: number;
  questions: ExamDayQuestion[];
};

export type ExamDayResult = {
  session_id: string;
  status: string;
  answered_count: number;
  question_count: number;
  average_score: number | null;
  earned_known_marks: number;
  total_known_marks: number;
  automatic_grade_count: number;
  self_grade_count: number;
  topic_breakdown: Array<{
    topic_id: string | null;
    topic_name: string;
    question_count: number;
    average_score: number;
  }>;
  questions: ExamDayQuestion[];
};
