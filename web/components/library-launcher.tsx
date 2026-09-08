"use client";

import { UiIcon } from "@/components/ui-icon";

export function LibraryLauncher({ isAdmin }: { isAdmin: boolean }) {
  return (
    <div className="library-launcher" aria-label="Institutional library shortcuts">
      <a href="/library"><UiIcon name="sources" /><span>Institutional library</span></a>
      {isAdmin && <a href="/admin/library"><UiIcon name="shield" /><span>Institution files</span></a>}
      <style jsx global>{`
        .library-launcher{position:fixed;right:18px;bottom:18px;z-index:45;display:flex;gap:8px;align-items:center}.library-launcher a{min-height:40px;display:flex;align-items:center;gap:8px;padding:0 13px;border:1px solid #2d3832;border-radius:9px;background:#0e1310e8;backdrop-filter:blur(16px);box-shadow:0 14px 38px #0005;color:#b7c6be;text-decoration:none;font-size:10px}.library-launcher a:hover{border-color:#466052;color:#d5e5dc;background:#121914}.library-launcher .ui-icon{width:14px;height:14px;color:#9bcbb1}@media(max-width:720px){.library-launcher{right:12px;bottom:12px;max-width:calc(100vw - 24px)}.library-launcher a{padding:0 11px}.library-launcher a span{display:none}}
      `}</style>
    </div>
  );
}
