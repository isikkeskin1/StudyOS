export type Course = {
  id: string;
  name: string;
  exam_date: string | null;
  target_grade: number | null;
  max_grade: number;
  created_at: string;
};

export type CourseDocument = {
  id: string;
  course_id: string;
  original_filename: string;
  content_type: string | null;
  extension: string;
  size_bytes: number;
  sha256: string;
  status: string;
  created_at: string;
};

export type CourseSetup = {
  course_id: string;
  course_name: string;
  exam_date: string | null;
  target_grade: number | null;
  max_grade: number;
  document_count: number;
  processed_document_count: number;
  failed_document_count: number;
  course_analyzed: boolean;
  ready_for_planning: boolean;
  next_step: "upload_documents" | "process_documents" | "analyze_course" | "ready";
};
