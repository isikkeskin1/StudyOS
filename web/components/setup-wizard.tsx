"use client";

import { FormEvent, useEffect, useMemo, useState } from "react";

import type { Course, CourseDocument, CourseSetup } from "@/lib/setup-types";

type Step = 1 | 2 | 3 | 4;

async function json<T>(url: string, init?: RequestInit): Promise<T> {
  const response = await fetch(url, { ...init, cache: "no-store" });
  if (!response.ok) {
    let detail = `${response.status} ${response.statusText}`;
    try {
      const body = (await response.json()) as { detail?: string };
      if (body.detail) detail = body.detail;
    } catch {}
    throw new Error(detail);
  }
  return (await response.json()) as T;
}

export function SetupWizard({ onReady }: { onReady: () => void }) {
  const [step, setStep] = useState<Step>(1);
  const [courses, setCourses] = useState<Course[]>([]);
  const [course, setCourse] = useState<Course | null>(null);
  const [setup, setSetup] = useState<CourseSetup | null>(null);
  const [documents, setDocuments] = useState<CourseDocument[]>([]);
  const [files, setFiles] = useState<File[]>([]);
  const [name, setName] = useState("");
  const [examDate, setExamDate] = useState("");
  const [targetGrade, setTargetGrade] = useState("25");
  const [maxGrade, setMaxGrade] = useState("30");
  const [availableHours, setAvailableHours] = useState("12");
  const [blockMinutes, setBlockMinutes] = useState("30");
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  const refreshCourse = async (courseId: string) => {
    const [status, docs] = await Promise.all([
      json<CourseSetup>(`/api/v1/courses/${courseId}/setup`),
      json<CourseDocument[]>(`/api/v1/courses/${courseId}/documents`),
    ]);
    setSetup(status);
    setDocuments(docs);
    if (status.ready_for_planning) setStep(4);
    else if (status.next_step === "analyze_course") setStep(3);
    else if (status.next_step === "process_documents") setStep(2);
  };

  useEffect(() => {
    void json<Course[]>("/api/v1/courses")
      .then(setCourses)
      .catch(() => setCourses([]));
  }, []);

  const progress = useMemo(() => ((step - 1) / 3) * 100, [step]);

  const createCourse = async (event: FormEvent) => {
    event.preventDefault();
    const parsedMax = Number(maxGrade);
    const parsedTarget = targetGrade ? Number(targetGrade) : null;
    if (!name.trim()) {
      setError("Enter a course name.");
      return;
    }
    if (!Number.isFinite(parsedMax) || parsedMax <= 0) {
      setError("Grade scale must be greater than zero.");
      return;
    }
    if (
      parsedTarget !== null
      && (!Number.isFinite(parsedTarget) || parsedTarget < 0 || parsedTarget > parsedMax)
    ) {
      setError("Target grade must be between zero and the grade scale.");
      return;
    }

    setBusy(true);
    setError(null);
    try {
      const created = await json<Course>("/api/v1/courses", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          name: name.trim(),
          exam_date: examDate || null,
          target_grade: parsedTarget,
          max_grade: parsedMax,
        }),
      });
      setCourse(created);
      setCourses((current) => [created, ...current]);
      await refreshCourse(created.id);
      setStep(2);
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "Could not create course.");
    } finally {
      setBusy(false);
    }
  };

  const resumeCourse = async (selected: Course) => {
    setBusy(true);
    setError(null);
    try {
      setCourse(selected);
      await refreshCourse(selected.id);
      if (!setup?.ready_for_planning) setStep(2);
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "Could not load course setup.");
    } finally {
      setBusy(false);
    }
  };

  const importFiles = async () => {
    if (!course || !files.length) return;
    setBusy(true);
    setError(null);
    setMessage(null);
    try {
      for (const file of files) {
        const form = new FormData();
        form.append("file", file);
        const uploaded = await json<CourseDocument>(`/api/v1/courses/${course.id}/documents`, {
          method: "POST",
          body: form,
        });
        await json(`/api/v1/courses/${course.id}/documents/${uploaded.id}/process`, {
          method: "POST",
        });
      }
      setFiles([]);
      await refreshCourse(course.id);
      setStep(3);
      setMessage("Materials imported and processed.");
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "Import failed.");
    } finally {
      setBusy(false);
    }
  };

  const analyze = async () => {
    if (!course) return;
    setBusy(true);
    setError(null);
    try {
      await json(`/api/v1/courses/${course.id}/analyze`, { method: "POST" });
      await refreshCourse(course.id);
      setStep(4);
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "Analysis failed.");
    } finally {
      setBusy(false);
    }
  };

  const createPlan = async () => {
    if (!course) return;
    const hours = Number(availableHours);
    const minutes = Number(blockMinutes);
    if (!Number.isFinite(hours) || hours < 0.5 || hours > 336) {
      setError("Available study time must be between 0.5 and 336 hours.");
      return;
    }
    if (![30, 45, 60, 90].includes(minutes)) {
      setError("Choose a supported focus block length.");
      return;
    }

    setBusy(true);
    setError(null);
    try {
      await json("/api/v1/semester-queues", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          available_hours: hours,
          block_minutes: minutes,
          courses: [{ course_id: course.id, use_stored_mastery: true }],
        }),
      });
      onReady();
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "Could not create study queue.");
    } finally {
      setBusy(false);
    }
  };

  return (
    <main className="setup-shell">
      <section className="setup-card">
        <header className="setup-header">
          <div className="brand setup-brand">
            <span className="brand-mark">S</span>
            <span><strong>StudyOS</strong><small>First run</small></span>
          </div>
          <span className="setup-step">Step {step} of 4</span>
        </header>
        <div className="setup-progress"><span style={{ width: `${progress}%` }} /></div>

        {error && <div className="error-banner" role="alert"><span>{error}</span></div>}
        {message && <div className="setup-message">{message}</div>}

        {step === 1 && (
          <>
            <p className="eyebrow">Course setup</p>
            <h1>Build your first study command center.</h1>
            <p className="setup-copy">Add the exam target first. StudyOS will ground the plan in your own material next.</p>
            <form className="setup-form" onSubmit={createCourse}>
              <label>Course name<input required value={name} onChange={(e) => setName(e.target.value)} placeholder="Physics I" /></label>
              <div className="setup-row">
                <label>Exam date<input type="date" value={examDate} onChange={(e) => setExamDate(e.target.value)} /></label>
                <label>Target grade<input type="number" min="0" step="0.1" value={targetGrade} onChange={(e) => setTargetGrade(e.target.value)} /></label>
                <label>Grade scale<input type="number" min="1" step="0.1" value={maxGrade} onChange={(e) => setMaxGrade(e.target.value)} /></label>
              </div>
              <button className="primary-button" disabled={busy}>{busy ? "Creating…" : "Create course"}</button>
            </form>
            {courses.length > 0 && (
              <div className="resume-box">
                <span>Or continue an existing course</span>
                <div className="resume-list">
                  {courses.slice(0, 4).map((item) => (
                    <button key={item.id} type="button" onClick={() => void resumeCourse(item)} disabled={busy}>
                      <strong>{item.name}</strong><small>{item.exam_date ?? "No exam date"}</small>
                    </button>
                  ))}
                </div>
              </div>
            )}
          </>
        )}

        {step === 2 && course && (
          <>
            <p className="eyebrow">Ground the system</p>
            <h1>Import {course.name} materials.</h1>
            <p className="setup-copy">Upload lecture notes, PDFs, DOCX, PPTX, TXT, or past exams. StudyOS processes every file before it can influence planning.</p>
            <label className="drop-zone">
              <input type="file" multiple accept=".pdf,.docx,.pptx,.txt" onChange={(e) => setFiles(Array.from(e.target.files ?? []))} />
              <strong>{files.length ? `${files.length} file${files.length === 1 ? "" : "s"} selected` : "Choose course files"}</strong>
              <span>PDF · DOCX · PPTX · TXT</span>
            </label>
            {documents.length > 0 && <p className="setup-file-count">{documents.length} material{documents.length === 1 ? "" : "s"} already attached.</p>}
            <div className="setup-actions">
              <button className="ghost-button" type="button" onClick={() => setStep(1)}>Back</button>
              <button className="primary-button" type="button" disabled={busy || !files.length} onClick={() => void importFiles()}>
                {busy ? "Processing…" : "Upload & process"}
              </button>
            </div>
          </>
        )}

        {step === 3 && course && (
          <>
            <p className="eyebrow">Course intelligence</p>
            <h1>Turn source material into a topic map.</h1>
            <p className="setup-copy">StudyOS will extract evidence-backed topics, relationships, and exam-weight signals from the processed files. Re-running analysis replaces the previous map.</p>
            <div className="setup-summary">
              <div><span>Materials</span><strong>{setup?.document_count ?? documents.length}</strong></div>
              <div><span>Processed</span><strong>{setup?.processed_document_count ?? 0}</strong></div>
              <div><span>Target</span><strong>{course.target_grade ?? "—"} / {course.max_grade}</strong></div>
            </div>
            <div className="setup-actions">
              <button className="ghost-button" type="button" onClick={() => setStep(2)}>Add more files</button>
              <button className="primary-button" type="button" disabled={busy || !setup?.processed_document_count} onClick={() => void analyze()}>
                {busy ? "Analyzing…" : "Analyze course"}
              </button>
            </div>
          </>
        )}

        {step === 4 && course && (
          <>
            <p className="eyebrow">Ready to execute</p>
            <h1>{course.name} is grounded.</h1>
            <p className="setup-copy">Choose the study budget you can actually spend. StudyOS will create the first executable semester queue from the analyzed course.</p>
            <div className="setup-summary">
              <div><span>Sources</span><strong>{setup?.document_count ?? 0}</strong></div>
              <div><span>Analysis</span><strong>{setup?.course_analyzed ? "Ready" : "Pending"}</strong></div>
              <div><span>Exam</span><strong>{course.exam_date ?? "Unscheduled"}</strong></div>
            </div>
            <div className="setup-row planning-row">
              <label>Available hours<input type="number" min="0.5" max="336" step="0.5" value={availableHours} onChange={(e) => setAvailableHours(e.target.value)} /></label>
              <label>Focus block<select value={blockMinutes} onChange={(e) => setBlockMinutes(e.target.value)}><option value="30">30 min</option><option value="45">45 min</option><option value="60">60 min</option><option value="90">90 min</option></select></label>
            </div>
            <div className="setup-actions">
              <button className="ghost-button" type="button" onClick={() => setStep(2)}>Add more files</button>
              <button className="primary-button" type="button" disabled={busy} onClick={() => void createPlan()}>
                {busy ? "Optimizing…" : "Create my study plan"}
              </button>
            </div>
          </>
        )}
      </section>
    </main>
  );
}
