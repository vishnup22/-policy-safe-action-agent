/**
 * Runs with `prefers-reduced-motion: reduce`. Framer Motion caches the preference on
 * first read, so this lives in its own file (own module registry) and stubs
 * matchMedia before any import executes.
 */
import { readFileSync } from "node:fs";
import path from "node:path";
import { render } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

vi.hoisted(() => {
  window.matchMedia = (query: string) =>
    ({
      matches: query.includes("reduce"),
      media: query,
      onchange: null,
      addListener: () => {},
      removeListener: () => {},
      addEventListener: () => {},
      removeEventListener: () => {},
      dispatchEvent: () => false,
    }) as MediaQueryList;
});

vi.mock("next/navigation", () => ({ usePathname: () => "/evals" }));

const { PageTransition } = await import("@/components/page-transition");

describe("prefers-reduced-motion: reduce", () => {
  it("page transitions fade without sliding", () => {
    const { container } = render(<PageTransition>page</PageTransition>);
    const el = container.firstElementChild as HTMLElement;
    expect(el.style.opacity).toBe("0");
    expect(el.style.transform).toBe("");
  });

  it("CSS stops the aurora drift and the badge shimmer", () => {
    const css = readFileSync(path.resolve(import.meta.dirname, "../app/globals.css"), "utf8");
    const block = css.slice(css.indexOf("@media (prefers-reduced-motion: reduce)"));
    expect(block).toMatch(/\.shimmer-sweep\s*\{[^}]*animation:\s*none/);
    expect(block).toMatch(/\.aurora-blob\s*\{[^}]*animation:\s*none/);
  });
});
