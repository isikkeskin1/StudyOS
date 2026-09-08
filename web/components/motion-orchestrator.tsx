"use client";

import { usePathname } from "next/navigation";
import { useEffect, useRef, useState } from "react";

import { BrandMark } from "@/components/ui-icon";

const REVEAL_SELECTOR = [
  ".today-header",
  ".today-focus",
  ".course-ledger .ledger-row",
  ".workspace-section",
  ".workspace-metrics article",
  ".focus-room-stage-copy > *",
  ".focus-room-clock",
  ".focus-room-tools",
  ".focus-room-panel",
  ".institution-library-main > *",
  ".admin-library-main > *",
  ".setup-card > *:not(.setup-header):not(.setup-progress)",
  ".auth-card > *",
].join(",");

function isRouteAnchor(anchor: HTMLAnchorElement, event: MouseEvent) {
  if (event.defaultPrevented || event.button !== 0 || event.metaKey || event.ctrlKey || event.shiftKey || event.altKey) return false;
  if (anchor.target && anchor.target !== "_self") return false;
  if (anchor.hasAttribute("download")) return false;
  const href = anchor.getAttribute("href");
  if (!href || href.startsWith("#") || href.startsWith("mailto:") || href.startsWith("tel:")) return false;

  try {
    const target = new URL(anchor.href, window.location.href);
    if (target.origin !== window.location.origin) return false;
    const current = new URL(window.location.href);
    return target.pathname !== current.pathname || target.search !== current.search;
  } catch {
    return false;
  }
}

export function MotionOrchestrator() {
  const pathname = usePathname();
  const [routeBusy, setRouteBusy] = useState(false);
  const fallbackTimer = useRef<number | null>(null);

  useEffect(() => {
    document.body.dataset.motionReady = "true";

    const observer = new IntersectionObserver(
      (entries) => {
        for (const entry of entries) {
          if (!entry.isIntersecting) continue;
          const element = entry.target as HTMLElement;
          element.dataset.motionIn = "true";
          observer.unobserve(element);
        }
      },
      { rootMargin: "0px 0px -7% 0px", threshold: 0.04 },
    );

    let revealIndex = 0;
    const register = (root: ParentNode) => {
      const nodes = root instanceof Element && root.matches(REVEAL_SELECTOR)
        ? [root, ...root.querySelectorAll<HTMLElement>(REVEAL_SELECTOR)]
        : [...root.querySelectorAll<HTMLElement>(REVEAL_SELECTOR)];

      for (const node of nodes) {
        if (!(node instanceof HTMLElement) || node.dataset.motionObserved === "true") continue;
        node.dataset.motionObserved = "true";
        node.style.setProperty("--motion-delay", `${Math.min(revealIndex % 7, 6) * 42}ms`);
        revealIndex += 1;
        observer.observe(node);
      }
    };

    register(document);
    const mutations = new MutationObserver((records) => {
      for (const record of records) {
        for (const added of record.addedNodes) {
          if (added instanceof Element) register(added);
        }
      }
    });
    mutations.observe(document.body, { childList: true, subtree: true });

    let frame = 0;
    const onPointerMove = (event: PointerEvent) => {
      if (event.pointerType === "touch") return;
      if (frame) cancelAnimationFrame(frame);
      frame = requestAnimationFrame(() => {
        const x = Math.max(0, Math.min(1, event.clientX / Math.max(window.innerWidth, 1)));
        const y = Math.max(0, Math.min(1, event.clientY / Math.max(window.innerHeight, 1)));
        document.documentElement.style.setProperty("--motion-x", `${(x * 100).toFixed(2)}%`);
        document.documentElement.style.setProperty("--motion-y", `${(y * 100).toFixed(2)}%`);
      });
    };

    window.addEventListener("pointermove", onPointerMove, { passive: true });
    return () => {
      observer.disconnect();
      mutations.disconnect();
      window.removeEventListener("pointermove", onPointerMove);
      if (frame) cancelAnimationFrame(frame);
    };
  }, []);

  useEffect(() => {
    const onClick = (event: MouseEvent) => {
      const target = event.target instanceof Element ? event.target.closest("a") : null;
      if (!(target instanceof HTMLAnchorElement) || !isRouteAnchor(target, event)) return;
      setRouteBusy(true);
      document.documentElement.dataset.routeMoving = "true";
      if (fallbackTimer.current) window.clearTimeout(fallbackTimer.current);
      fallbackTimer.current = window.setTimeout(() => {
        setRouteBusy(false);
        delete document.documentElement.dataset.routeMoving;
      }, 1800);
    };

    document.addEventListener("click", onClick, true);
    return () => document.removeEventListener("click", onClick, true);
  }, []);

  useEffect(() => {
    const finish = window.setTimeout(() => {
      setRouteBusy(false);
      delete document.documentElement.dataset.routeMoving;
      if (fallbackTimer.current) {
        window.clearTimeout(fallbackTimer.current);
        fallbackTimer.current = null;
      }
    }, 90);
    return () => window.clearTimeout(finish);
  }, [pathname]);

  return (
    <div className={`study-route-motion${routeBusy ? " is-active" : ""}`} aria-hidden={!routeBusy}>
      <div className="study-route-progress"><span /></div>
      <div className="study-route-toast" role="status" aria-live="polite">
        <BrandMark />
        <span><strong>StudyOS</strong><small>Opening view</small></span>
        <i />
      </div>
    </div>
  );
}
