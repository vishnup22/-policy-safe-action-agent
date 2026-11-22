import Link from "next/link";
import { ArrowRight, GitBranch } from "lucide-react";
import { buttonVariants } from "@/components/ui/button";
import { REPO_URL } from "@/lib/site";
import { cn } from "@/lib/utils";

/** Server-rendered with no entrance animation so the headline paints immediately (LCP). */
export function Hero() {
  return (
    <section id="top" aria-labelledby="hero-heading" className="mx-auto flex max-w-5xl flex-col items-center px-4 pt-36 pb-20 text-center sm:pt-48 sm:pb-28">
      <span className="relative isolate inline-flex items-center gap-2 overflow-hidden rounded-full border border-glass-edge bg-glass-inset px-3.5 py-1 text-xs font-medium text-muted-foreground shadow-[inset_0_1px_0_0_var(--glass-highlight)]">
        <span aria-hidden className="shimmer-sweep -z-10" />
        <span aria-hidden className="size-1.5 rounded-full bg-emerald-500 shadow-[0_0_8px_2px_rgb(16_185_129/0.45)] dark:bg-emerald-300" />
        Policy-safe agents
      </span>
      <h1
        id="hero-heading"
        className="mt-7 text-[2.6rem] leading-[1.04] font-semibold tracking-display text-balance sm:text-6xl md:text-7xl"
      >
        Agents that can act —{" "}
        <span className="text-gradient">and can&apos;t break policy.</span>
      </h1>
      <p className="mt-6 max-w-2xl text-base leading-relaxed text-pretty text-muted-foreground sm:text-lg">
        The model only <strong className="font-medium text-foreground">proposes</strong>. A deterministic, versioned
        policy engine <strong className="font-medium text-foreground">decides</strong>. An idempotent executor{" "}
        <strong className="font-medium text-foreground">acts</strong> — and every step lands in an append-only log you
        can replay.
      </p>
      <div className="mt-10 flex flex-col items-stretch gap-3 sm:flex-row sm:items-center">
        <Link href="/chat" className={buttonVariants({ size: "xl" })}>
          Open console <ArrowRight aria-hidden />
        </Link>
        <a href={REPO_URL} target="_blank" rel="noreferrer" className={cn(buttonVariants({ variant: "glass", size: "xl" }))}>
          <GitBranch aria-hidden /> View on GitHub
          <span className="sr-only"> (opens in a new tab)</span>
        </a>
      </div>
      <p className="mt-6 text-xs text-muted-foreground">
        Larkspur Goods is a fictional retailer. Every customer and order is synthetic.
      </p>
    </section>
  );
}
