"use client";

import { FormEvent, useEffect, useMemo, useState } from "react";

import type { Course, CourseDocument, CourseSetup } from "@/lib/setup-types";

async function api<T>(url: string, init?: RequestInit): Promise<T> {
  const response = await fetch(url, { ...init, cache: "no-store" });
  if (!response.ok) {
    let detail = `${response.status} ${response.statusText}`;
    try {
      const body = (await response.json()) as { detail?: string };
      if (body.detail) detail = body.detail;
    } catch {
      // Keep the HTTP status fallback when the response body is not JSON.
    }
    throw new Error(detail);
  }
  if (response.status === 204) return undefined as T;
  return (await response.json()) as T;
}

export function CourseManager({
  open,
  onClose,
  onChanged,
}: {
  open: boolean;
  onClose: () => void;
  onChanged: () => void;
}) {
  const [courses, setCourses] = useState<Course[]>([]);
  const [setups, setSetups] = useState<Record<string, CourseSetup>>({});
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [documents, setDocuments] = useState<CourseDocument[]>([]);
  const [files, setFiles] = useState<File[]>([]);
  const [name, setName] = useState("");
  const [examDate, setExamDate] = useState("");
  const [targetGrade, setTargetGrade] = useState("");
  const [maxGrade, setMaxGrade] = useState("30");
  const [newCourse, setNewCourse] = useState(false);
  const [planHours, setPlanHours] = useState("12");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const [deleteConfirmation, setDeleteConfirmation] = useState("");

  const selected = useMemo(
    () => courses.find((course) => course.id === selectedId) ?? null,
    [courses, selectedId],
  );
  const setup = selectedId ? setups[selectedId] : undefined;
  const readyCourses = useMemo(
    () => courses.filter((course) => setups[course.id]?.ready_for_planning),
    [courses, setups],
  );

  const load = async (preferredId?: string | null) => {
    const list = await api<Course[]>("/api/v1/courses");
    const statusPairs = await Promise.all(
      list.map(async (course) => [course.id, await api<CourseSetup>(`/api/v1/courses/${course.id}/setup`)] as const),
    );
    const statusMap = Object.fromEntries(statusPairs);
    setCourses(list);
    setSetups(statusMap);
    const nextId = preferredId === null
      ? list[0]?.id ?? null
      : preferredId ?? selectedId ?? list[0]?.id ?? null;
    setSelectedId(nextId);
    if (nextId) {
      setDocuments(await api<CourseDocument[]>(`/api/v1/courses/${nextId}/documents`));
      const course = list.find((item) => item.id === nextId);
      if (course) fillCourse(course);
    } else {
      setDocuments([]);
    }
  };

  const fillCourse = (course: Course) => {
    setName(course.name);
    setExamDate(course.exam_date ?? "");
    setTargetGrade(course.target_grade === null ? "" : String(course.target_grade));
    setMaxGrade(String(course.max_grade));
  };

  useEffect(() => {
    if (!open) return;
    setError(null);
    setNotice(null);
    void load();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [open]);

  useEffect(() => {
    if (!selectedId || !open) return;
    const course = courses.find((item) => item.id === selectedId);
    if (course) fillCourse(course);
    void api<CourseDocument[]>(`/api/v1/courses/${selectedId}/documents`)
      .then(setDocuments)
      .catch(() => setDocuments([]));
  }, [selectedId, courses, open]);

  if (!open) return null;

  const run = async (work: () => Promise<void>) => {
    setBusy(true);
    setError(null);
    setNotice(null);
    try {
      await work();
      onChanged();
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "Course operation failed.");
    } finally {
      setBusy(false);
    }
  };

  const saveCourse = (event: FormEvent) => {
    event.preventDefault();
    if (!selected) return;
    void run(async () => {
      await api<Course>(`/api/v1/courses/${selected.id}`, {
        method: "PATCH",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          name: name.trim(),
          exam_date: examDate || null,
          target_grade: targetGrade ? Number(targetGrade) : null,
          max_grade: Number(maxGrade),
        }),
      });
      await load(selected.id);
      setNotice("Course settings saved.");
    });
  };

  const createCourse = (event: FormEvent) => {
    event.preventDefault();
    void run(async () => {
      const created = await api<Course>("/api/v1/courses", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          name: name.trim(),
          exam_date: examDate || null,
          target_grade: targetGrade ? Number(targetGrade) : null,
          max_grade: Number(maxGrade),
        }),
      });
      setNewCourse(false);
      await load(created.id);
      setNotice("Course added.");
    });
  };

  const upload = () => {
    if (!selected || !files.length) return;
    void run(async () => {
      for (const file of files) {
        const form = new FormData();
        form.append("file", file);
        const uploaded = await api<CourseDocument>(`/api/v1/courses/${selected.id}/documents`, {
          method: "POST",
          body: form,
        });
        await api(`/api/v1/courses/${selected.id}/documents/${uploaded.id}/process`, {
          method: "POST",
        });
      }
      setFiles([]);
      await load(selected.id);
      setNotice("Materials uploaded and processed. Re-run analysis before planning.");
    });
  };

  const removeDocument = (documentId: string) => {
    if (!selected) return;
    void run(async () => {
      await api(`/api/v1/courses/${selected.id}/documents/${documentId}`, {
        method: "DELETE",
      });
      await load(selected.id);
      setNotice("Material removed. Analysis is now stale until rebuilt.");
    });
  };

  const removeCourse = () => {
    if (!selected || deleteConfirmation !== selected.name) return;
    void run(async () => {
      await api(`/api/v1/courses/${selected.id}`, { method: "DELETE" });
      setDeleteConfirmation("");
      setSelectedId(null);
      await load(null);
      setNotice("Course and its StudyOS data were deleted.");
    });
  };

  const analyze = () => {
    if (!selected) return;
    void run(async () => {
      await api(`/api/v1/courses/${selected.id}/analyze`, { method: "POST" });
      await load(selected.id);
      setNotice("Course intelligence rebuilt from the current source set.");
    });
  };

  const rebuildPlan = () => {
    if (!readyCourses.length) return;
    void run(async () => {
      await api("/api/v1/semester-queues", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          available_hours: Number(planHours),
          block_minutes: 30,
          courses: readyCourses.map((course) => ({
            course_id: course.id,
            use_stored_mastery: true,
          })),
        }),
      });
      setNotice(`New semester queue created from ${readyCourses.length} ready course${readyCourses.length === 1 ? "" : "s"}.`);
    });
  };

  return (
    <div className="manager-backdrop" role="presentation" onMouseDown={(event) => {
      if (event.target === event.currentTarget) onClose();
    }}>
      <section className="manager-panel" role="dialog" aria-modal="true" aria-label="Manage courses">
        <header className="manager-header">
          <div><p className="eyebrow">Course control</p><h2>Manage StudyOS</h2></div>
          <button className="manager-close" type="button" onClick={onClose}>×</button>
        </header>

        {error && <div className="error-banner"><span>{error}</span></div>}
        {notice && <div className="setup-message">{notice}</div>}

        <div className="manager-layout">
          <aside className="manager-list">
            <button className="manager-add" type="button" onClick={() => {
              setNewCourse(true); setSelectedId(null); setName(""); setExamDate(""); setTargetGrade(""); setMaxGrade("30");
            }}>+ Add course</button>
            {courses.map((course) => {
              const status = setups[course.id];
              return (
                <button
                  key={course.id}
                  type="button"
                  className={selectedId === course.id ? "manager-course active" : "manager-course"}
                  onClick={() => { setNewCourse(false); setSelectedId(course.id); }}
                >
                  <strong>{course.name}</strong>
                  <small>{status?.ready_for_planning ? "Ready" : status?.analysis_stale ? "Analysis stale" : status?.next_step?.replaceAll("_", " ")}</small>
                </button>
              );
            })}
          </aside>

          <div className="manager-detail">
            {(newCourse || selected) && (
              <form className="manager-form" onSubmit={newCourse ? createCourse : saveCourse}>
                <div className="manager-section-head">
                  <div><span>{newCourse ? "New course" : "Course settings"}</span><strong>{newCourse ? "Add another course" : selected?.name}</strong></div>
                  {!newCourse && setup && <b className={setup.ready_for_planning ? "manager-ready" : "manager-stale"}>{setup.ready_for_planning ? "Ready" : "Needs attention"}</b>}
                </div>
                <label>Name<input required value={name} onChange={(e) => setName(e.target.value)} /></label>
                <div className="setup-row">
                  <label>Exam date<input type="date" value={examDate} onChange={(e) => setExamDate(e.target.value)} /></label>
                  <label>Target<input type="number" min="0" step="0.1" value={targetGrade} onChange={(e) => setTargetGrade(e.target.value)} /></label>
                  <label>Scale<input type="number" min="1" step="0.1" value={maxGrade} onChange={(e) => setMaxGrade(e.target.value)} /></label>
                </div>
                <button className="primary-button manager-save" disabled={busy}>{newCourse ? "Create course" : "Save changes"}</button>
              </form>
            )}

            {selected && !newCourse && (
              <>
                <section className="manager-section">
                  <div className="manager-section-head">
                    <div><span>Evidence</span><strong>Course materials</strong></div>
                    <small>{documents.length} file{documents.length === 1 ? "" : "s"}</small>
                  </div>
                  <label className="manager-upload">
                    <input type="file" multiple accept=".pdf,.docx,.pptx,.txt" onChange={(e) => setFiles(Array.from(e.target.files ?? []))} />
                    <span>{files.length ? `${files.length} selected` : "Choose files"}</span>
                  </label>
                  {files.length > 0 && <button className="primary-button" type="button" disabled={busy} onClick={upload}>Upload & process</button>}
                  <div className="manager-documents">
                    {documents.map((document) => (
                      <div key={document.id}>
                        <span><strong>{document.original_filename}</strong><small>{document.status} · {(document.size_bytes / 1024).toFixed(0)} KB</small></span>
                        <button type="button" disabled={busy} onClick={() => removeDocument(document.id)}>Remove</button>
                      </div>
                    ))}
                    {!documents.length && <p className="muted">No source material yet.</p>}
                  </div>
                </section>

                <section className="manager-section">
                  <div className="manager-section-head">
                    <div><span>Intelligence</span><strong>Analysis state</strong></div>
                    <small>{setup?.processed_document_count ?? 0} processed</small>
                  </div>
                  <p className="manager-note">
                    {setup?.analysis_stale
                      ? "Your material set changed after the last analysis. Rebuild intelligence before regenerating plans."
                      : setup?.course_analyzed
                        ? "Topic intelligence matches the current processed source set."
                        : "Analyze the processed materials to make this course plannable."}
                  </p>
                  <button className="ghost-button" type="button" disabled={busy || !setup?.processed_document_count} onClick={analyze}>
                    {setup?.course_analyzed ? "Re-run analysis" : "Analyze course"}
                  </button>
                </section>

                <section className="manager-section manager-danger-section">
                  <div className="manager-section-head">
                    <div><span>Danger zone</span><strong>Delete this course</strong></div>
                  </div>
                  <p className="manager-note">
                    This permanently removes the course, uploaded source records, mastery evidence,
                    study history, forecasts, and course-specific schedules.
                  </p>
                  <label className="manager-delete-confirm">
                    Type <strong>{selected.name}</strong> to confirm
                    <input
                      value={deleteConfirmation}
                      onChange={(event) => setDeleteConfirmation(event.target.value)}
                    />
                  </label>
                  <button
                    className="danger-button"
                    type="button"
                    disabled={busy || deleteConfirmation !== selected.name}
                    onClick={removeCourse}
                  >
                    Delete course permanently
                  </button>
                </section>
              </>
            )}
          </div>
        </div>

        <footer className="manager-planbar">
          <div>
            <span>Semester queue</span>
            <strong>{readyCourses.length} ready / {courses.length} courses</strong>
          </div>
          <label>Hours<input type="number" min="0.5" max="336" step="0.5" value={planHours} onChange={(e) => setPlanHours(e.target.value)} /></label>
          <button className="primary-button" type="button" disabled={busy || !readyCourses.length} onClick={rebuildPlan}>Regenerate plan</button>
        </footer>
      </section>
    </div>
  );
}
