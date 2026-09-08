"use client";

import Link from "next/link";
import { useEffect, useState } from "react";

import { AdminCatalog } from "@/components/admin-catalog";
import { BrandMark, UiIcon } from "@/components/ui-icon";

type AdminUser = { email: string; is_admin: boolean };

export function AdminHome() {
  const [user, setUser] = useState<AdminUser | null>(null);
  const [loading, setLoading] = useState(true);
  const [catalogOpen, setCatalogOpen] = useState(false);

  useEffect(() => {
    fetch("/api/v1/auth/me", { cache: "no-store" })
      .then(async (response) => response.ok ? response.json() as Promise<AdminUser> : null)
      .then(setUser)
      .finally(() => setLoading(false));
  }, []);

  if (loading) return <main className="admin-home-shell"><div className="admin-home-loading">Loading admin…</div></main>;

  if (!user?.is_admin) {
    return <main className="admin-home-shell"><section className="admin-home-denied"><BrandMark /><h1>Admin only.</h1><p>This workspace is only available to StudyOS administrators.</p><Link href="/">Back to StudyOS</Link></section></main>;
  }

  return (
    <main className="admin-home-shell">
      <header className="admin-home-topbar">
        <Link href="/" className="admin-home-brand"><BrandMark /><strong>StudyOS.</strong></Link>
        <div><span>Admin</span><Link href="/">Today</Link></div>
      </header>

      <div className="admin-home-wrap">
        <div className="admin-home-intro">
          <span>StudyOS Admin</span>
          <h1>Keep the catalog clean.</h1>
          <p>Master courses, institutional material, and publishing live here.</p>
        </div>

        <section className="admin-home-grid">
          <button className="admin-home-card primary" onClick={() => setCatalogOpen(true)}>
            <span className="admin-home-icon"><UiIcon name="layers" /></span>
            <div><strong>Master courses</strong><small>Create courses, discover official sources, publish, and assign them.</small></div>
            <UiIcon name="arrow" />
          </button>
          <Link className="admin-home-card" href="/admin/library">
            <span className="admin-home-icon"><UiIcon name="sources" /></span>
            <div><strong>Institution files</strong><small>Build folders, upload PDFs and documents, preview files, and manage what students see.</small></div>
            <UiIcon name="arrow" />
          </Link>
          <Link className="admin-home-card" href="/library">
            <span className="admin-home-icon"><UiIcon name="courses" /></span>
            <div><strong>Student library</strong><small>Open the published library exactly as students see it.</small></div>
            <UiIcon name="arrow" />
          </Link>
        </section>

        <div className="admin-home-foot"><span>Signed in as</span><strong>{user.email}</strong></div>
      </div>

      <AdminCatalog open={catalogOpen} onClose={() => setCatalogOpen(false)} onChanged={() => undefined} />

      <style jsx global>{`
        .admin-home-shell{min-height:100vh;background:#f5f5f7;color:#1d1d1f;font-family:inherit}.admin-home-topbar{height:58px;display:flex;align-items:center;justify-content:space-between;padding:0 28px;border-bottom:1px solid #0000000d;background:#f8f8facf;backdrop-filter:saturate(180%) blur(24px);position:sticky;top:0;z-index:20}.admin-home-brand{display:flex;align-items:center;gap:9px;color:#1d1d1f;text-decoration:none}.admin-home-brand svg{width:28px;height:28px}.admin-home-brand strong{font-size:16px;letter-spacing:-.04em}.admin-home-topbar>div{display:flex;align-items:center;gap:18px;font-size:11px;color:#86868b}.admin-home-topbar a{color:#515154;text-decoration:none}.admin-home-wrap{width:min(100% - 48px,1040px);margin:0 auto;padding:76px 0 100px}.admin-home-intro{max-width:680px}.admin-home-intro>span{font-size:12px;color:#0071e3;font-weight:600}.admin-home-intro h1{margin:8px 0 14px;font-size:clamp(44px,6vw,72px);line-height:.98;letter-spacing:-.065em;font-weight:690}.admin-home-intro p{margin:0;color:#6e6e73;font-size:16px;line-height:1.5}.admin-home-grid{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:12px;margin-top:54px}.admin-home-card{min-height:160px;display:grid;grid-template-columns:44px 1fr 18px;gap:16px;align-items:center;padding:26px;border:1px solid #0000000a;border-radius:22px;background:#fff;color:#1d1d1f;text-decoration:none;text-align:left;box-shadow:0 1px 2px #00000008;cursor:pointer;font:inherit}.admin-home-card:hover{transform:translateY(-1px);box-shadow:0 10px 30px #0000000d}.admin-home-card.primary{grid-column:1/-1;min-height:190px;background:linear-gradient(145deg,#fff,#f2f6ff)}.admin-home-icon{width:44px;height:44px;display:grid;place-items:center;border-radius:13px;background:#f0f0f2;color:#515154}.admin-home-card.primary .admin-home-icon{background:#e8f2ff;color:#0071e3}.admin-home-card>div{display:grid;gap:6px}.admin-home-card strong{font-size:18px;letter-spacing:-.025em}.admin-home-card small{max-width:520px;color:#86868b;font-size:12px;line-height:1.55}.admin-home-card>svg{color:#c7c7cc}.admin-home-foot{display:flex;gap:8px;margin-top:34px;color:#8e8e93;font-size:11px}.admin-home-foot strong{color:#515154;font-weight:500}.admin-home-loading,.admin-home-denied{width:min(100% - 48px,700px);margin:0 auto;padding-top:120px}.admin-home-denied h1{font-size:44px;letter-spacing:-.05em}.admin-home-denied p{color:#6e6e73}.admin-home-denied a{color:#0071e3;text-decoration:none}@media(max-width:720px){.admin-home-topbar{padding:0 16px}.admin-home-wrap{width:min(100% - 32px,1040px);padding-top:48px}.admin-home-grid{grid-template-columns:1fr}.admin-home-card.primary{grid-column:auto}.admin-home-intro h1{font-size:48px}}
      `}</style>
    </main>
  );
}
