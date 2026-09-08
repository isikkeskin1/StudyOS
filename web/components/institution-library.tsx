"use client";

import Link from "next/link";
import { useCallback, useEffect, useMemo, useState } from "react";

import { BrandMark, UiIcon } from "@/components/ui-icon";

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

async function requestJson<T>(url: string, init?: RequestInit): Promise<T> {
  const response = await fetch(url, { ...init, cache: "no-store" });
  if (!response.ok) {
    let detail = `${response.status} ${response.statusText}`;
    try {
      const body = (await response.json()) as { detail?: string };
      if (body.detail) detail = body.detail;
    } catch {
      // Keep the HTTP fallback.
    }
    throw new Error(detail);
  }
  return (await response.json()) as T;
}

function formatBytes(value: number) {
  if (value < 1024) return `${value} B`;
  if (value < 1024 * 1024) return `${(value / 1024).toFixed(1)} KB`;
  return `${(value / (1024 * 1024)).toFixed(1)} MB`;
}

export function InstitutionLibrary() {
  const [courses, setCourses] = useState<CatalogCourse[]>([]);
  const [courseId, setCourseId] = useState<string | null>(null);
  const [folderId, setFolderId] = useState<string | null>(null);
  const [library, setLibrary] = useState<LibraryPayload | null>(null);
  const [selected, setSelected] = useState<Set<string>>(new Set());
  const [preview, setPreview] = useState<LibraryDocument | null>(null);
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);

  const loadCourses = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const list = await requestJson<CatalogCourse[]>("/api/v1/catalog/courses");
      setCourses(list);
      setCourseId((current) => current ?? list[0]?.id ?? null);
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "Could not load the institutional library.");
    } finally {
      setLoading(false);
    }
  }, []);

  const loadLibrary = useCallback(async (nextCourseId: string, nextFolderId: string | null) => {
    setLoading(true);
    setError(null);
    try {
      const params = nextFolderId ? `?folder_id=${encodeURIComponent(nextFolderId)}` : "";
      const payload = await requestJson<LibraryPayload>(`/api/v1/catalog/courses/${nextCourseId}/library${params}`);
      setLibrary(payload);
      setSelected(new Set());
      setPreview(null);
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "Could not open this library folder.");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void loadCourses();
  }, [loadCourses]);

  useEffect(() => {
    if (!courseId) {
      setLibrary(null);
      return;
    }
    void loadLibrary(courseId, folderId);
  }, [courseId, folderId, loadLibrary]);

  const allSelected = useMemo(
    () => Boolean(library?.documents.length) && library!.documents.every((document) => selected.has(document.id)),
    [library, selected],
  );

  const chooseCourse = (id: string) => {
    setCourseId(id);
    setFolderId(null);
    setNotice(null);
  };

  const openFolder = (id: string | null) => {
    setFolderId(id);
    setNotice(null);
  };

  const toggleDocument = (id: string) => {
    setSelected((current) => {
      const next = new Set(current);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  };

  const toggleAll = () => {
    if (!library) return;
    setSelected(allSelected ? new Set() : new Set(library.documents.map((document) => document.id)));
  };

  const downloadPack = async () => {
    if (!courseId || selected.size === 0) return;
    setBusy(true);
    setError(null);
    try {
      const response = await fetch(`/api/v1/catalog/courses/${courseId}/download-pack`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ document_ids: Array.from(selected) }),
      });
      if (!response.ok) {
        let detail = "Could not build the document pack.";
        try {
          const body = (await response.json()) as { detail?: string };
          if (body.detail) detail = body.detail;
        } catch {
          // Keep fallback.
        }
        throw new Error(detail);
      }
      const blob = await response.blob();
      const url = URL.createObjectURL(blob);
      const anchor = document.createElement("a");
      anchor.href = url;
      anchor.download = `${library?.catalog.name ?? "studyos"}-pack.zip`;
      document.body.appendChild(anchor);
      anchor.click();
      anchor.remove();
      URL.revokeObjectURL(url);
      setNotice(`${selected.size} document${selected.size === 1 ? "" : "s"} packaged for download.`);
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "Could not download the selected pack.");
    } finally {
      setBusy(false);
    }
  };

  const enroll = async () => {
    if (!courseId) return;
    setBusy(true);
    setError(null);
    try {
      const course = await requestJson<{ name: string }>(`/api/v1/catalog/courses/${courseId}/enroll`, { method: "POST" });
      setNotice(`${course.name} was added to your StudyOS courses with its institutional material.`);
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "Could not add this institutional course.");
    } finally {
      setBusy(false);
    }
  };

  return (
    <main className="institution-library-shell">
      <header className="institution-library-topbar">
        <Link href="/" className="institution-library-brand"><BrandMark /><strong>StudyOS<span>.</span></strong></Link>
        <div><span>Institutional Library</span><Link href="/">Back to Today</Link></div>
      </header>

      <div className="institution-library-layout">
        <aside className="institution-library-courses">
          <p>Available institutions</p>
          {courses.map((course) => (
            <button key={course.id} className={courseId === course.id ? "active" : ""} onClick={() => chooseCourse(course.id)}>
              <span>{course.institution_code ?? course.institution_name}</span>
              <strong>{course.name}</strong>
              <small>{course.course_code ?? "Course library"}{course.academic_year ? ` · ${course.academic_year}` : ""}</small>
            </button>
          ))}
          {!loading && courses.length === 0 && <div className="institution-library-empty-mini">No institutional libraries have been published yet.</div>}
        </aside>

        <section className="institution-library-main">
          {error && <div className="error-banner" role="alert"><span>{error}</span></div>}
          {notice && <div className="setup-message">{notice}</div>}

          {library ? (
            <>
              <header className="institution-library-heading">
                <div>
                  <span>{library.catalog.institution_name}</span>
                  <h1>{library.catalog.name}</h1>
                  <p>{library.catalog.description ?? "Official and curated institutional course material available inside StudyOS."}</p>
                </div>
                <button className="primary-button" disabled={busy} onClick={() => void enroll()}><UiIcon name="plus" />Add course to StudyOS</button>
              </header>

              <div className="institution-library-breadcrumbs" aria-label="Folder path">
                <button onClick={() => openFolder(null)}>Library</button>
                {library.breadcrumbs.map((folder) => <button key={folder.id} onClick={() => openFolder(folder.id)}><span>/</span>{folder.name}</button>)}
              </div>

              <div className="institution-library-toolbar">
                <div><strong>{library.folders.length}</strong> folders · <strong>{library.documents.length}</strong> files</div>
                <div>
                  <button className="ghost-button" disabled={!library.documents.length} onClick={toggleAll}>{allSelected ? "Clear selection" : "Select files"}</button>
                  <button className="primary-button" disabled={busy || selected.size === 0} onClick={() => void downloadPack()}>{busy ? "Building pack…" : `Download pack${selected.size ? ` (${selected.size})` : ""}`}</button>
                </div>
              </div>

              <div className="institution-library-browser">
                {library.current_folder && (
                  <button className="institution-folder-row back" onClick={() => openFolder(library.current_folder?.parent_id ?? null)}>
                    <span className="institution-file-icon"><UiIcon name="arrow" /></span><div><strong>..</strong><small>Parent folder</small></div>
                  </button>
                )}
                {library.folders.map((folder) => (
                  <button key={folder.id} className="institution-folder-row" onClick={() => openFolder(folder.id)}>
                    <span className="institution-file-icon"><UiIcon name="layers" /></span><div><strong>{folder.name}</strong><small>Folder</small></div><UiIcon name="arrow" />
                  </button>
                ))}
                {library.documents.map((document) => (
                  <div className="institution-document-row" key={document.id}>
                    <label className="institution-select"><input type="checkbox" checked={selected.has(document.id)} onChange={() => toggleDocument(document.id)} /><span /></label>
                    <button className="institution-document-open" onClick={() => document.previewable && setPreview(document)} disabled={!document.previewable}>
                      <span className="institution-file-icon"><UiIcon name="sources" /></span>
                      <div><strong>{document.original_filename}</strong><small>{document.extension.replace(".", "").toUpperCase()} · {formatBytes(document.size_bytes)}</small></div>
                    </button>
                    {document.previewable ? <button className="text-action" onClick={() => setPreview(document)}>Preview</button> : <span className="institution-no-preview">No inline preview</span>}
                    <a className="institution-download" href={`/api/v1/catalog/courses/${courseId}/documents/${document.id}/file?download=true`}><UiIcon name="arrow" />Download</a>
                  </div>
                ))}
                {!loading && library.folders.length === 0 && library.documents.length === 0 && <div className="institution-library-empty"><UiIcon name="sources" /><strong>This folder is empty.</strong><span>Choose another folder or return to the course root.</span></div>}
              </div>
            </>
          ) : loading ? <div className="institution-library-loading">Opening institutional library…</div> : null}
        </section>
      </div>

      {preview && courseId && (
        <div className="institution-preview-backdrop" role="presentation" onMouseDown={(event) => event.target === event.currentTarget && setPreview(null)}>
          <section className="institution-preview" role="dialog" aria-modal="true" aria-label={`Preview ${preview.original_filename}`}>
            <header><div><span>PDF viewer</span><strong>{preview.original_filename}</strong></div><button onClick={() => setPreview(null)}>×</button></header>
            <iframe title={preview.original_filename} src={`/api/v1/catalog/courses/${courseId}/documents/${preview.id}/file`} />
          </section>
        </div>
      )}

      <style jsx global>{`
        .institution-library-shell{min-height:100vh;background:#0a0c0b;color:#e8ece9}.institution-library-topbar{height:64px;display:flex;align-items:center;justify-content:space-between;padding:0 26px;border-bottom:1px solid #242927;background:#0a0c0bf2;position:sticky;top:0;z-index:20}.institution-library-brand{display:flex;align-items:center;gap:9px;color:inherit;text-decoration:none}.institution-library-brand .brand-mark{width:31px;height:31px}.institution-library-brand strong{font-size:15px;letter-spacing:-.04em}.institution-library-brand strong span{color:#b6ebce}.institution-library-topbar>div{display:flex;align-items:center;gap:20px;font-size:10px;color:#7e8883;text-transform:uppercase;letter-spacing:.06em}.institution-library-topbar a{color:#a9b3ae;text-decoration:none}.institution-library-layout{display:grid;grid-template-columns:280px minmax(0,1fr);min-height:calc(100vh - 64px)}.institution-library-courses{border-right:1px solid #232825;padding:30px 18px;background:#0d100f}.institution-library-courses>p{padding:0 10px 10px;color:#59635e;font-size:9px;text-transform:uppercase;letter-spacing:.08em}.institution-library-courses>button{width:100%;display:grid;text-align:left;gap:4px;padding:13px 12px;margin:2px 0;border:1px solid transparent;border-radius:8px;background:transparent;color:#d8dedb}.institution-library-courses>button:hover,.institution-library-courses>button.active{background:#131815;border-color:#29312d}.institution-library-courses>button span{font-size:8px;color:#65716b;text-transform:uppercase;letter-spacing:.07em}.institution-library-courses>button strong{font-size:11px;font-weight:560}.institution-library-courses>button small{font-size:8px;color:#66716b}.institution-library-empty-mini{padding:14px 10px;color:#68736d;font-size:10px;line-height:1.6}.institution-library-main{min-width:0;padding:clamp(30px,5vw,72px)}.institution-library-heading{display:flex;align-items:flex-start;justify-content:space-between;gap:32px;padding-bottom:32px;border-bottom:1px solid #262c29}.institution-library-heading>div>span{font-size:9px;color:#718079;text-transform:uppercase;letter-spacing:.08em}.institution-library-heading h1{margin:8px 0 12px;font-size:clamp(34px,5vw,62px);line-height:1;letter-spacing:-.06em;font-weight:560}.institution-library-heading p{max-width:720px;color:#7f8a84;font-size:11px;line-height:1.7}.institution-library-heading .primary-button{display:flex;align-items:center;gap:7px;white-space:nowrap}.institution-library-heading .ui-icon{width:14px;height:14px}.institution-library-breadcrumbs{display:flex;flex-wrap:wrap;align-items:center;gap:4px;padding:18px 0;border-bottom:1px solid #202522}.institution-library-breadcrumbs button{border:0;background:none;color:#a9b4ae;font-size:10px}.institution-library-breadcrumbs button span{margin-right:7px;color:#4c5550}.institution-library-toolbar{min-height:58px;display:flex;align-items:center;justify-content:space-between;gap:20px;color:#66716b;font-size:9px}.institution-library-toolbar>div:last-child{display:flex;gap:8px}.institution-library-browser{border-top:1px solid #2a302d}.institution-folder-row,.institution-document-row{width:100%;min-height:66px;border:0;border-bottom:1px solid #222724;background:transparent;color:inherit}.institution-folder-row{display:grid;grid-template-columns:38px 1fr 20px;align-items:center;text-align:left;gap:12px}.institution-folder-row>div,.institution-document-open>div{display:grid;gap:3px}.institution-folder-row strong,.institution-document-open strong{font-size:11px;font-weight:540;overflow-wrap:anywhere}.institution-folder-row small,.institution-document-open small{font-size:8px;color:#616c66}.institution-folder-row>.ui-icon{width:14px;height:14px;color:#5d6862}.institution-folder-row:hover,.institution-document-row:hover{background:#0f1311}.institution-file-icon{width:32px;height:32px;display:grid;place-items:center;border:1px solid #2b332f;border-radius:7px;background:#121714;color:#88ad99}.institution-file-icon .ui-icon{width:15px;height:15px}.institution-document-row{display:grid;grid-template-columns:28px minmax(0,1fr) auto auto;align-items:center;gap:10px}.institution-select{display:grid;place-items:center}.institution-select input{position:absolute;opacity:0}.institution-select span{width:14px;height:14px;border:1px solid #46514b;border-radius:4px}.institution-select input:checked+span{background:#b6ebce;border-color:#b6ebce;box-shadow:inset 0 0 0 3px #18231d}.institution-document-open{display:grid;grid-template-columns:38px minmax(0,1fr);align-items:center;gap:12px;text-align:left;border:0;background:none;color:inherit}.institution-document-open:disabled{cursor:default;opacity:1}.institution-no-preview{color:#59635e;font-size:8px}.institution-download{display:flex;align-items:center;gap:6px;color:#a9c8b8;text-decoration:none;font-size:9px}.institution-download .ui-icon{width:12px;height:12px}.institution-library-empty,.institution-library-loading{min-height:220px;display:flex;flex-direction:column;align-items:center;justify-content:center;text-align:center;color:#626e68;gap:8px}.institution-library-empty .ui-icon{width:22px;height:22px}.institution-library-empty strong{font-size:11px;color:#aab4af}.institution-library-empty span{font-size:9px}.institution-preview-backdrop{position:fixed;inset:0;z-index:100;background:#030504d9;display:grid;place-items:center;padding:24px}.institution-preview{width:min(1100px,96vw);height:min(880px,92vh);display:grid;grid-template-rows:58px 1fr;border:1px solid #303733;border-radius:12px;overflow:hidden;background:#0d100f;box-shadow:0 30px 100px #0009}.institution-preview header{display:flex;align-items:center;justify-content:space-between;padding:0 18px;border-bottom:1px solid #2a302d}.institution-preview header>div{display:grid;gap:2px}.institution-preview header span{font-size:8px;color:#647069;text-transform:uppercase;letter-spacing:.07em}.institution-preview header strong{font-size:11px}.institution-preview header button{width:34px;height:34px;border:0;background:none;color:#9ba69f;font-size:20px}.institution-preview iframe{width:100%;height:100%;border:0;background:white}@media(max-width:820px){.institution-library-layout{grid-template-columns:1fr}.institution-library-courses{border-right:0;border-bottom:1px solid #232825;display:flex;gap:6px;overflow:auto;padding:12px}.institution-library-courses>p{display:none}.institution-library-courses>button{min-width:190px}.institution-library-main{padding:28px 16px}.institution-library-heading{display:grid}.institution-library-heading .primary-button{width:100%;justify-content:center}.institution-library-toolbar{align-items:flex-start;flex-direction:column;padding:12px 0}.institution-document-row{grid-template-columns:28px minmax(0,1fr) auto}.institution-document-row>.text-action,.institution-no-preview{display:none}.institution-library-topbar{padding:0 14px}.institution-library-topbar>div>span{display:none}}@media(max-width:520px){.institution-document-row{grid-template-columns:24px minmax(0,1fr)}.institution-download{grid-column:2}.institution-preview-backdrop{padding:0}.institution-preview{width:100vw;height:100vh;border:0;border-radius:0}}
      `}</style>
    </main>
  );
}
