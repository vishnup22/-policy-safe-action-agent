"use client";

import dynamic from "next/dynamic";
import { whenIdle } from "@/lib/motion";

function BentoPlaceholder() {
  return <div aria-busy="true" aria-label="Loading results" className="min-h-[2400px] md:min-h-[1500px] lg:min-h-[980px]" />;
}

/** The bento sits below the hero; its code, the API client and the fixtures load once the hero has painted. */
export const DeferredBento = dynamic(
  () => whenIdle().then(() => import("./bento").then((mod) => mod.Bento)),
  { ssr: false, loading: BentoPlaceholder },
);
