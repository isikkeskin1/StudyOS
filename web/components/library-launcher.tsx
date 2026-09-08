"use client";

import { UiIcon } from "@/components/ui-icon";

export function LibraryLauncher({ isAdmin }: { isAdmin: boolean }) {
  return (
    <div className="library-launcher" aria-label="Institutional library shortcuts">
      <a href="/library"><UiIcon name="sources" /><span>Library</span></a>
      {isAdmin && <a href="/admin"><UiIcon name="shield" /><span>Admin</span></a>}
      <style jsx global>{`
        .library-launcher{position:fixed;left:18px;bottom:18px;z-index:80;display:flex;gap:6px;align-items:center}
        .library-launcher a{min-height:36px;display:flex;align-items:center;gap:7px;padding:0 11px;border:1px solid var(--ui-line);border-radius:999px;background:color-mix(in srgb,var(--ui-surface) 86%,transparent);backdrop-filter:blur(20px) saturate(150%);box-shadow:var(--ui-shadow-soft);color:var(--ui-muted);text-decoration:none;font-size:10px;font-weight:600}
        .library-launcher a:hover{border-color:var(--ui-line-strong);color:var(--ui-text);background:var(--ui-surface-2)}
        .library-launcher .ui-icon{width:14px;height:14px;color:var(--ui-accent)}
        @media(max-width:760px){.library-launcher{left:12px;bottom:calc(82px + env(safe-area-inset-bottom))}.library-launcher a{width:38px;min-height:38px;padding:0;justify-content:center}.library-launcher a span{display:none}}
      `}</style>
    </div>
  );
}
