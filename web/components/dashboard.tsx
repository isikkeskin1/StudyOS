"use client";

import { useCallback, useEffect, useMemo, useState } from "react";

import { AccountSettings } from "@/components/account-settings";
import { AdminCatalog } from "@/components/admin-catalog";
import { CourseManager } from "@/components/course-manager";
import { BrandMark, UiIcon, type IconName } from "@/components/ui-icon";
import { FocusTimer } from "@/components/focus-timer";
import { GlobalSearch } from "@/components/global-search";

import type {
  AnalyticsCourse,
  AnalyticsDashboard,
  FocusAction,
  FocusSession,
  SemesterDashboard,
} from "@/lib/types";

const WINDOWS = [7, 30, 90] as const;
type WindowDays = (typeof WINDOWS)[number];

async function requestJson<T>(url: string, init?: RequestInit): Promise<T> {
  const response = await fetch(url, {
    ...init,
    headers: { "Content-Type": "application/json" },
    cache: "no-store",
  });

  if (!response.ok) {
    let detail = `${response.status} ${response.statusText}`;
    try {
      const body = (await response.json()) as { detail?: string };
      if (body.detail) detail = body.detail;
    } catch {
      // Keep the HTTP fallback when the response is not JSON.
    }
    throw new Error(detail);
  }

  return (await response.json()) as T;
}

function formatMinutes(minutes: number) {
  if (minutes < 60) return `${minutes}m`;
  const hours = Math.floor(minutes / 60);
  const remainder = minutes % 60;
  return remainder ? `${hours}h ${remainder}m` : `${hours}h`;
}

function formatPercent(value: number | null, digits = 0) {
  if (value === null) return "—";
  return `${(value * 100).toFixed(digits)}%`;
}

function statusLabel(status: AnalyticsCourse["target_status"]) {
  switch (status) {
    case "at_target":
      return "At target";
    case "below_target":
      return "Below target";
    case "unmeasured":
      return "Needs evidence";
    default:
      return "No target";
  }
}

function activityLabel(value: string) {
  return new Date(`${value}T00:00:00`).toLocaleDateString(undefined, {
    month: "short",
    day: "numeric",
  });
}

export function Dashboard({
  userEmail,
  isAdmin,
  onSignOut,
  onAccountDeleted,
}: {
  userEmail: string | null;
  isAdmin: boolean;
  onSignOut: () => void;
  onAccountDeleted: () => void;
}) {
  const [activeSection, setActiveSection] = useState("overview");
  const [days, setDays] = useState<WindowDays>(30);
  const [courseId, setCourseId] = useState("all");
  const [timezone] = useState(() => {
    if (typeof Intl === "undefined") return "Europe/Rome";
    return Intl.DateTimeFormat().resolvedOptions().timeZone || "Europe/Rome";
  });
  const [analytics, setAnalytics] = useState<AnalyticsDashboard | null>(null);
  const [semester, setSemester] = useState<SemesterDashboard | null>(null);
  const [activeFocus, setActiveFocus] = useState<FocusSession | null>(null);
  const [loading, setLoading] = useState(true);
  const [actionBusy, setActionBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [managerOpen, setManagerOpen] = useState(false);
  const [adminOpen, setAdminOpen] = useState(false);
  const [accountOpen, setAccountOpen] = useState(false);

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const params = new URLSearchParams({ days: String(days), timezone });
      if (courseId !== "all") params.set("course_id", courseId);

      const [analyticsData, semesterData] = await Promise.all([
        requestJson<AnalyticsDashboard>(`/api/v1/analytics?${params.toString()}`),
        requestJson<SemesterDashboard>("/api/v1/semester/dashboard"),
      ]);

      setAnalytics(analyticsData);
      setSemester(semesterData);

      if (semesterData.selected_queue_id) {
        const sessions = await requestJson<FocusSession[]>(
          `/api/v1/semester-queues/${semesterData.selected_queue_id}/focus-sessions`,
        );
        setActiveFocus(sessions.find((session) => session.status === "active") ?? null);
      } else {
        setActiveFocus(null);
      }
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "Unable to load StudyOS data.");
    } finally {
      setLoading(false);
    }
  }, [courseId, days, timezone]);

  useEffect(() => {
    void load();
  }, [load]);

  useEffect(() => {
    const updateSection = () => {
      const sections = ["overview", "activity", "courses", "risks"];
      const current = sections.filter((id) => {
        const element = document.getElementById(id);
        return element && element.getBoundingClientRect().top <= window.innerHeight * 0.4;
      }).at(-1);
      setActiveSection(current ?? "overview");
    };
    window.addEventListener("scroll", updateSection, { passive: true });
    updateSection();
    return () => window.removeEventListener("scroll", updateSection);
  }, [analytics]);

  const selectedQueue = useMemo(() => {
    if (!semester?.selected_queue_id) return null;
    return semester.queues.find((queue) => queue.queue_id === semester.selected_queue_id) ?? null;
  }, [semester]);

  const riskRows = useMemo(() => {
    if (!analytics) return [];
    return analytics.courses
      .flatMap((course) =>
        course.highest_risk_topics.slice(0, 2).map((topic) => ({
          ...topic,
          courseName: course.course_name,
        })),
      )
      .sort((a, b) => b.mistake_burden - a.mistake_burden)
      .slice(0, 6);
  }, [analytics]);

  const maxFocus = useMemo(() => {
    if (!analytics?.activity.length) return 1;
    return Math.max(1, ...analytics.activity.map((day) => day.focus_minutes));
  }, [analytics]);

  const focusAction = async (kind: "start" | "complete" | "skip") => {
    if (!semester?.selected_queue_id) return;
    const queueId = semester.selected_queue_id;
    let url = `/api/v1/semester-queues/${queueId}/focus-sessions`;
    let body: Record<string, string> = {};

    if (kind === "start") {
      if (!semester.next_action) return;
      body = { expected_block_id: semester.next_action.id };
    } else {
      if (!activeFocus) return;
      url += `/${activeFocus.id}/${kind}`;
    }

    setActionBusy(true);
    setError(null);
    try {
      const result = await requestJson<FocusAction>(url, {
        method: "POST",
        body: JSON.stringify(body),
      });
      setActiveFocus(result.session.status === "active" ? result.session : null);
      await load();
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "Focus action failed.");
    } finally {
      setActionBusy(false);
    }
  };

  const refreshQueue = async () => {
    if (!semester?.selected_queue_id) return;
    setActionBusy(true);
    setError(null);
    try {
      await requestJson(`/api/v1/semester-queues/${semester.selected_queue_id}/refresh`, {
        method: "POST",
        body: JSON.stringify({}),
      });
      await load();
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "Queue refresh failed.");
    } finally {
      setActionBusy(false);
    }
  };

  return (
    <div className="app-shell">
      <a className="skip-link" href="#main-content">Skip to content</a>
      <aside className="sidebar">
        <a className="brand" href="#overview" aria-label="StudyOS home">
          <BrandMark />
          <span><strong>StudyOS<span className="brand-period">.</span></strong><small>Your study workspace</small></span>
        </a>
        <div className="sidebar-search"><GlobalSearch /></div>
        <p className="nav-label">Workspace</p>
        <nav className="side-nav" aria-label="Dashboard sections">
          {([["overview", "Overview"], ["activity", "Activity"], ["courses", "Courses"], ["risks", "Needs attention"]] as const).map(([id, label]) => (
            <a key={id} className={activeSection === id ? "active" : ""} aria-current={activeSection === id ? "location" : undefined} href={`#${id}`} onClick={() => setActiveSection(id)}>
              <UiIcon name={id as IconName} /><span className="nav-text">{label}</span>
              {id === "courses" && semester && <small className="nav-count">{semester.course_count}</small>}
            </a>
          ))}
        </nav>
        <div className="sidebar-tools">
          <p className="nav-label">Tools</p>
          <button onClick={() => setManagerOpen(true)}><UiIcon name="plus" />Manage courses</button>
          {isAdmin && <button onClick={() => setAdminOpen(true)}><UiIcon name="shield" />Admin catalog</button>}
          <button onClick={() => setAccountOpen(true)}><UiIcon name="settings" />Account</button>
          <button onClick={onSignOut}><UiIcon name="logout" />Sign out</button>
        </div>
        <div className="sidebar-note"><UiIcon name="layers" /><strong>A little progress, every day.</strong><span>Your next session is a good place to start.</span></div>
        <div className="sidebar-foot account-foot">
          <span className="account-avatar">{(userEmail?.[0] ?? "S").toUpperCase()}</span>
          <div><strong>{userEmail ?? "Signed in"}</strong><small><span className="status-dot" />Private workspace</small></div>
        </div>
      </aside>

      <main className="main-content" id="main-content" tabIndex={-1}>
        <div className="dashboard-context"><span>Workspace <span>/</span> Overview</span><span className="context-status"><span className="status-dot" />{loading ? "Syncing your workspace" : error ? "Sync interrupted" : "Up to date"}</span></div>
        <section className="topbar" id="overview">
          <div>
            <p className="eyebrow">Your semester, in focus</p>
            <h1>Let’s make progress.</h1>
            <p className="muted">Pick up where you left off. Make your next session count.</p>
          </div>
          <div className="topbar-actions">
            <select aria-label="Filter analytics by course" value={courseId} onChange={(event) => setCourseId(event.target.value)}>
              <option value="all">All courses</option>
              {semester?.courses.map((course) => <option key={course.course_id} value={course.course_id}>{course.course_name}</option>)}
            </select>
            <button className="ghost-button icon-button" aria-label="Refresh dashboard" title="Refresh dashboard" onClick={() => void load()} disabled={loading}><UiIcon name="refresh" className={loading ? "is-spinning" : ""} /></button>
          </div>
        </section>

        {error && (
          <div className="error-banner" role="alert">
            <span>{error}</span>
            <button onClick={() => void load()}>Retry</button>
          </div>
        )}

        {!analytics || !semester ? (
          <div className="loading-grid" aria-label="Loading dashboard">
            {Array.from({ length: 8 }).map((_, index) => <div className="skeleton" key={index} />)}
          </div>
        ) : (
          <>
            <section className="metric-grid" aria-label="Key metrics">
              <article className="metric-card metric-primary">
                <p><UiIcon name="clock" />Focused study</p>
                <strong>{formatMinutes(analytics.summary.focus_minutes)}</strong>
                <span>{formatPercent(analytics.summary.focus_completion_rate)} completion rate</span>
              </article>
              <article className="metric-card">
                <p><UiIcon name="check" />Answer quality</p>
                <strong>{formatPercent(analytics.summary.average_answer_score)}</strong>
                <span>{analytics.summary.answer_count} graded answers</span>
              </article>
              <article className="metric-card">
                <p><UiIcon name="layers" />Due reviews</p>
                <strong>{semester.due_review_count}</strong>
                <span>{semester.upcoming_exam_count} upcoming exams</span>
              </article>
              <article className="metric-card">
                <p><UiIcon name="target" />Below target</p>
                <strong>{analytics.summary.below_target_count}</strong>
                <span>{analytics.summary.at_target_count} courses at target</span>
              </article>
            </section>

            <section className="hero-grid">
              <article className="panel next-action-panel">
                <div className="focus-content">
                <div className="panel-head">
                  <div>
                    <p className="eyebrow">Up next · Focus session</p>
                    <h2>{semester.next_action?.topic_name ?? "Your next step starts here"}</h2>
                  </div>
                  {semester.next_action && (
                    <span className={`pill ${semester.next_action.status}`}>
                      {semester.next_action.status.replace("_", " ")}
                    </span>
                  )}
                </div>

                {semester.next_action ? (
                  <>
                    <p className="next-course">{semester.next_action.course_name}</p>
                    <div className="action-stats">
                      <div><span>Block</span><strong>{semester.next_action.planned_minutes} min</strong></div>
                      <div><span>Expected gain</span><strong>+{semester.next_action.expected_mark_gain.toFixed(2)}</strong></div>
                      <div><span>Session type</span><strong>Deep focus</strong></div>
                    </div>
                    {activeFocus ? (
                      <div className="focus-running">
                        <div>
                          <span className="live-dot" /> Focus active until {new Date(activeFocus.target_end_at).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" })}
                        </div>
                        <div className="button-row">
                          <button className="primary-button" disabled={actionBusy} onClick={() => void focusAction("complete")}>Complete</button>
                          <button className="danger-button" disabled={actionBusy} onClick={() => void focusAction("skip")}>Skip</button>
                        </div>
                      </div>
                    ) : (
                      <button className="primary-button full" disabled={actionBusy || selectedQueue?.needs_refresh} onClick={() => void focusAction("start")}>
                        <UiIcon name="play" />{selectedQueue?.needs_refresh ? "Refresh queue first" : actionBusy ? "Starting…" : "Start focus block"}<UiIcon name="arrow" />
                      </button>
                    )}
                  </>
                ) : (
                  <div className="empty-state">
                    <strong>{selectedQueue?.needs_refresh ? "Queue needs a refresh" : "Ready when you are"}</strong>
                    <span>{selectedQueue?.needs_refresh ? selectedQueue.refresh_reasons.join(" · ") : "Add your course materials and build a study plan to find the best place to start."}</span>
                    {!selectedQueue && <button className="primary-button" onClick={() => setManagerOpen(true)}><UiIcon name="plus" />Build your study plan</button>}
                    {selectedQueue?.needs_refresh && (
                      <button className="primary-button" disabled={actionBusy} onClick={() => void refreshQueue()}>Refresh queue</button>
                    )}
                  </div>
                )}
                </div>
                {(semester.next_action || activeFocus) && <FocusTimer session={activeFocus} minutes={activeFocus?.planned_minutes ?? semester.next_action?.planned_minutes ?? 0} />}
              </article>

              <article className="panel queue-panel">
                <div className="panel-head compact">
                  <div>
                    <p className="eyebrow">Study plan</p>
                    <h2>{selectedQueue ? "Your session budget" : "Room to get started"}</h2>
                  </div>
                  <span className={`health-dot ${selectedQueue?.needs_refresh ? "warn" : "good"}`} />
                </div>
                {selectedQueue ? (
                  <>
                    <div className="queue-stat"><span>Completed</span><strong>{formatMinutes(selectedQueue.completed_study_minutes)}</strong></div>
                    <div className="queue-stat"><span>Remaining budget</span><strong>{formatMinutes(selectedQueue.remaining_available_minutes)}</strong></div>
                    <div className="queue-stat"><span>Planned work</span><strong>{formatMinutes(selectedQueue.planned_minutes)}</strong></div>
                    <div className="queue-progress">
                      <span style={{ width: `${Math.min(100, (selectedQueue.completed_study_minutes / Math.max(1, selectedQueue.completed_study_minutes + selectedQueue.planned_minutes)) * 100)}%` }} />
                    </div>
                    <p className="queue-caption">{selectedQueue.needs_refresh ? `Refresh required: ${selectedQueue.refresh_reasons.join(", ")}` : "Your plan is up to date."}</p>
                  </>
                ) : (
                  <p className="muted">Your planned sessions and completed study time will appear here.</p>
                )}
              </article>
            </section>

            <section className="panel activity-panel" id="activity">
              <div className="panel-head">
                <div>
                  <p className="eyebrow">Your consistency</p>
                  <h2>Focused study activity</h2>
                </div>
                <div className="window-toggle" aria-label="Analytics window">
                  {WINDOWS.map((windowDays) => (
                    <button key={windowDays} aria-pressed={days === windowDays} className={days === windowDays ? "active" : ""} onClick={() => setDays(windowDays)}>
                      {windowDays}D
                    </button>
                  ))}
                </div>
              </div>
              <div className="chart-scroll">
                <div className="activity-chart" style={{ minWidth: `${Math.max(620, analytics.activity.length * 34)}px` }}>
                  {analytics.activity.map((day, index) => {
                    const height = Math.max(4, (day.focus_minutes / maxFocus) * 100);
                    const answers = day.diagnostic_responses + day.practice_attempts;
                    return (
                      <div className="bar-column" key={day.date} title={`${activityLabel(day.date)} — ${day.focus_minutes} focus min, ${answers} answers`}>
                        <div className="bar-track"><span style={{ height: `${day.focus_minutes === 0 ? 0 : height}%`, animationDelay: `${Math.min(index, 20) * 18}ms` }} /></div>
                        <small>{activityLabel(day.date)}</small>
                      </div>
                    );
                  })}
                </div>
              </div>
              <div className="chart-legend">
                <span><i className="legend-focus" /> Focus minutes</span>
                <span>{analytics.summary.mastery_updates} mastery updates</span>
                <span>{analytics.summary.forecast_snapshots} forecasts</span>
                <span>Timezone: {analytics.timezone}</span>
              </div>
            </section>

            <section className="section-head" id="courses">
              <div>
                <p className="eyebrow">Readiness</p>
                <h2>Your courses</h2>
              </div>
              <span>{analytics.courses.length} shown</span>
            </section>

            <section className="course-grid">
              {analytics.courses.length === 0 && <div className="panel course-empty"><UiIcon name="courses" /><h3>{courseId === "all" ? "A home for every course" : "No course data in this view"}</h3><p className="muted">{courseId === "all" ? "Add your first course to keep your materials, practice, and progress together." : "Choose all courses or refresh to try again."}</p><button className="primary-button" onClick={() => courseId === "all" ? setManagerOpen(true) : setCourseId("all")}>{courseId === "all" ? "Add a course" : "Show all courses"}<UiIcon name="arrow" /></button></div>}
              {analytics.courses.map((course, index) => {
                const readiness = Math.max(0, Math.min(1, course.normalized_current_grade ?? 0));
                const target = Math.max(0, Math.min(1, course.normalized_target_grade ?? 0));
                return (
                  <article className="course-card" key={course.course_id} style={{ animationDelay: `${Math.min(index, 6) * 55}ms` }}>
                    <div className="course-top">
                      <span className={`course-symbol course-color-${index % 4}`}><UiIcon name="courses" /></span>
                      <div>
                        <span className={`confidence ${course.confidence}`}>{course.confidence}</span>
                        <h3>{course.course_name}</h3>
                      </div>
                      <span className={`target-status ${course.target_status}`}>{statusLabel(course.target_status)}</span>
                    </div>
                    <div className="grade-row">
                      <div>
                        <span>Estimated grade</span>
                        <strong>{course.current_estimated_grade === null ? "—" : `${course.current_estimated_grade.toFixed(1)} / ${course.max_grade}`}</strong>
                      </div>
                      <div>
                        <span>Target</span>
                        <strong>{course.target_grade === null ? "—" : `${course.target_grade.toFixed(1)} / ${course.max_grade}`}</strong>
                      </div>
                    </div>
                    <div className="readiness-track" aria-label={`${course.course_name} normalized grade progress`}>
                      {course.target_grade !== null && <span className="target-marker" style={{ left: `${target * 100}%` }} />}
                      <span className="readiness-fill" style={{ width: `${readiness * 100}%` }} />
                    </div>
                    <div className="course-stats">
                      <div><span>Mastery</span><strong>{formatPercent(course.current_mean_mastery)}</strong></div>
                      <div><span>Answers</span><strong>{formatPercent(course.average_answer_score)}</strong></div>
                      <div><span>Focus</span><strong>{formatMinutes(course.focus_minutes)}</strong></div>
                    </div>
                    <div className="course-foot">
                      <span>{course.measured_topic_count}/{course.topic_count} topics measured</span>
                      <a className="course-open" href={`/courses/${course.course_id}`}>Open workspace <UiIcon name="arrow" /></a>
                    </div>
                  </article>
                );
              })}
            </section>

            <section className="risk-grid" id="risks">
              <article className="panel">
                <div className="panel-head">
                  <div>
                    <p className="eyebrow">Worth another look</p>
                    <h2>Needs attention</h2>
                  </div>
                </div>
                {riskRows.length ? (
                  <div className="risk-list">
                    {riskRows.map((risk) => (
                      <div className="risk-row" key={`${risk.courseName}-${risk.topic_id}`}>
                        <div>
                          <strong>{risk.topic_name}</strong>
                          <span>{risk.courseName} · {risk.dominant_categories.join(" · ") || "uncategorized"}</span>
                        </div>
                        <div className="risk-meter"><span style={{ width: `${risk.mistake_burden * 100}%` }} /></div>
                        <b>{formatPercent(risk.mistake_burden)}</b>
                      </div>
                    ))}
                  </div>
                ) : (
                  <p className="muted">No classified mistake hotspots yet.</p>
                )}
              </article>

              <article className="panel evidence-panel">
                <div className="panel-head">
                  <div>
                    <p className="eyebrow">Recent progress</p>
                    <h2>What changed</h2>
                  </div>
                </div>
                <div className="evidence-list">
                  <div><span>Mastery updates</span><strong>{analytics.summary.mastery_updates}</strong></div>
                  <div><span>Forecast snapshots</span><strong>{analytics.summary.forecast_snapshots}</strong></div>
                  <div><span>Completed focus</span><strong>{analytics.summary.focus_sessions_completed}</strong></div>
                  <div><span>Skipped focus</span><strong>{analytics.summary.focus_sessions_skipped}</strong></div>
                </div>
                <p className="fine-print">Analytics are read-only projections from StudyOS evidence. Estimated grades and target probabilities are planning signals, not guaranteed outcomes.</p>
              </article>
            </section>
          </>
        )}
      </main>
      <AdminCatalog
        open={adminOpen}
        onClose={() => setAdminOpen(false)}
        onChanged={() => void load()}
      />
      <CourseManager
        open={managerOpen}
        onClose={() => setManagerOpen(false)}
        onChanged={() => void load()}
      />
      <AccountSettings
        open={accountOpen}
        email={userEmail}
        onClose={() => setAccountOpen(false)}
        onDeleted={onAccountDeleted}
      />
    </div>
  );
}
