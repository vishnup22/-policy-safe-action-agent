"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { ArrowRight, ShieldCheck } from "lucide-react";
import { buttonVariants } from "@/components/ui/button";
import { GlassPanel, PillNav } from "@/components/ui/glass";
import { cn } from "@/lib/utils";

const SECTIONS = [
  { href: "#top", label: "Overview" },
  { href: "#architecture", label: "How it works" },
  { href: "#results", label: "Results" },
] as const;

/** The last section whose top has crossed 35% of the viewport. */
function useActiveSection(): string {
  const [active, setActive] = useState<string>(SECTIONS[0].href);
  useEffect(() => {
    let frame = 0;
    function update() {
      frame = 0;
      const line = window.innerHeight * 0.35;
      let current: string = SECTIONS[0].href;
      for (const { href } of SECTIONS) {
        const el = document.getElementById(href.slice(1));
        if (el && el.getBoundingClientRect().top <= line) current = href;
      }
      setActive(current);
    }
    function onScroll() {
      if (!frame) frame = requestAnimationFrame(update);
    }
    update();
    window.addEventListener("scroll", onScroll, { passive: true });
    window.addEventListener("resize", onScroll);
    return () => {
      cancelAnimationFrame(frame);
      window.removeEventListener("scroll", onScroll);
      window.removeEventListener("resize", onScroll);
    };
  }, []);
  return active;
}

export function LandingNav() {
  const active = useActiveSection();
  return (
    <header className="pointer-events-none fixed inset-x-0 top-3 z-40 flex justify-center px-3 sm:top-6">
      <GlassPanel radius="full" className="pointer-events-auto flex items-center gap-1 py-1.5 pr-1.5 pl-4 sm:gap-2">
        <Link
          href="#top"
          className="flex shrink-0 items-center gap-2 rounded-full pr-1 text-sm font-semibold tracking-tight focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-ring"
        >
          <ShieldCheck aria-hidden className="size-5 text-emerald-600 dark:text-emerald-300" />
          Larkspur
        </Link>
        <PillNav
          items={SECTIONS}
          activeHref={active}
          layoutId="landing-nav-pill"
          label="Sections"
          current="location"
          className="hidden md:block"
        />
        <Link href="/chat" className={cn(buttonVariants({ size: "sm" }), "ml-2 h-8 px-3.5")}>
          Open console <ArrowRight aria-hidden />
        </Link>
      </GlassPanel>
    </header>
  );
}
