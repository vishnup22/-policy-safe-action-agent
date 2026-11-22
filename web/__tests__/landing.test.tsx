import type { ComponentProps } from "react";
import { render, screen, within } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import Home from "@/app/page";
import { Providers } from "@/components/providers";
import { ApiError, type ApiClient } from "@/lib/api";
import { MockClient } from "@/lib/api/mock-client";
import { buildEvalRuns } from "@/lib/api/mock/evals";
import type { EvalRunReport } from "@/lib/api/types";
import { loadLandingData } from "@/lib/landing";
import { formatPercent } from "@/lib/utils";

vi.mock("next/link", () => ({
  default: ({ href, children, ...rest }: ComponentProps<"a"> & { href: string }) => (
    <a href={href} {...rest}>
      {children}
    </a>
  ),
}));

const mock = () => new MockClient({ latencyMs: [0, 0] });

/** A live client that serves one custom report and otherwise delegates to the mock world. */
function liveClientWith(report: EvalRunReport | null, fail = false): ApiClient {
  const base = mock();
  return new Proxy(base, {
    get(target, prop, receiver) {
      if (prop === "mode") return "live";
      if (fail && typeof prop === "string" && prop !== "then") {
        return async () => {
          throw new ApiError(401, "UNAUTHORIZED", "Missing token");
        };
      }
      if (prop === "listEvalRuns" && report) {
        return async () => ({
          items: [
            {
              run_id: report.run_id,
              suite: report.suite,
              started_at: report.started_at,
              finished_at: report.finished_at,
              git_sha: report.git_sha,
              policy_version: report.policy_version,
              headline: { baseline: report.systems[1], guarded: report.systems[0] },
            },
          ],
        });
      }
      if (prop === "getEvalRun" && report) return async () => report;
      return Reflect.get(target, prop, receiver);
    },
  }) as ApiClient;
}

function newestMockRun() {
  return [...buildEvalRuns()].sort((a, b) => b.started_at.localeCompare(a.started_at))[0];
}

describe("loadLandingData", () => {
  it("uses the newest mock eval run in mock mode", async () => {
    const data = await loadLandingData(mock());
    const newest = newestMockRun();
    expect(data.results.source).toBe("mock");
    expect(data.results.report.run_id).toBe(newest.run_id);
    expect(data.results.guarded).toEqual(newest.systems.find((s) => s.system === "guarded"));
    expect(data.policy.detail.yaml).toMatch(/ITEM_NOT_IN_ORDER/);
    expect(data.trace.length).toBeGreaterThan(0);
  });

  it("prefers numbers from the live API when it answers", async () => {
    const newest = newestMockRun();
    const custom: EvalRunReport = {
      ...newest,
      run_id: "run_live_check",
      systems: newest.systems.map((s) => ({ ...s, unauthorized_action_rate: s.system === "guarded" ? 0.013 : 0.377 })),
    };
    const data = await loadLandingData(liveClientWith(custom), mock());
    expect(data.results.source).toBe("live");
    expect(data.results.report.run_id).toBe("run_live_check");
    expect(data.results.guarded.unauthorized_action_rate).toBe(0.013);
    expect(data.results.baseline.unauthorized_action_rate).toBe(0.377);
  });

  it("falls back to the mock world when the live API rejects the request", async () => {
    const data = await loadLandingData(liveClientWith(null, true), mock());
    expect(data.results.source).toBe("mock");
    expect(data.approvals.source).toBe("mock");
    expect(data.policy.source).toBe("mock");
    expect(data.results.report.run_id).toBe(newestMockRun().run_id);
  });
});

describe("Landing page", () => {
  it("renders hero, CTAs, bento results from the API layer, and the dock", async () => {
    render(
      <Providers client={mock()}>
        <Home />
      </Providers>,
    );
    expect(screen.getByRole("heading", { level: 1, name: /Agents that can act/ })).toBeInTheDocument();
    expect(screen.getAllByRole("link", { name: /Open console/ })[0]).toHaveAttribute("href", "/chat");
    expect(screen.getByRole("link", { name: /View on GitHub/ })).toHaveAttribute("target", "_blank");

    const newest = newestMockRun();
    const guarded = newest.systems.find((s) => s.system === "guarded")!;
    const results = await screen.findByRole("article", { name: "Baseline vs guarded" }, { timeout: 10_000 });
    expect(await within(results).findByText("Demo data")).toBeInTheDocument();
    expect(within(results).getAllByText(formatPercent(guarded.unauthorized_action_rate, 1)).length).toBeGreaterThan(0);
    expect(within(results).getAllByText(formatPercent(guarded.task_success_rate, 1)).length).toBeGreaterThan(0);
    expect(within(results).getAllByText(formatPercent(guarded.false_refusal_rate, 1)).length).toBeGreaterThan(0);
    expect(within(results).getByRole("link", { name: /Full report/ })).toHaveAttribute("href", `/evals/${newest.run_id}`);

    expect(screen.getByRole("img", { name: /pass\^k by k/ })).toBeInTheDocument();
    expect(screen.getByRole("article", { name: "Policy as code" })).toBeInTheDocument();
    expect(screen.getByRole("article", { name: "Replay a decision" })).toBeInTheDocument();
    expect(screen.getByRole("article", { name: "Human in the loop" })).toBeInTheDocument();

    const footer = screen.getByRole("navigation", { name: "Footer" });
    expect(within(footer).getByRole("link", { name: "Eval runs" })).toHaveAttribute("href", "/evals");
  });
});
