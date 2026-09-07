import type { CSSProperties } from "react";

const paths = {
  overview: "M3 3h7v7H3z M14 3h7v7h-7z M3 14h7v7H3z M14 14h7v7h-7z",
  activity: "M3 17V9 M9 17V3 M15 17v-6 M21 17V6 M3 21h18",
  courses: "M4 4h6a3 3 0 0 1 3 3v14a4 4 0 0 0-4-3H4z M13 7a3 3 0 0 1 3-3h5v14h-4a4 4 0 0 0-4 3",
  risks: "m12 3 10 18H2z M12 9v5 M12 17v.1",
  clock: "M12 8v5l3 2 M22 12a10 10 0 1 1-20 0 10 10 0 0 1 20 0",
  target: "M22 12a10 10 0 1 1-20 0 10 10 0 0 1 20 0 M18 12a6 6 0 1 1-12 0 6 6 0 0 1 12 0 M14 12a2 2 0 1 1-4 0 2 2 0 0 1 4 0",
  check: "m5 12 4 4L19 6",
  arrow: "M4 12h16 m-6-6 6 6-6 6",
  plus: "M12 5v14 M5 12h14",
  play: "m8 4 12 8-12 8z",
  pause: "M8 5v14 M16 5v14",
  next: "m6 5 8 7-8 7z M18 5v14",
  previous: "m18 5-8 7 8 7z M6 5v14",
  music: "M9 18V5l10-2v13 M9 8l10-2 M6 21a3 3 0 1 0 0-6 3 3 0 0 0 0 6 M16 19a3 3 0 1 0 0-6 3 3 0 0 0 0 6",
  refresh: "M20 8a8 8 0 0 0-14-3L3 8 M3 3v5h5 M4 16a8 8 0 0 0 14 3l3-3 M16 16h5v5",
  settings: "M12 3v3 M12 18v3 M3 12h3 M18 12h3 M5.6 5.6l2.1 2.1 M16.3 16.3l2.1 2.1 M5.6 18.4l2.1-2.1 M16.3 7.7l2.1-2.1 M17 12a5 5 0 1 1-10 0 5 5 0 0 1 10 0",
  logout: "M9 4H4v16h5 M9 12h12 m-5-5 5 5-5 5",
  search: "M16 10a6 6 0 1 1-12 0 6 6 0 0 1 12 0 m-2 4 6 6",
  sources: "M6 3h9l4 4v14H6z M14 3v5h5 M9 12h7 M9 16h5",
  tutor: "M21 11a8 8 0 0 1-8 8H8l-5 3V7a4 4 0 0 1 4-4h6a8 8 0 0 1 8 8 M7 9h10 M7 13h6",
  layers: "m12 3 10 5-10 5L2 8z M2 12l10 5 10-5 M2 16l10 5 10-5",
  calendar: "M4 5h16v16H4z M8 3v4 M16 3v4 M4 10h16 M8 14h2 M14 14h2 M8 17h2",
  shield: "m12 3 8 3v6c0 5-8 9-8 9s-8-4-8-9V6z m-4 9 3 3 5-6",
} as const;

export type IconName = keyof typeof paths;

export function UiIcon({ name, className = "", style }: { name: IconName; className?: string; style?: CSSProperties }) {
  return <svg className={`ui-icon ${className}`} style={style} width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.65" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true"><path d={paths[name]} /></svg>;
}

export function BrandMark() {
  return <span className="brand-mark" aria-hidden="true"><svg width="24" height="24" viewBox="0 0 24 24" fill="none"><path d="m4 7 8-4 8 4-8 4-8-4Zm0 5 8 4 8-4M4 17l8 4 8-4" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" /></svg></span>;
}
