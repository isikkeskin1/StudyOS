"use client";

import Link from "next/link";
import { useEffect, useRef, useState } from "react";

type SearchKind =
  | "course"
  | "topic"
  | "source"
  | "practice"
  | "mistake"
  | "cheat_sheet"
  | "forecast";

type SearchResult = {
  kind: SearchKind;
  id: string;
  course_id: string;
  course_name: string;
  title: string;
  subtitle: string | null;
  excerpt: string | null;
  score: number;
  href: string;
};

type SearchResponse = {
  query: string;
  result_count: number;
  results: SearchResult[];
};

const LABELS: Record<SearchKind, string> = {
  course: "Course",
  topic: "Topic",
  source: "Source",
  practice: "Practice",
  mistake: "Mistake",
  cheat_sheet: "Cheat sheet",
  forecast: "Forecast",
};

export function GlobalSearch() {
  const [open, setOpen] = useState(false);
  const [query, setQuery] = useState("");
  const [results, setResults] = useState<SearchResult[]>([]);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const inputRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    if (!open) return;
    window.setTimeout(() => inputRef.current?.focus(), 0);
  }, [open]);

  useEffect(() => {
    if (!open || query.trim().length < 2) {
      setResults([]);
      setBusy(false);
      return;
    }

    const controller = new AbortController();
    const timer = window.setTimeout(() => {
      setBusy(true);
      setError(null);
      void fetch(
        `/api/v1/search?q=${encodeURIComponent(query.trim())}&limit=30`,
        { cache: "no-store", signal: controller.signal },
      )
        .then(async (response) => {
          if (!response.ok) throw new Error("Search failed.");
          return (await response.json()) as SearchResponse;
        })
        .then((body) => setResults(body.results))
        .catch((caught) => {
          if (caught instanceof DOMException && caught.name === "AbortError") return;
          setError(caught instanceof Error ? caught.message : "Search failed.");
        })
        .finally(() => setBusy(false));
    }, 220);

    return () => {
      window.clearTimeout(timer);
      controller.abort();
    };
  }, [open, query]);

  useEffect(() => {
    const onKey = (event: KeyboardEvent) => {
      if ((event.metaKey || event.ctrlKey) && event.key.toLowerCase() === "k") {
        event.preventDefault();
        setOpen(true);
        return;
      }
      if (open && event.key === "Escape") setOpen(false);
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [open]);

  return (
    <>
      <button className="ghost-button global-search-trigger" onClick={() => setOpen(true)}>
        Search
        <span>⌘K</span>
      </button>

      {open && (
        <div className="global-search-backdrop" onMouseDown={() => setOpen(false)}>
          <section
            className="global-search-panel"
            onMouseDown={(event) => event.stopPropagation()}
            aria-label="Search StudyOS"
          >
            <div className="global-search-input-row">
              <span>⌕</span>
              <input
                ref={inputRef}
                value={query}
                onChange={(event) => setQuery(event.target.value)}
                placeholder="Search courses, topics, sources, mistakes, practice…"
              />
              <button onClick={() => setOpen(false)} aria-label="Close search">Esc</button>
            </div>

            <div className="global-search-body">
              {query.trim().length < 2 && (
                <div className="global-search-empty">
                  <strong>Search your entire StudyOS workspace.</strong>
                  <span>Type at least two characters.</span>
                </div>
              )}

              {busy && <div className="global-search-empty"><span>Searching…</span></div>}
              {error && <div className="global-search-empty error"><span>{error}</span></div>}

              {!busy && !error && query.trim().length >= 2 && results.length === 0 && (
                <div className="global-search-empty">
                  <strong>No matches.</strong>
                  <span>Try a topic, filename, mistake type, or phrase from your notes.</span>
                </div>
              )}

              {!busy && results.length > 0 && (
                <div className="global-search-results">
                  {results.map((result) => (
                    <Link
                      key={`${result.kind}:${result.id}`}
                      href={result.href}
                      onClick={() => setOpen(false)}
                    >
                      <div className="global-search-result-head">
                        <span className="global-search-kind">{LABELS[result.kind]}</span>
                        <small>{result.course_name}</small>
                      </div>
                      <strong>{result.title}</strong>
                      {result.subtitle && <span className="global-search-subtitle">{result.subtitle}</span>}
                      {result.excerpt && <p>{result.excerpt}</p>}
                    </Link>
                  ))}
                </div>
              )}
            </div>
          </section>
        </div>
      )}
    </>
  );
}
