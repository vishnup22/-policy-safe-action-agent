"use client";

import { useEffect, useRef, useState } from "react";
import dynamic from "next/dynamic";
import { whenIdle } from "@/lib/motion";

/** Anchors inside the bento. The placeholder carries `results` so nav links and deep links land on it. */
const BENTO_ANCHORS = new Set(["results", "replay"]);

const INTERACTION_EVENTS = ["scroll", "wheel", "pointerdown", "touchstart", "keydown"] as const;

function BentoPlaceholder() {
  return (
    <div id="results" aria-busy="true" className="min-h-[2400px] scroll-mt-28 md:min-h-[1500px] lg:min-h-[980px]">
      <span className="sr-only">Loading results…</span>
    </div>
  );
}

const Bento = dynamic(() => whenIdle().then(() => import("./bento").then((mod) => mod.Bento)), {
  ssr: false,
  loading: BentoPlaceholder,
});

function linksIntoBento(): boolean {
  return BENTO_ANCHORS.has(decodeURIComponent(window.location.hash.slice(1)));
}

/**
 * The bento sits below the hero. Its code, the API client, the Zod schemas and the fixtures load
 * once the visitor heads towards it — first scroll or input (about a screen before the grid is
 * reached), the placeholder entering the viewport on tall screens, or a link to one of its
 * anchors — so none of that work competes with the first screen.
 */
export function DeferredBento() {
  const placeholder = useRef<HTMLDivElement>(null);
  const [requested, setRequested] = useState(false);

  useEffect(() => {
    if (requested) return;
    const request = () => setRequested(true);
    const onHashChange = () => linksIntoBento() && request();
    if (linksIntoBento()) {
      request();
      return;
    }

    const observer = new IntersectionObserver((entries) => entries.some((e) => e.isIntersecting) && request());
    if (placeholder.current) observer.observe(placeholder.current);
    for (const type of INTERACTION_EVENTS) window.addEventListener(type, request, { once: true, passive: true });
    window.addEventListener("hashchange", onHashChange);
    return () => {
      observer.disconnect();
      for (const type of INTERACTION_EVENTS) window.removeEventListener(type, request);
      window.removeEventListener("hashchange", onHashChange);
    };
  }, [requested]);

  if (requested) return <Bento />;
  return (
    <div ref={placeholder}>
      <BentoPlaceholder />
    </div>
  );
}
