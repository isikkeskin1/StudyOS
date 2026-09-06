"use client";

import { FormEvent, useEffect, useMemo, useState } from "react";

type CatalogCourse = {
  id: string;
  source_course_id: string;
  institution_name: string;
  institution_code: string | null;
  course_code: string | null;
  academic_year: string | null;
  language: string | null;
  description: string | null;
  published: boolean;
  created_at: string;
  updated_at: string;
  name: string;
  document_count: number;
};

type CatalogSource = {
  id: string;
  catalog_course_id: string;
  url: string;
  discovered_from_url: string | null;
  title: string | null;
  source_kind: string;
  content_type: string | null;
  extension: string | null;
  status: string;
  depth: number;
  sha256: string | null;
  imported_document_id: string | null;
  discovery_note: string | null;
  created_at: string;
  updated_at: string;
};

async function api<T>(url: string, init?: RequestInit): Promise<T> {
  const response = await fetch(url, { ...init, cache: "no-store" });
  if (!response.ok) {
    let detail = `${response.status} ${response.statusText}`;
    try {
      const body = (await response.json()) as { detail?: string };
      if (body.detail) detail = body.detail;
    } catch {
      // Preserve the HTTP fallback if the response is not JSON.
    }
    throw new Error(detail);
  }
  if (response.status === 204) return undefined as T;
  return (await response.json()) as T;
}

function sourceLabel(kind: string) {
  return kind.replaceAll("_", " ");
}

export function AdminCatalog({
  open,
  onClose,
  onChanged,
}: {
  open: boolean;
  onClose: () => void;
  onChanged: () => void;
}) {
  const [courses, setCourses] = useState<CatalogCourse[]>([]);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [sources, setSources] = useState<CatalogSource[]>([]);
  const [institutionName, setInstitutionName] = useState("Politecnico di Torino");
  const [institutionCode, setInstitutionCode] = useState("POLITO");
  const [courseName, setCourseName] = useState("");
  const [courseCode, setCourseCode] = useState("");
  const [academicYear, setAcademicYear] = useState("");
  const [language, setLanguage] = useState("English");
  const [description, setDescription] = useState("");
  const [seedUrls, setSeedUrls] = useState("");
  const [maxDepth, setMaxDepth] = useState("2");
  const [maxSources, setMaxSources] = useState("80");
  const [creating, setCreating] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);

  const selected = useMemo(
    () => courses.find((course) => course.id === selectedId) ?? null,
    [courses, selectedId],
  );

  const counts = useMemo(() => {
    const result: Record<string, number> = {};
    for (const source of sources) {
      result[source.status] = (result[source.status] ?? 0) + 1;
    }
    return result;
  }, [sources]);

  const loadCourses = async (preferredId?: string | null) => {
    const list = await api<CatalogCourse[]>("/api/v1/admin/catalog/courses");
    setCourses(list);
    const nextId = preferredId ?? selectedId ?? list[0]?.id ?? null;
    setSelectedId(nextId);
    if (nextId) {
      setSources(
        await api<CatalogSource[]>(
          `/api/v1/admin/catalog/courses/${nextId}/sources`,
        ),
      );
    } else {
      setSources([]);
    }
  };

  const loadSources = async (catalogId = selectedId) => {
    if (!catalogId) {
      setSources([]);
      return;
    }
    setSources(
      await api<CatalogSource[]>(
        `/api/v1/admin/catalog/courses/${catalogId}/sources`,
      ),
    );
  };

  useEffect(() => {
    if (!open) return;
    setError(null);
    setNotice(null);
    void loadCourses();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [open]);

  useEffect(() => {
    if (!open || !selectedId) return;
    void loadSources(selectedId);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [selectedId, open]);

  if (!open) return null;

  const run = async (work: () => Promise<void>) => {
    setBusy(true);
    setError(null);
    setNotice(null);
    try {
      await work();
      onChanged();
    } catch (caught) {
      setError(
        caught instanceof Error ? caught.message : "Admin catalog operation failed.",
      );
    } finally {
      setBusy(false);
    }
  };

  const createCourse = (event: FormEvent) => {
    event.preventDefault();
    void run(async () => {
      const created = await api<CatalogCourse>("/api/v1/admin/catalog/courses", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          name: courseName.trim(),
          institution_name: institutionName.trim(),
          institution_code: institutionCode.trim() || null,
          course_code: courseCode.trim() || null,
          academic_year: academicYear.trim() || null,
          language: language.trim() || null,
          description: description.trim() || null,
          max_grade: 30,
        }),
      });
      setCreating(false);
      setCourseName("");
      setCourseCode("");
      setDescription("");
      await loadCourses(created.id);
      setNotice("Institutional master course created.");
    });
  };

  const discover = () => {
    if (!selected) return;
    const seeds = seedUrls
      .split(/\r?\n/)
      .map((value) => value.trim())
      .filter(Boolean);
    if (!seeds.length) {
      setError("Add at least one public institution seed URL.");
      return;
    }
    void run(async () => {
      const discovered = await api<CatalogSource[]>(
        `/api/v1/admin/catalog/courses/${selected.id}/discover`,
        {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            seed_urls: seeds,
            max_depth: Number(maxDepth),
            max_sources: Number(maxSources),
          }),
        },
      );
      await loadSources(selected.id);
      setNotice(
        `Discovery finished with ${discovered.length} new source candidates.`,
      );
    });
  };

  const setSourceStatus = (source: CatalogSource, status: string) => {
    if (!selected) return;
    void run(async () => {
      await api(
        `/api/v1/admin/catalog/courses/${selected.id}/sources/${source.id}`,
        {
          method: "PATCH",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ status }),
        },
      );
      await loadSources(selected.id);
      setNotice(`Source marked ${status}.`);
    });
  };

  const importApproved = () => {
    if (!selected) return;
    void run(async () => {
      const documents = await api<Array<{ id: string }>>(
        `/api/v1/admin/catalog/courses/${selected.id}/import-approved`,
        { method: "POST" },
      );
      await Promise.all([loadSources(selected.id), loadCourses(selected.id)]);
      setNotice(
        `${documents.length} source${documents.length === 1 ? "" : "s"} imported and analyzed.`,
      );
    });
  };

  const togglePublish = () => {
    if (!selected) return;
    void run(async () => {
      const action = selected.published ? "unpublish" : "publish";
      await api(
        `/api/v1/admin/catalog/courses/${selected.id}/${action}`,
        { method: "POST" },
      );
      await loadCourses(selected.id);
      setNotice(selected.published ? "Course unpublished." : "Course published.");
    });
  };

  return (
    <div
      className="manager-backdrop"
      role="presentation"
      onMouseDown={(event) => {
        if (event.target === event.currentTarget) onClose();
      }}
    >
      <section
        className="manager-panel admin-catalog-panel"
        role="dialog"
        aria-modal="true"
        aria-label="Admin course catalog"
      >
        <header className="manager-header">
          <div>
            <p className="eyebrow">Institution intelligence</p>
            <h2>Admin course catalog</h2>
          </div>
          <button className="manager-close" type="button" onClick={onClose}>
            ×
          </button>
        </header>

        {error && <div className="error-banner"><span>{error}</span></div>}
        {notice && <div className="setup-message">{notice}</div>}

        <div className="manager-layout admin-catalog-layout">
          <aside className="manager-list">
            <button
              className="manager-add"
              type="button"
              onClick={() => setCreating(true)}
            >
              + New institutional course
            </button>
            {courses.map((course) => (
              <button
                key={course.id}
                type="button"
                className={
                  selectedId === course.id
                    ? "manager-course active"
                    : "manager-course"
                }
                onClick={() => {
                  setCreating(false);
                  setSelectedId(course.id);
                }}
              >
                <strong>{course.name}</strong>
                <small>
                  {course.institution_code ?? course.institution_name}
                  {course.course_code ? ` · ${course.course_code}` : ""}
                </small>
                <small>{course.published ? "Published" : "Draft"}</small>
              </button>
            ))}
          </aside>

          <div className="manager-detail admin-catalog-detail">
            {creating && (
              <form className="manager-form" onSubmit={createCourse}>
                <div className="manager-section-head">
                  <div>
                    <span>Master course</span>
                    <strong>Create institutional catalog entry</strong>
                  </div>
                </div>
                <label>
                  Institution
                  <input
                    required
                    value={institutionName}
                    onChange={(event) => setInstitutionName(event.target.value)}
                  />
                </label>
                <div className="setup-row">
                  <label>
                    Institution code
                    <input
                      value={institutionCode}
                      onChange={(event) => setInstitutionCode(event.target.value)}
                    />
                  </label>
                  <label>
                    Course code
                    <input
                      value={courseCode}
                      onChange={(event) => setCourseCode(event.target.value)}
                    />
                  </label>
                </div>
                <label>
                  Course name
                  <input
                    required
                    value={courseName}
                    onChange={(event) => setCourseName(event.target.value)}
                    placeholder="Physics I"
                  />
                </label>
                <div className="setup-row">
                  <label>
                    Academic year
                    <input
                      value={academicYear}
                      onChange={(event) => setAcademicYear(event.target.value)}
                      placeholder="2026/27"
                    />
                  </label>
                  <label>
                    Language
                    <input
                      value={language}
                      onChange={(event) => setLanguage(event.target.value)}
                    />
                  </label>
                </div>
                <label>
                  Description
                  <textarea
                    value={description}
                    onChange={(event) => setDescription(event.target.value)}
                    rows={4}
                  />
                </label>
                <button className="primary-button" disabled={busy}>
                  Create master course
                </button>
              </form>
            )}

            {!creating && selected && (
              <>
                <section className="manager-section">
                  <div className="manager-section-head">
                    <div>
                      <span>{selected.institution_name}</span>
                      <strong>{selected.name}</strong>
                    </div>
                    <b
                      className={
                        selected.published ? "manager-ready" : "manager-stale"
                      }
                    >
                      {selected.published ? "Published" : "Draft"}
                    </b>
                  </div>
                  <div className="admin-catalog-meta">
                    <span>{selected.course_code ?? "No course code"}</span>
                    <span>{selected.academic_year ?? "No academic year"}</span>
                    <span>{selected.document_count} imported documents</span>
                  </div>
                </section>

                <section className="manager-section">
                  <div className="manager-section-head">
                    <div>
                      <span>Discovery</span>
                      <strong>Crawl public institution sources</strong>
                    </div>
                  </div>
                  <p className="manager-note">
                    Add public course or teaching-portal URLs, one per line.
                    StudyOS only follows those seeded hosts and blocks private-network targets.
                  </p>
                  <label>
                    Seed URLs
                    <textarea
                      rows={5}
                      value={seedUrls}
                      onChange={(event) => setSeedUrls(event.target.value)}
                      placeholder={
                        "https://didattica.polito.it/...\nhttps://www.polito.it/..."
                      }
                    />
                  </label>
                  <div className="setup-row">
                    <label>
                      Crawl depth
                      <input
                        type="number"
                        min="0"
                        max="3"
                        value={maxDepth}
                        onChange={(event) => setMaxDepth(event.target.value)}
                      />
                    </label>
                    <label>
                      Max sources
                      <input
                        type="number"
                        min="1"
                        max="250"
                        value={maxSources}
                        onChange={(event) => setMaxSources(event.target.value)}
                      />
                    </label>
                  </div>
                  <button
                    className="primary-button"
                    type="button"
                    disabled={busy}
                    onClick={discover}
                  >
                    Discover sources
                  </button>
                </section>

                <section className="manager-section">
                  <div className="manager-section-head">
                    <div>
                      <span>Review queue</span>
                      <strong>Candidate sources</strong>
                    </div>
                    <small>
                      {counts.candidate ?? 0} candidate · {counts.approved ?? 0} approved ·{" "}
                      {counts.imported ?? 0} imported
                    </small>
                  </div>
                  <div className="admin-source-list">
                    {sources.map((source) => (
                      <article className="admin-source-card" key={source.id}>
                        <div className="admin-source-main">
                          <div>
                            <span className={`pill ${source.status}`}>
                              {source.status}
                            </span>
                            <span className="admin-source-kind">
                              {sourceLabel(source.source_kind)}
                            </span>
                          </div>
                          <strong>{source.title || source.url}</strong>
                          <a href={source.url} target="_blank" rel="noreferrer">
                            {source.url}
                          </a>
                          {source.discovery_note && (
                            <small>{source.discovery_note}</small>
                          )}
                        </div>
                        <div className="admin-source-actions">
                          {["candidate", "rejected"].includes(source.status) && (
                            <button
                              type="button"
                              disabled={busy}
                              onClick={() => setSourceStatus(source, "approved")}
                            >
                              Approve
                            </button>
                          )}
                          {["candidate", "approved"].includes(source.status) && (
                            <button
                              type="button"
                              disabled={busy}
                              onClick={() => setSourceStatus(source, "rejected")}
                            >
                              Reject
                            </button>
                          )}
                        </div>
                      </article>
                    ))}
                    {!sources.length && (
                      <p className="muted">
                        No sources yet. Start discovery from the official course pages.
                      </p>
                    )}
                  </div>
                  <div className="button-row">
                    <button
                      className="primary-button"
                      type="button"
                      disabled={busy || !(counts.approved ?? 0)}
                      onClick={importApproved}
                    >
                      Import approved
                    </button>
                    <button
                      className="ghost-button"
                      type="button"
                      disabled={busy}
                      onClick={() => void loadSources(selected.id)}
                    >
                      Refresh queue
                    </button>
                  </div>
                </section>

                <section className="manager-section">
                  <div className="manager-section-head">
                    <div>
                      <span>Distribution</span>
                      <strong>Publish to students</strong>
                    </div>
                  </div>
                  <p className="manager-note">
                    Publishing requires processed master-course documents and current course
                    intelligence. Students can then add the curated course to their own StudyOS.
                  </p>
                  <button
                    className={selected.published ? "danger-button" : "primary-button"}
                    type="button"
                    disabled={busy}
                    onClick={togglePublish}
                  >
                    {selected.published ? "Unpublish course" : "Publish course"}
                  </button>
                </section>
              </>
            )}

            {!creating && !selected && (
              <div className="empty-state">
                <strong>No institutional courses yet.</strong>
                <span>Create the first master course to begin source discovery.</span>
              </div>
            )}
          </div>
        </div>
      </section>
    </div>
  );
}
