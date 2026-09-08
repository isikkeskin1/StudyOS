"use client";

import Link from "next/link";
import { useCallback, useEffect, useState } from "react";

import { BrandMark, UiIcon } from "@/components/ui-icon";

type AdminUser = { email: string; is_admin: boolean };

type CatalogCourse = {
  id: string;
  institution_name: string;
  institution_code: string | null;
  course_code: string | null;
  academic_year: string | null;
  published: boolean;
  name: string;
  document_count: number;
};

type CatalogFolder = {
  id: string;
  catalog_course_id: string;
  parent_id: string | null;
  name: string;
  created_at: string;
};

type LibraryDocument = {
  id: string;
  folder_id: string | null;
  original_filename: string;
  content_type: string | null;
  extension: string;
  size_bytes: number;
  status: string;
  created_at: string;
  previewable: boolean;
};

type LibraryPayload = {
  catalog: CatalogCourse;
  current_folder: CatalogFolder | null;
  breadcrumbs: CatalogFolder[];
  folders: CatalogFolder[];
  documents: LibraryDocument[];
};

type CatalogSource = {
  id: string;
  url: string;
  title: string | null;
  source_kind: string;
  status: string;
  imported_document_id: string | null;
};

async function requestJson<T>(url: string, init?: RequestInit): Promise<T> {
  const response = await fetch(url, { ...init, cache: "no-store" });
  if (!response.ok) {
    let detail = `${response.status} ${response.statusText}`;
    try {
      const body = (await response.json()) as { detail?: string };
      if (body.detail) detail = body.detail;
    } catch {
      // Preserve HTTP fallback.
    }
    throw new Error(detail);
  }
  if (response.status === 204) return undefined as T;
  return (await response.json()) as T;
}

function formatBytes(value: number) {
  if (value < 1024 * 1024) return `${Math.max(1, Math.round(value / 1024))} KB`;
  return `${(value / (1024 * 1024)).toFixed(1)} MB`;
}

function sourceName(source: CatalogSource) {
  if (source.title?.trim()) return source.title.trim();
  try {
    return new URL(source.url).hostname;
  } catch {
    return source.url;
  }
}

export function AdminResourceManager() {
  const [user, setUser] = useState<AdminUser | null>(null);
  const [courses, setCourses] = useState<CatalogCourse[]>([]);
  const [courseId, setCourseId] = useState<string | null>(null);
  const [folderId, setFolderId] = useState<string | null>(null);
  const [library, setLibrary] = useState<LibraryPayload | null>(null);
  const [sources, setSources] = useState<CatalogSource[]>([]);
  const [preview, setPreview] = useState<LibraryDocument | null>(null);
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);

  const loadCourses = useCallback(async (preferred?: string | null) => {
    const list = await requestJson<CatalogCourse[]>("/api/v1/admin/catalog/courses");
    setCourses(list);
    setCourseId((current) => {
      const candidate = preferred === undefined ? current : preferred;
      if (candidate && list.some((course) => course.id === candidate)) return candidate;
      return list[0]?.id ?? null;
    });
    return list;
  }, []);

  const loadCurrent = useCallback(async (nextCourseId: string, nextFolderId: string | null) => {
    const params = nextFolderId ? `?folder_id=${encodeURIComponent(nextFolderId)}` : "";
    const [nextLibrary, nextSources] = await Promise.all([
      requestJson<LibraryPayload>(`/api/v1/admin/catalog/courses/${nextCourseId}/library${params}`),
      requestJson<CatalogSource[]>(`/api/v1/admin/catalog/courses/${nextCourseId}/sources`),
    ]);
    setLibrary(nextLibrary);
    setSources(nextSources);
  }, []);

  useEffect(() => {
    let cancelled = false;
    void requestJson<AdminUser>("/api/v1/auth/me")
      .then(async (resolved) => {
        if (cancelled) return;
        setUser(resolved);
        if (!resolved.is_admin) return;
        await loadCourses();
      })
      .catch((caught) => {
        if (!cancelled) setError(caught instanceof Error ? caught.message : "Could not open admin management.");
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [loadCourses]);

  useEffect(() => {
    if (!user?.is_admin || !courseId) {
      setLibrary(null);
      setSources([]);
      return;
    }
    setLoading(true);
    setError(null);
    void loadCurrent(courseId, folderId)
      .catch((caught) => setError(caught instanceof Error ? caught.message : "Could not load course resources."))
      .finally(() => setLoading(false));
  }, [courseId, folderId, loadCurrent, user?.is_admin]);

  const chooseCourse = (id: string) => {
    setCourseId(id);
    setFolderId(null);
    setPreview(null);
    setNotice(null);
  };

  const deleteDocument = async (document: LibraryDocument) => {
    if (!courseId) return;
    if (!window.confirm(`Delete “${document.original_filename}” from this institutional course?\n\nThe master course stays intact. Existing student copies are not changed.`)) return;
    setBusy(true);
    setError(null);
    setNotice(null);
    try {
      await requestJson<void>(
        `/api/v1/admin/catalog/courses/${courseId}/documents/${document.id}`,
        { method: "DELETE" },
      );
      if (preview?.id === document.id) setPreview(null);
      await Promise.all([loadCurrent(courseId, folderId), loadCourses(courseId)]);
      setNotice(`Deleted ${document.original_filename}.`);
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "Could not delete this resource.");
    } finally {
      setBusy(false);
    }
  };

  const deleteSource = async (source: CatalogSource) => {
    if (!courseId) return;
    if (!window.confirm(`Delete this discovered source?\n\n${sourceName(source)}\n\nAny document already imported from it stays in the course unless you delete that file separately.`)) return;
    setBusy(true);
    setError(null);
    setNotice(null);
    try {
      await requestJson<void>(
        `/api/v1/admin/catalog/courses/${courseId}/sources/${source.id}`,
        { method: "DELETE" },
      );
      await loadCurrent(courseId, folderId);
      setNotice("Discovered source removed.");
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "Could not delete this source.");
    } finally {
      setBusy(false);
    }
  };

  const deleteCourse = async () => {
    if (!courseId || !library) return;
    const expected = library.catalog.name;
    const typed = window.prompt(
      `Permanently delete “${expected}” and all of its institutional folders, files, and discovered sources?\n\nExisting courses already copied to students will remain.\n\nType the course name to confirm:`,
    );
    if (typed !== expected) {
      if (typed !== null) setNotice("Course deletion cancelled — the name did not match.");
      return;
    }

    setBusy(true);
    setError(null);
    setNotice(null);
    try {
      await requestJson<void>(`/api/v1/admin/catalog/courses/${courseId}`, { method: "DELETE" });
      setPreview(null);
      setFolderId(null);
      setLibrary(null);
      setSources([]);
      await loadCourses(null);
      setNotice(`${expected} was permanently deleted from the institutional catalog.`);
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "Could not delete this course.");
    } finally {
      setBusy(false);
    }
  };

  if (loading && user === null) {
    return <main className="admin-manage-shell"><div className="admin-manage-loading">Opening resource manager…</div></main>;
  }

  if (!user?.is_admin) {
    return (
      <main className="admin-manage-shell">
        <section className="admin-manage-denied"><BrandMark /><h1>Admin only.</h1><p>This workspace can permanently change institutional content.</p><Link href="/">Back to StudyOS</Link></section>
      </main>
    );
  }

  return (
    <main className="admin-manage-shell">
      <header className="admin-manage-topbar">
        <Link href="/" className="admin-manage-brand"><BrandMark /><strong>StudyOS<span>.</span></strong></Link>
        <nav><span>Admin · Manage</span><Link href="/admin">Admin home</Link><Link href="/admin/library">Institution files</Link><Link href="/">Today</Link></nav>
      </header>

      <div className="admin-manage-layout">
        <aside className="admin-manage-courses">
          <div className="admin-manage-aside-head"><span>Master courses</span><small>Select exactly what you want to remove.</small></div>
          {courses.map((course) => (
            <button key={course.id} className={courseId === course.id ? "active" : ""} onClick={() => chooseCourse(course.id)}>
              <span>{course.institution_code ?? course.institution_name}</span>
              <strong>{course.name}</strong>
              <small>{course.document_count} files · {course.published ? "Published" : "Draft"}</small>
            </button>
          ))}
          {!loading && courses.length === 0 && <div className="admin-manage-empty-list">No institutional courses.</div>}
        </aside>

        <section className="admin-manage-main">
          {error && <div className="error-banner" role="alert"><span>{error}</span></div>}
          {notice && <div className="setup-message">{notice}</div>}

          {library && courseId ? (
            <>
              <header className="admin-manage-heading">
                <div>
                  <span>{library.catalog.institution_name}</span>
                  <h1>{library.catalog.name}</h1>
                  <p>Delete individual files and sources here, or permanently remove the master course. Student copies already enrolled are independent and stay untouched.</p>
                </div>
                <div className="admin-manage-heading-actions">
                  <b className={library.catalog.published ? "manager-ready" : "manager-stale"}>{library.catalog.published ? "Published" : "Draft"}</b>
                  <button className="admin-danger-button" type="button" disabled={busy} onClick={() => void deleteCourse()}>Delete course</button>
                </div>
              </header>

              <section className="admin-manage-section">
                <div className="admin-manage-section-head"><div><span>Institution files</span><h2>Resources</h2></div><Link href="/admin/library">Add or organize files</Link></div>
                <div className="admin-manage-breadcrumbs">
                  <button onClick={() => setFolderId(null)}>Library</button>
                  {library.breadcrumbs.map((folder) => <button key={folder.id} onClick={() => setFolderId(folder.id)}><span>/</span>{folder.name}</button>)}
                </div>
                <div className="admin-manage-browser">
                  {library.current_folder && <button className="admin-manage-folder" onClick={() => setFolderId(library.current_folder?.parent_id ?? null)}><UiIcon name="arrow" /><div><strong>..</strong><small>Parent folder</small></div></button>}
                  {library.folders.map((folder) => <button className="admin-manage-folder" key={folder.id} onClick={() => setFolderId(folder.id)}><UiIcon name="layers" /><div><strong>{folder.name}</strong><small>Folder</small></div><UiIcon name="arrow" /></button>)}
                  {library.documents.map((document) => (
                    <div className="admin-manage-document" key={document.id}>
                      <span className="admin-manage-file-icon"><UiIcon name="sources" /></span>
                      <div><strong>{document.original_filename}</strong><small>{document.extension.replace(".", "").toUpperCase()} · {formatBytes(document.size_bytes)}</small></div>
                      {document.previewable && <button className="text-action" onClick={() => setPreview(document)}>Preview</button>}
                      <a href={`/api/v1/admin/catalog/courses/${courseId}/documents/${document.id}/file?download=true`}>Download</a>
                      <button className="admin-row-delete" disabled={busy} onClick={() => void deleteDocument(document)}>Delete</button>
                    </div>
                  ))}
                  {!loading && library.folders.length === 0 && library.documents.length === 0 && <div className="admin-manage-empty"><strong>Nothing in this folder.</strong><span>You can add resources from Institution files.</span></div>}
                </div>
              </section>

              <section className="admin-manage-section">
                <div className="admin-manage-section-head"><div><span>Discovery history</span><h2>Sources</h2></div><small>{sources.length} discovered</small></div>
                <div className="admin-manage-sources">
                  {sources.map((source) => (
                    <div className="admin-manage-source" key={source.id}>
                      <div><strong>{sourceName(source)}</strong><a href={source.url} target="_blank" rel="noreferrer">{source.url}</a></div>
                      <span>{source.source_kind.replaceAll("_", " ")} · {source.status}</span>
                      {source.imported_document_id && <small>Imported file retained separately</small>}
                      <button className="admin-row-delete" disabled={busy} onClick={() => void deleteSource(source)}>Delete source</button>
                    </div>
                  ))}
                  {!loading && sources.length === 0 && <div className="admin-manage-empty"><strong>No discovered sources.</strong><span>There is nothing to clean up here.</span></div>}
                </div>
              </section>
            </>
          ) : loading ? <div className="admin-manage-loading">Loading course resources…</div> : courses.length === 0 ? <div className="admin-manage-zero"><strong>Catalog is empty.</strong><Link href="/admin">Create a master course</Link></div> : null}
        </section>
      </div>

      {preview && courseId && (
        <div className="admin-preview-backdrop" role="presentation" onMouseDown={(event) => event.target === event.currentTarget && setPreview(null)}>
          <section className="admin-preview" role="dialog" aria-modal="true" aria-label={`Preview ${preview.original_filename}`}>
            <header><div><span>Institutional PDF</span><strong>{preview.original_filename}</strong></div><button onClick={() => setPreview(null)}>×</button></header>
            <iframe title={preview.original_filename} src={`/api/v1/admin/catalog/courses/${courseId}/documents/${preview.id}/file`} />
          </section>
        </div>
      )}

      <style jsx global>{`
        .admin-manage-shell{min-height:100vh;background:var(--ui-bg);color:var(--ui-text)}
        .admin-manage-topbar{height:60px;display:flex;align-items:center;justify-content:space-between;padding:0 24px;border-bottom:1px solid var(--ui-line);background:color-mix(in srgb,var(--ui-bg) 84%,transparent);backdrop-filter:blur(22px) saturate(150%);position:sticky;top:0;z-index:30}
        .admin-manage-brand{display:flex;align-items:center;gap:9px;color:var(--ui-text);text-decoration:none}.admin-manage-brand .brand-mark{width:30px;height:30px}.admin-manage-brand strong{font-size:16px;letter-spacing:-.04em}.admin-manage-brand strong span{color:var(--ui-accent)}
        .admin-manage-topbar nav{display:flex;align-items:center;gap:18px;color:var(--ui-faint);font-size:10px}.admin-manage-topbar a{color:var(--ui-text-2);text-decoration:none}
        .admin-manage-layout{display:grid;grid-template-columns:260px minmax(0,1fr);min-height:calc(100vh - 60px)}
        .admin-manage-courses{padding:24px 14px;border-right:1px solid var(--ui-line);background:var(--ui-bg-soft)}.admin-manage-aside-head{display:grid;gap:4px;padding:0 9px 14px}.admin-manage-aside-head span{font-size:9px;color:var(--ui-muted);text-transform:uppercase;letter-spacing:.08em}.admin-manage-aside-head small{font-size:9px;color:var(--ui-faint);line-height:1.5}
        .admin-manage-courses>button{width:100%;display:grid;gap:4px;padding:13px 11px;margin:2px 0;border:1px solid transparent;border-radius:10px;background:transparent;color:var(--ui-text);text-align:left}.admin-manage-courses>button:hover,.admin-manage-courses>button.active{background:var(--ui-surface);border-color:var(--ui-line)}.admin-manage-courses>button span{font-size:8px;color:var(--ui-muted);text-transform:uppercase;letter-spacing:.06em}.admin-manage-courses>button strong{font-size:12px}.admin-manage-courses>button small{font-size:9px;color:var(--ui-faint)}
        .admin-manage-main{min-width:0;padding:clamp(30px,5vw,68px)}.admin-manage-heading{display:flex;justify-content:space-between;align-items:flex-start;gap:28px;padding-bottom:28px;border-bottom:1px solid var(--ui-line)}.admin-manage-heading>div:first-child>span{font-size:10px;color:var(--ui-muted);text-transform:uppercase;letter-spacing:.08em}.admin-manage-heading h1{margin:8px 0 11px;font-size:clamp(38px,5vw,60px);line-height:1;letter-spacing:-.06em}.admin-manage-heading p{max-width:760px;color:var(--ui-muted);font-size:11px;line-height:1.65}.admin-manage-heading-actions{display:grid;justify-items:end;gap:12px;flex:0 0 auto}
        .admin-danger-button,.admin-row-delete{border:1px solid color-mix(in srgb,var(--ui-danger) 38%,transparent);background:color-mix(in srgb,var(--ui-danger) 9%,transparent);color:var(--ui-danger);border-radius:9px;font:inherit;cursor:pointer}.admin-danger-button{min-height:38px;padding:0 13px;font-size:10px;font-weight:650}.admin-row-delete{min-height:32px;padding:0 10px;font-size:9px}.admin-danger-button:hover,.admin-row-delete:hover{background:color-mix(in srgb,var(--ui-danger) 15%,transparent)}.admin-danger-button:disabled,.admin-row-delete:disabled{opacity:.45;cursor:wait}
        .admin-manage-section{margin-top:42px}.admin-manage-section-head{display:flex;align-items:flex-end;justify-content:space-between;gap:20px;margin-bottom:14px}.admin-manage-section-head span{font-size:9px;color:var(--ui-muted);text-transform:uppercase;letter-spacing:.08em}.admin-manage-section-head h2{margin-top:3px;font-size:22px;letter-spacing:-.035em}.admin-manage-section-head>a{color:var(--ui-accent);font-size:10px;text-decoration:none}.admin-manage-section-head>small{color:var(--ui-faint);font-size:9px}
        .admin-manage-breadcrumbs{display:flex;flex-wrap:wrap;gap:5px;padding:12px 0;border-block:1px solid var(--ui-line)}.admin-manage-breadcrumbs button{border:0;background:transparent;color:var(--ui-text-2);font-size:10px}.admin-manage-breadcrumbs span{margin-right:6px;color:var(--ui-faint)}
        .admin-manage-browser,.admin-manage-sources{border-bottom:1px solid var(--ui-line)}.admin-manage-folder,.admin-manage-document,.admin-manage-source{min-height:64px;border:0;border-bottom:1px solid var(--ui-line);background:transparent;color:var(--ui-text)}.admin-manage-folder{width:100%;display:grid;grid-template-columns:30px minmax(0,1fr) 18px;align-items:center;gap:10px;text-align:left}.admin-manage-folder>svg:first-child{transform:rotate(180deg)}.admin-manage-folder div,.admin-manage-document>div,.admin-manage-source>div{display:grid;gap:3px}.admin-manage-folder strong,.admin-manage-document strong,.admin-manage-source strong{font-size:11px}.admin-manage-folder small,.admin-manage-document small{color:var(--ui-faint);font-size:9px}
        .admin-manage-document{display:grid;grid-template-columns:34px minmax(0,1fr) auto auto auto;align-items:center;gap:12px}.admin-manage-file-icon{width:30px;height:30px;display:grid;place-items:center;border-radius:9px;background:var(--ui-surface-3);color:var(--ui-muted)}.admin-manage-document>a,.admin-manage-source a{color:var(--ui-accent);font-size:9px;text-decoration:none}
        .admin-manage-source{display:grid;grid-template-columns:minmax(0,1fr) auto auto auto;align-items:center;gap:14px;padding:11px 0}.admin-manage-source>div a{max-width:680px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}.admin-manage-source>span,.admin-manage-source>small{color:var(--ui-muted);font-size:9px}.admin-manage-source>small{color:var(--ui-faint)}
        .admin-manage-empty{display:grid;gap:5px;padding:28px 4px;color:var(--ui-text-2)}.admin-manage-empty strong{font-size:11px}.admin-manage-empty span{color:var(--ui-faint);font-size:9px}.admin-manage-empty-list{padding:12px 9px;color:var(--ui-faint);font-size:10px}.admin-manage-loading,.admin-manage-zero,.admin-manage-denied{padding:70px clamp(24px,5vw,68px);color:var(--ui-muted)}.admin-manage-zero{display:grid;gap:10px}.admin-manage-zero a,.admin-manage-denied a{color:var(--ui-accent);text-decoration:none}.admin-manage-denied{width:min(100% - 40px,700px);margin:auto;padding-top:120px}.admin-manage-denied h1{margin:18px 0 8px;font-size:44px;letter-spacing:-.05em}.admin-manage-denied p{margin-bottom:18px}
        @media(max-width:850px){.admin-manage-layout{grid-template-columns:1fr}.admin-manage-courses{display:flex;gap:7px;overflow-x:auto;border-right:0;border-bottom:1px solid var(--ui-line);padding:12px}.admin-manage-aside-head{display:none}.admin-manage-courses>button{min-width:180px;margin:0}.admin-manage-main{padding:28px 18px 90px}.admin-manage-heading{display:grid}.admin-manage-heading-actions{display:flex;align-items:center;justify-content:space-between}.admin-manage-document{grid-template-columns:34px minmax(0,1fr) auto}.admin-manage-document>a{display:none}.admin-manage-document .text-action{display:none}.admin-manage-source{grid-template-columns:minmax(0,1fr) auto}.admin-manage-source>span,.admin-manage-source>small{display:none}.admin-manage-topbar{padding:0 14px}.admin-manage-topbar nav>span,.admin-manage-topbar nav a:not(:last-child){display:none}}
      `}</style>
    </main>
  );
}
