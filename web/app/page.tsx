import type { Metadata } from "next";
import { Bento } from "@/components/landing/bento";
import { Hero } from "@/components/landing/hero";
import { LandingNav } from "@/components/landing/landing-nav";
import { SiteFooter } from "@/components/landing/site-footer";
import { BlurFade } from "@/components/ui/glass";

export const metadata: Metadata = {
  title: { absolute: "Policy-Safe Action Agent — agents that can act and can't break policy" },
};

export default function Home() {
  return (
    <>
      <LandingNav />
      <main id="main" className="flex-1">
        <Hero />
        <section id="architecture" aria-labelledby="architecture-heading" className="mx-auto max-w-6xl scroll-mt-28 px-4 pb-24 sm:px-6">
          <BlurFade className="mx-auto mb-12 max-w-2xl text-center">
            <p className="text-sm font-medium text-muted-foreground">How it works</p>
            <h2 id="architecture-heading" className="mt-2 text-3xl font-semibold tracking-display text-balance sm:text-5xl">
              Propose. Decide. Execute.
            </h2>
            <p className="mt-4 text-base text-pretty text-muted-foreground">
              Business rules live outside the model. The numbers below come from the latest eval run: the same scenarios
              played against a prompt-only baseline and the guarded agent.
            </p>
          </BlurFade>
          <Bento />
        </section>
      </main>
      <SiteFooter />
    </>
  );
}
