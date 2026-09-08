"use client";

import Link from "next/link";
import { FormEvent, useCallback, useEffect, useState } from "react";

import { BrandMark, UiIcon } from "@/components/ui-icon";

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

async function requestJson<T>(url: string, init?: RequestInit): Promise<T> {
  const response = await fetch(url, { ...init, cache: "no-store" });
  if (!response.ok) {
    let detail = `${response.status} ${response.statusText}`;
    try {
      const body = (await response.json()) as { detail?: string };
      if (body.detail) detail = body.detail;
    } catch {
      // Keep HTTP fallback.
    }
    throw new Error(detail);
  }
  return (await response.json()) as T;
}

function formatBytes(value: number) {
  if (value < 1024 * 1024) return `${Math.max(1, Math.round(value / 1024))} KB`;
  return `${(value / (1024 * 1024)).toFixed(1)} MB`;
}

export function AdminLibrary() {
  const [courses, setCourses] = useState<CatalogCourse[]>([]);
  const [courseId, setCourseId] = useState<string | null>(null);
  const [folderId, setFolderId] = useState<string | null>(null);
  const [library, setLibrary] = useState<LibraryPayload | null>(null);
  const [folderName, setFolderName] = useState("");
  const [files, setFiles] = useState<File[]>([]);
  const [preview, setPreview] = useState<LibraryDocument | null>(null);
  const [busy, setBusy] = useState(false);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);

  const loadCourses = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const list = await requestJson<CatalogCourse[]>("/api/v1/admin/catalog/courses");
      setCourses(list);
      setCourseId((current) => current ?? list[0]?.id ?? null);
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "Could not load admin libraries.");
    } finally {
      setLoading(false);
    }
  }, []);

  const loadLibrary = useCallback(async (nextCourseId: string, nextFolderId: string | null) => {
    setLoading(true);
    setError(null);
    try {
      const params = nextFolderId ? `?folder_id=${encodeURIComponent(nextFolderId)}` : "";
      setLibrary(await requestJson<LibraryPayload>(`/api/v1/admin/catalog/courses/${nextCourseId}/library${params}`));
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "Could not load this folder.");
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

  const createFolder = async (event: FormEvent) => {
    event.preventDefault();
    if (!courseId || !folderName.trim()) return;
    setBusy(true);
    setError(null);
    setNotice(null);
    try {
      await requestJson(`/api/v1/admin/catalog/courses/${courseId}/folders`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ name: folderName.trim(), parent_id: folderId }),
      });
      setFolderName("");
      await loadLibrary(courseId, folderId);
      setNotice("Folder created in the current location.");
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "Could not create folder.");
    } finally {
      setBusy(false);
    }
  };

  const uploadFiles = async () => {
    if (!courseId || files.length === 0) return;
    setBusy(true);
    setError(null);
    setNotice(null);
    let uploaded = 0;
    try {
      for (const file of files) {
        const body = new FormData();
        body.append("file", file);
        const params = folderId ? `?folder_id=${encodeURIComponent(folderId)}` : "";
        const response = await fetch(`/api/v1/admin/catalog/courses/${courseId}/documents${params}`, { method: "POST", body });
        if (!response.ok) {
          let detail = `${response.status} ${response.statusText}`;
          try {
            const payload = (await response.json()) as { detail?: string };
            if (payload.detail) detail = payload.detail;
          } catch {
            // Keep fallback.
          }
          throw new Error(`${file.name}: ${detail}`);
        }
        uploaded += 1;
      }
      setFiles([]);
      await Promise.all([loadLibrary(courseId, folderId), loadCourses()]);
      setNotice(`${uploaded} document${uploaded === 1 ? "" : "s"} uploaded, processed, and added to course intelligence.`);
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "Institutional upload failed.");
    } finally {
      setBusy(false);
    }
  };

  const chooseCourse = (id: string) => {
    setCourseId(id);
    setFolderId(null);
    setPreview(null);
    setNotice(null);
  };

  return (
    <main className="admin-library-shell">
      <header className="admin-library-topbar">
        <Link href="/" className="admin-library-brand"><BrandMark /><strong>StudyOS<span>.</span></strong></Link>
        <div><span>Admin · Institutional files</span><Link href="/admin">Admin home</Link><Link href="/library">Student library</Link><Link href="/">Today</Link></div>
      </header>

      <div className="admin-library-layout">
        <aside className="admin-library-course-list">
          <div className="admin-library-aside-head"><span>Master courses</span><small>Create and manage institutional courses from Admin.</small></div>
          {courses.map((course) => (
            <button key={course.id} className={courseId === course.id ? "active" : ""} onClick={() => chooseCourse(course.id)}>
              <span>{course.institution_code ?? course.institution_name}</span>
              <strong>{course.name}</strong>
              <small>{course.course_code ?? "No code"} · {course.published ? "Published" : "Draft"}</small>
            </button>
          ))}
          {!loading && courses.length === 0 && <div className="admin-library-no-courses">No master courses yet. Create your first one in Admin.</div>}
        </aside>

        <section className="admin-library-main">
          {error && <div className="error-banner" role="alert"><span>{error}</span></div>}
          {notice && <div className="setup-message">{notice}</div>}

          {library && courseId ? (
            <>
              <header className="admin-library-heading">
                <div><span>{library.catalog.institution_name}</span><h1>{library.catalog.name}</h1><p>Build the exact folder tree students will see. Uploading here also processes the material for institutional course intelligence.</p></div>
                <b className={library.catalog.published ? "manager-ready" : "manager-stale"}>{library.catalog.published ? "Published" : "Draft"}</b>
              </header>

              <div className="admin-library-breadcrumbs">
                <button onClick={() => setFolderId(null)}>Library</button>
                {library.breadcrumbs.map((folder) => <button key={folder.id} onClick={() => setFolderId(folder.id)}><span>/</span>{folder.name}</button>)}
              </div>

              <section className="admin-library-actions">
                <form onSubmit={createFolder}>
                  <label><span>New folder in {library.current_folder?.name ?? "Library"}</span><div><input value={folderName} onChange={(event) => setFolderName(event.target.value)} placeholder="Lectures, Past Exams, Week 01…" /><button className="ghost-button" disabled={busy || !folderName.trim()}><UiIcon name="plus" />Create folder</button></div></label>
                </form>
                <div className="admin-library-upload">
                  <label><span>Upload into {library.current_folder?.name ?? "Library"}</span><input type="file" multiple accept=".pdf,.docx,.pptx,.txt,.md" onChange={(event) => setFiles(Array.from(event.target.files ?? []))} /></label>
                  <button className="primary-button" type="button" disabled={busy || files.length === 0} onClick={() => void uploadFiles()}>{busy ? "Processing…" : files.length ? `Upload ${files.length} file${files.length === 1 ? "" : "s"}` : "Choose files first"}</button>
                </div>
              </section>

              <div className="admin-library-table-head"><span>{library.folders.length} folders</span><span>{library.documents.length} files in this folder</span></div>
              <div className="admin-library-browser">
                {library.current_folder && <button className="admin-folder-row" onClick={() => setFolderId(library.current_folder?.parent_id ?? null)}><span className="admin-library-icon"><UiIcon name="arrow" /></span><div><strong>..</strong><small>Parent folder</small></div></button>}
                {library.folders.map((folder) => <button className="admin-folder-row" key={folder.id} onClick={() => setFolderId(folder.id)}><span className="admin-library-icon"><UiIcon name="layers" /></span><div><strong>{folder.name}</strong><small>Folder · add more folders inside it</small></div><UiIcon name="arrow" /></button>)}
                {library.documents.map((document) => (
                  <div className="admin-document-row" key={document.id}>
                    <span className="admin-library-icon"><UiIcon name="sources" /></span>
                    <div><strong>{document.original_filename}</strong><small>{document.extension.replace(".", "").toUpperCase()} · {formatBytes(document.size_bytes)} · processed</small></div>
                    {document.previewable && <button className="text-action" onClick={() => setPreview(document)}>Preview</button>}
                    <a href={`/api/v1/admin/catalog/courses/${courseId}/documents/${document.id}/file?download=true`}>Download</a>
                  </div>
                ))}
                {!loading && library.folders.length === 0 && library.documents.length === 0 && <div className="admin-library-empty"><strong>Empty folder.</strong><span>Create a subfolder or upload material here.</span></div>}
              </div>
            </>
          ) : loading ? <div className="admin-library-loading">Loading institutional files…</div> : null}
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
        .admin-library-shell{min-height:100vh;background:#090b0a;color:#e8ece9}.admin-library-topbar{height:64px;display:flex;align-items:center;justify-content:space-between;padding:0 26px;border-bottom:1px solid #242a27;background:#090b0af2;position:sticky;top:0;z-index:20}.admin-library-brand{display:flex;align-items:center;gap:9px;color:inherit;text-decoration:none}.admin-library-brand .brand-mark{width:31px;height:31px}.admin-library-brand strong{font-size:15px;letter-spacing:-.04em}.admin-library-brand strong span{color:#b6ebce}.admin-library-topbar>div{display:flex;align-items:center;gap:18px;color:#78847d;font-size:9px;text-transform:uppercase;letter-spacing:.06em}.admin-library-topbar a{color:#a7b2ac;text-decoration:none}.admin-library-layout{display:grid;grid-template-columns:290px minmax(0,1fr);min-height:calc(100vh - 64px)}.admin-library-course-list{padding:26px 17px;border-right:1px solid #222825;background:#0c0f0d}.admin-library-aside-head{display:grid;gap:4px;padding:0 10px 14px}.admin-library-aside-head span{font-size:9px;color:#78847d;text-transform:uppercase;letter-spacing:.07em}.admin-library-aside-head small{font-size:8px;color:#525d57;line-height:1.5}.admin-library-course-list>button{width:100%;display:grid;gap:4px;text-align:left;padding:13px 12px;margin:2px 0;border:1px solid transparent;border-radius:8px;background:transparent;color:#dce2de}.admin-library-course-list>button:hover,.admin-library-course-list>button.active{background:#131815;border-color:#2a332e}.admin-library-course-list>button span{font-size:8px;color:#6c7871;text-transform:uppercase;letter-spacing:.06em}.admin-library-course-list>button strong{font-size:11px;font-weight:560}.admin-library-course-list>button small{font-size:8px;color:#5f6b65}.admin-library-no-courses{padding:12px 10px;color:#66716b;font-size:9px;line-height:1.6}.admin-library-main{min-width:0;padding:clamp(30px,5vw,68px)}.admin-library-heading{display:flex;align-items:flex-start;justify-content:space-between;gap:24px;padding-bottom:28px;border-bottom:1px solid #272e2a}.admin-library-heading>div>span{font-size:9px;color:#718079;text-transform:uppercase;letter-spacing:.08em}.admin-library-heading h1{margin:8px 0 10px;font-size:clamp(34px,5vw,60px);letter-spacing:-.06em;line-height:1;font-weight:560}.admin-library-heading p{max-width:760px;color:#7d8982;font-size:11px;line-height:1.7}.admin-library-breadcrumbs{display:flex;flex-wrap:wrap;gap:5px;padding:17px 0;border-bottom:1px solid #202622}.admin-library-breadcrumbs button{border:0;background:none;color:#a7b3ac;font-size:10px}.admin-library-breadcrumbs span{margin-right:7px;color:#4b5550}.admin-library-actions{display:grid;grid-template-columns:1fr 1fr;gap:22px;padding:22px 0;border-bottom:1px solid #292f2c}.admin-library-actions label{display:grid;gap:8px}.admin-library-actions label>span{font-size:9px;color:#6e7a73;text-transform:uppercase;letter-spacing:.06em}.admin-library-actions form label>div{display:grid;grid-template-columns:1fr auto;gap:8px}.admin-library-actions input[type=text],.admin-library-actions form input{min-height:40px;border:1px solid #2b332f;border-radius:7px;background:#101412;color:#e2e7e4;padding:0 11px}.admin-library-upload{display:grid;grid-template-columns:1fr auto;gap:8px;align-items:end}.admin-library-upload input{font-size:9px;color:#718079}.admin-library-upload .primary-button,.admin-library-actions .ghost-button{display:flex;align-items:center;gap:6px;justify-content:center}.admin-library-actions .ui-icon{width:13px;height:13px}.admin-library-table-head{display:flex;justify-content:space-between;padding:15px 0;color:#5d6962;font-size:9px}.admin-library-browser{border-top:1px solid #2a312d}.admin-folder-row,.admin-document-row{width:100%;min-height:66px;border:0;border-bottom:1px solid #232925;background:transparent;color:inherit}.admin-folder-row{display:grid;grid-template-columns:38px 1fr 20px;align-items:center;text-align:left;gap:12px}.admin-folder-row:hover,.admin-document-row:hover{background:#101411}.admin-folder-row>div,.admin-document-row>div{display:grid;gap:3px}.admin-folder-row strong,.admin-document-row strong{font-size:11px;font-weight:540;overflow-wrap:anywhere}.admin-folder-row small,.admin-document-row small{font-size:8px;color:#616e67}.admin-folder-row>.ui-icon{width:14px;height:14px;color:#5f6a64}.admin-library-icon{width:32px;height:32px;display:grid;place-items:center;border:1px solid #2c342f;border-radius:7px;background:#121714;color:#86aa97}.admin-library-icon .ui-icon{width:15px;height:15px}.admin-document-row{display:grid;grid-template-columns:38px minmax(0,1fr) auto auto;align-items:center;gap:12px}.admin-document-row>a{color:#a7c7b6;text-decoration:none;font-size:9px}.admin-library-empty,.admin-library-loading{min-height:200px;display:flex;flex-direction:column;align-items:center;justify-content:center;gap:7px;color:#65716a}.admin-library-empty strong{font-size:11px;color:#aab5af}.admin-library-empty span{font-size:9px}.admin-preview-backdrop{position:fixed;inset:0;z-index:100;background:#020403dc;display:grid;place-items:center;padding:24px}.admin-preview{width:min(1100px,96vw);height:min(880px,92vh);display:grid;grid-template-rows:58px 1fr;border:1px solid #303733;border-radius:12px;overflow:hidden;background:#0d100f}.admin-preview header{display:flex;align-items:center;justify-content:space-between;padding:0 18px;border-bottom:1px solid #2a302d}.admin-preview header>div{display:grid;gap:2px}.admin-preview header span{font-size:8px;color:#66716b;text-transform:uppercase}.admin-preview header strong{font-size:11px}.admin-preview header button{width:34px;height:34px;border:0;background:none;color:#a5afa9;font-size:20px}.admin-preview iframe{width:100%;height:100%;border:0;background:white}@media(max-width:900px){.admin-library-layout{grid-template-columns:1fr}.admin-library-course-list{border-right:0;border-bottom:1px solid #222825;display:flex;gap:6px;overflow:auto;padding:12px}.admin-library-aside-head{display:none}.admin-library-course-list>button{min-width:190px}.admin-library-main{padding:28px 16px}.admin-library-actions{grid-template-columns:1fr}.admin-library-topbar{padding:0 14px}.admin-library-topbar>div>span{display:none}}@media(max-width:560px){.admin-library-upload{grid-template-columns:1fr}.admin-document-row{grid-template-columns:38px minmax(0,1fr)}.admin-document-row>.text-action,.admin-document-row>a{grid-column:2}.admin-preview-backdrop{padding:0}.admin-preview{width:100vw;height:100vh;border:0;border-radius:0}}
      `}</style>
    </main>
  );
}
