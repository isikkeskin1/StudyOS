"use client";

import { useCallback, useEffect, useMemo, useState } from "react";

import { AccountSettings } from "@/components/account-settings";
import { AdminCatalog } from "@/components/admin-catalog";
import { CourseManager } from "@/components/course-manager";
import { FocusTimer } from "@/components/focus-timer";
import { GlobalSearch } from "@/components/global-search";
import { SpotifyDock } from "@/components/spotify-dock";
import { BrandMark, UiIcon, type IconName } from "@/components/ui-icon";

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
    headers: { "Content-Type": "application/json", ...(init?.headers ?? {}) },
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
      return "On target";
    case "below_target":
      return "Gap to close";
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

function dayHeading() {
  return new Intl.DateTimeFormat(undefined, {
    weekday: "long",
    month: "long",
    day: "numeric",
  }).format(new Date());
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
      const sections = ["overview", "courses", "activity", "risks"];
      const current = sections
        .filter((id) => {
          const element = document.getElementById(id);
          return element && element.getBoundingClientRect().top <= window.innerHeight * 0.42;
        })
        .at(-1);
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
      .slice(0, 5);
  }, [analytics]);

  const maxFocus = useMemo(() => {
    if (!analytics?.activity.length) return 1;
    return Math.max(1, ...analytics.activity.map((day) => day.focus_minutes));
  }, [analytics]);

  const nearestExam = useMemo(() => {
    if (!semester) return null;
    return semester.courses
      .filter((course) => course.days_until_exam !== null && course.days_until_exam >= 0)
      .sort((a, b) => (a.days_until_exam ?? 9999) - (b.days_until_exam ?? 9999))[0] ?? null;
  }, [semester]);

  const activity = useMemo(() => analytics?.activity.slice(-14) ?? [], [analytics]);

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
    <div className="app-shell study-cockpit">
      <a className="skip-link" href="#main-content">Skip to content</a>

      <aside className="sidebar cockpit-sidebar">
        <a className="brand" href="#overview" aria-label="StudyOS home">
          <BrandMark />
          <span><strong>StudyOS<span className="brand-period">.</span></strong><small>Your semester</small></span>
        </a>

        <div className="sidebar-search"><GlobalSearch /></div>

        <p className="nav-label">Workspace</p>
        <nav className="side-nav" aria-label="Dashboard sections">
          {([
            ["overview", "Today", "overview"],
            ["courses", "Courses", "courses"],
            ["activity", "Progress", "activity"],
            ["risks", "Review", "risks"],
          ] as const).map(([id, label, icon]) => (
            <a
              key={id}
              className={activeSection === id ? "active" : ""}
              aria-current={activeSection === id ? "location" : undefined}
              href={`#${id}`}
              onClick={() => setActiveSection(id)}
            >
              <UiIcon name={icon as IconName} />
              <span className="nav-text">{label}</span>
              {id === "courses" && semester && <small className="nav-count">{semester.course_count}</small>}
              {id === "risks" && semester && semester.due_review_count > 0 && <small className="nav-count attention">{semester.due_review_count}</small>}
            </a>
          ))}
        </nav>

        <div className="sidebar-tools">
          <p className="nav-label">Actions</p>
          <button onClick={() => setManagerOpen(true)}><UiIcon name="plus" />Add or manage courses</button>
          {isAdmin && <button onClick={() => setAdminOpen(true)}><UiIcon name="shield" />Master courses</button>}
          <button onClick={() => setAccountOpen(true)}><UiIcon name="settings" />Account & integrations</button>
        </div>

        <div className="sidebar-foot account-foot">
          <span className="account-avatar">{(userEmail?.[0] ?? "S").toUpperCase()}</span>
          <div><strong>{userEmail ?? "Signed in"}</strong><small><span className="status-dot" />Cloud synced</small></div>
          <button className="account-logout" onClick={onSignOut} aria-label="Sign out"><UiIcon name="logout" /></button>
        </div>
      </aside>

      <main className="main-content cockpit-main" id="main-content" tabIndex={-1}>
        <div className="cockpit-toolbar">
          <span>{loading ? "Syncing" : error ? "Sync interrupted" : "Synced"}<i className={error ? "sync-dot warn" : "sync-dot"} /></span>
          <div>
            <select aria-label="Filter dashboard by course" value={courseId} onChange={(event) => setCourseId(event.target.value)}>
              <option value="all">All courses</option>
              {semester?.courses.map((course) => <option key={course.course_id} value={course.course_id}>{course.course_name}</option>)}
            </select>
            <button className="ghost-button icon-button" aria-label="Refresh" onClick={() => void load()} disabled={loading}><UiIcon name="refresh" className={loading ? "is-spinning" : ""} /></button>
          </div>
        </div>

        {error && <div className="error-banner" role="alert"><span>{error}</span><button onClick={() => void load()}>Retry</button></div>}

        {!analytics || !semester ? (
          <div className="cockpit-loading"><div className="skeleton" /><div className="skeleton" /><div className="skeleton" /></div>
        ) : (
          <div className="cockpit-layout">
            <div className="cockpit-workspace">
              <section className="today-header" id="overview">
                <span className="today-date">{dayHeading()}</span>
                <h1>Today</h1>
                <div className="today-signals" aria-label="Today at a glance">
                  <span><strong>{formatMinutes(analytics.summary.focus_minutes)}</strong> focused · {days}d</span>
                  <span><strong>{semester.due_review_count}</strong> reviews due</span>
                  <span><strong>{formatPercent(analytics.summary.average_answer_score)}</strong> answer quality</span>
                  <span><strong>{analytics.summary.below_target_count}</strong> courses behind</span>
                </div>
              </section>

              <section className={`today-focus ${activeFocus ? "is-active" : ""}`}>
                <div className="today-focus-copy">
                  <div className="focus-kicker">
                    <span className={activeFocus ? "live-pulse" : "focus-index"}>{activeFocus ? "" : "01"}</span>
                    <span>{activeFocus ? "In session" : semester.next_action ? "Next session" : "Setup"}</span>
                  </div>

                  {semester.next_action ? (
                    <>
                      <span className="focus-course-name">{semester.next_action.course_name}</span>
                      <h2>{semester.next_action.topic_name}</h2>
                      <div className="focus-meta">
                        <span>{semester.next_action.planned_minutes} min</span>
                        <span>+{semester.next_action.expected_mark_gain.toFixed(2)} expected marks</span>
                        <span>{semester.next_action.status.replace("_", " ")}</span>
                      </div>

                      {activeFocus ? (
                        <div className="focus-actions">
                          <button className="primary-button" disabled={actionBusy} onClick={() => void focusAction("complete")}><UiIcon name="check" />Complete session</button>
                          <button className="quiet-action" disabled={actionBusy} onClick={() => void focusAction("skip")}>Skip</button>
                        </div>
                      ) : (
                        <button className="focus-launch" disabled={actionBusy || selectedQueue?.needs_refresh} onClick={() => void focusAction("start")}>
                          <span><UiIcon name="play" /></span>
                          <div><strong>{selectedQueue?.needs_refresh ? "Refresh plan first" : "Start session"}</strong><small>{semester.next_action.planned_minutes} minutes · distraction-free mode</small></div>
                          <UiIcon name="arrow" />
                        </button>
                      )}
                    </>
                  ) : (
                    <>
                      <span className="focus-course-name">{semester.course_count ? "Courses need planning" : "No courses yet"}</span>
                      <h2>{selectedQueue?.needs_refresh ? "Your study queue needs a refresh." : "Build the first real study block."}</h2>
                      <p className="focus-setup-copy">{selectedQueue?.needs_refresh ? selectedQueue.refresh_reasons.join(" · ") : "Add course evidence, set a target, and StudyOS will choose the highest-value next block."}</p>
                      {selectedQueue?.needs_refresh ? (
                        <button className="primary-button" disabled={actionBusy} onClick={() => void refreshQueue()}>Refresh plan</button>
                      ) : (
                        <button className="primary-button" onClick={() => setManagerOpen(true)}><UiIcon name="plus" />Set up courses</button>
                      )}
                    </>
                  )}
                </div>
                {(semester.next_action || activeFocus) && (
                  <div className="today-focus-timer"><FocusTimer session={activeFocus} minutes={activeFocus?.planned_minutes ?? semester.next_action?.planned_minutes ?? 0} /></div>
                )}
              </section>

              <section className="workspace-section course-momentum" id="courses">
                <div className="workspace-section-head">
                  <div><span className="section-number">02</span><div><h2>Courses</h2><p>Where you stand, and what needs work.</p></div></div>
                  <button className="text-action" onClick={() => setManagerOpen(true)}>Manage courses <UiIcon name="arrow" /></button>
                </div>

                <div className="course-ledger">
                  {analytics.courses.length === 0 ? (
                    <div className="ledger-empty"><strong>No course evidence yet.</strong><span>Add a course to start building an academic record.</span><button onClick={() => setManagerOpen(true)}>Add course</button></div>
                  ) : analytics.courses.map((course, index) => {
                    const readiness = Math.max(0, Math.min(1, course.normalized_current_grade ?? 0));
                    const target = Math.max(0, Math.min(1, course.normalized_target_grade ?? 0));
                    const semesterCourse = semester.courses.find((item) => item.course_id === course.course_id);
                    return (
                      <a className="ledger-row" href={`/courses/${course.course_id}`} key={course.course_id}>
                        <span className={`ledger-symbol course-color-${index % 4}`}>{course.course_name.split(/\s+/).map((part) => part[0]).join("").slice(0, 2).toUpperCase()}</span>
                        <div className="ledger-course">
                          <div><strong>{course.course_name}</strong><span>{course.measured_topic_count}/{course.topic_count} topics measured</span></div>
                          <div className="ledger-progress"><span style={{ width: `${readiness * 100}%` }} />{course.target_grade !== null && <i style={{ left: `${target * 100}%` }} />}</div>
                        </div>
                        <div className="ledger-grade"><span>Estimate</span><strong>{course.current_estimated_grade === null ? "—" : course.current_estimated_grade.toFixed(1)}{course.current_estimated_grade !== null && <small>/{course.max_grade}</small>}</strong></div>
                        <div className="ledger-grade"><span>Target</span><strong>{course.target_grade === null ? "—" : course.target_grade.toFixed(1)}{course.target_grade !== null && <small>/{course.max_grade}</small>}</strong></div>
                        <div className="ledger-evidence"><span>{formatPercent(course.current_mean_mastery)} mastery</span><span>{formatMinutes(course.focus_minutes)} focus</span></div>
                        <div className="ledger-deadline"><span>{semesterCourse?.days_until_exam === null || semesterCourse?.days_until_exam === undefined ? "No exam date" : semesterCourse.days_until_exam === 0 ? "Exam today" : `${semesterCourse.days_until_exam}d to exam`}</span><b className={`ledger-status ${course.target_status}`}>{statusLabel(course.target_status)}</b></div>
                        <UiIcon name="arrow" />
                      </a>
                    );
                  })}
                </div>
              </section>

              <section className="workspace-section progress-section" id="activity">
                <div className="workspace-section-head">
                  <div><span className="section-number">03</span><div><h2>Study rhythm</h2><p>Your actual study pattern over time.</p></div></div>
                  <div className="window-toggle" aria-label="Analytics window">
                    {WINDOWS.map((windowDays) => <button key={windowDays} aria-pressed={days === windowDays} className={days === windowDays ? "active" : ""} onClick={() => setDays(windowDays)}>{windowDays}D</button>)}
                  </div>
                </div>

                {analytics.summary.focus_minutes === 0 ? (
                  <div className="rhythm-empty"><span className="rhythm-line" /><div><strong>No focus history yet.</strong><span>Your completed sessions will build the timeline here.</span></div></div>
                ) : (
                  <div className="rhythm-chart">
                    {activity.map((day) => {
                      const height = Math.max(5, (day.focus_minutes / maxFocus) * 100);
                      return <div className="rhythm-day" key={day.date} title={`${activityLabel(day.date)} · ${day.focus_minutes} focused minutes`}><span><i style={{ height: `${day.focus_minutes ? height : 0}%` }} /></span><small>{activityLabel(day.date)}</small></div>;
                    })}
                  </div>
                )}
                <div className="rhythm-footer"><span>{analytics.summary.focus_sessions_completed} sessions completed</span><span>{analytics.summary.mastery_updates} mastery updates</span><span>{analytics.summary.forecast_snapshots} forecasts</span><span>{analytics.timezone}</span></div>
              </section>

              <section className="workspace-section review-section" id="risks">
                <div className="workspace-section-head">
                  <div><span className="section-number">04</span><div><h2>Review</h2><p>Mistakes and topics worth another pass.</p></div></div>
                  <span className="review-count">{riskRows.length} signals</span>
                </div>
                {riskRows.length ? (
                  <div className="review-ledger">
                    {riskRows.map((risk, index) => (
                      <div className="review-row" key={`${risk.courseName}-${risk.topic_id}`}>
                        <span>{String(index + 1).padStart(2, "0")}</span>
                        <div><strong>{risk.topic_name}</strong><small>{risk.courseName} · {risk.dominant_categories.join(" · ") || "uncategorized"}</small></div>
                        <div className="review-burden"><i style={{ width: `${Math.min(100, risk.mistake_burden * 100)}%` }} /></div>
                        <b>{formatPercent(risk.mistake_burden)}</b>
                      </div>
                    ))}
                  </div>
                ) : <div className="review-clear"><UiIcon name="check" /><div><strong>No mistake hotspots yet.</strong><span>As you practice, repeated errors will surface here automatically.</span></div></div>}
              </section>
            </div>

            <aside className="cockpit-rail" aria-label="Study context">
              <section className="rail-block rail-now">
                <span className="rail-label">Now</span>
                {activeFocus ? (
                  <><strong>{semester.next_action?.topic_name ?? "Focus session"}</strong><span>{semester.next_action?.course_name}</span><small>Active until {new Date(activeFocus.target_end_at).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" })}</small></>
                ) : semester.next_action ? (
                  <><strong>{semester.next_action.topic_name}</strong><span>{semester.next_action.course_name}</span><small>{semester.next_action.planned_minutes} min · +{semester.next_action.expected_mark_gain.toFixed(2)} marks</small></>
                ) : (
                  <><strong>No session queued</strong><span>Build or refresh your study plan.</span></>
                )}
              </section>

              <section className="rail-block rail-week">
                <span className="rail-label">Current window</span>
                <div><span>Focused</span><strong>{formatMinutes(analytics.summary.focus_minutes)}</strong></div>
                <div><span>Answer quality</span><strong>{formatPercent(analytics.summary.average_answer_score)}</strong></div>
                <div><span>Reviews due</span><strong>{semester.due_review_count}</strong></div>
                <div><span>At target</span><strong>{analytics.summary.at_target_count}/{analytics.summary.course_count}</strong></div>
              </section>

              <section className="rail-block rail-deadline">
                <span className="rail-label">Nearest exam</span>
                {nearestExam ? (
                  <><strong>{nearestExam.course_name}</strong><span>{nearestExam.days_until_exam === 0 ? "Today" : `${nearestExam.days_until_exam} days`}</span><small>{nearestExam.target_grade === null ? "No target set" : `Target ${nearestExam.target_grade}/${nearestExam.max_grade}`}</small></>
                ) : <><strong>No dated exams</strong><span>Add exam dates to make planning pressure-aware.</span></>}
              </section>

              <SpotifyDock />

              {selectedQueue && (
                <section className="rail-block rail-plan">
                  <span className="rail-label">Study plan</span>
                  <div className="rail-plan-progress"><span style={{ width: `${Math.min(100, (selectedQueue.completed_study_minutes / Math.max(1, selectedQueue.completed_study_minutes + selectedQueue.planned_minutes)) * 100)}%` }} /></div>
                  <div><span>Completed</span><strong>{formatMinutes(selectedQueue.completed_study_minutes)}</strong></div>
                  <div><span>Planned</span><strong>{formatMinutes(selectedQueue.planned_minutes)}</strong></div>
                </section>
              )}
            </aside>
          </div>
        )}
      </main>

      <AdminCatalog open={adminOpen} onClose={() => setAdminOpen(false)} onChanged={() => void load()} />
      <CourseManager open={managerOpen} onClose={() => setManagerOpen(false)} onChanged={() => void load()} />
      <AccountSettings open={accountOpen} email={userEmail} onClose={() => setAccountOpen(false)} onDeleted={onAccountDeleted} onSignedOut={onSignOut} />
    </div>
  );
}
