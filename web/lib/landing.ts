import type { ApiClient } from "@/lib/api/client";
import { LazyClient } from "@/lib/api/lazy-client";
import type { Approval, EvalRunReport, Event, PolicyDetail, SystemMetrics } from "@/lib/api/types";

function demoClient(): ApiClient {
  return new LazyClient("mock", async () => {
    const { MockClient } = await import("@/lib/api/mock-client");
    return new MockClient({ latencyMs: [0, 0] });
  });
}

export type DataSource = "live" | "mock";

export interface LandingResults {
  source: DataSource;
  report: EvalRunReport;
  baseline: SystemMetrics;
  guarded: SystemMetrics;
}

export interface LandingData {
  results: LandingResults;
  approvals: { source: DataSource; items: Approval[] };
  policy: { source: DataSource; detail: PolicyDetail };
  /** Demo replay trace; always from the mock world so the preview is stable. */
  trace: Event[];
}

/** The prompt-injection story: shows untrusted notes being ignored by the policy engine. */
export const PREVIEW_CONVERSATION_ID = "conv_h7nj3c5t";

async function latestReport(client: ApiClient): Promise<LandingResults | null> {
  const { items } = await client.listEvalRuns({ limit: 20 });
  const latest = [...items].sort((a, b) => b.started_at.localeCompare(a.started_at))[0];
  if (!latest) return null;
  const report = await client.getEvalRun(latest.run_id);
  const baseline = report.systems.find((s) => s.system === "baseline");
  const guarded = report.systems.find((s) => s.system === "guarded");
  if (!baseline || !guarded) return null;
  return { source: client.mode, report, baseline, guarded };
}

async function withFallback<T>(primary: ApiClient, fallback: ApiClient, load: (c: ApiClient) => Promise<T | null>) {
  if (primary.mode === "live") {
    try {
      const value = await load(primary);
      if (value !== null) return value;
    } catch {
      // Unreachable API, 401 for an anonymous visitor, or a contract mismatch: use the demo world.
    }
  }
  const value = await load(fallback);
  if (value === null) throw new Error("Mock fallback returned no data");
  return value;
}

/**
 * Everything the landing page shows. Numbers come from the newest eval run on the
 * API (`GET /api/evals/runs` → `GET /api/evals/runs/{id}`); if that is unavailable,
 * from the mock world. Nothing on the page is hardcoded.
 */
export async function loadLandingData(
  primary: ApiClient,
  fallback: ApiClient = primary.mode === "mock" ? primary : demoClient(),
): Promise<LandingData> {
  const mock = primary.mode === "mock" ? primary : fallback;
  const [results, approvals, policy, events] = await Promise.all([
    withFallback(primary, fallback, latestReport),
    withFallback(primary, fallback, async (c) => ({ source: c.mode, items: (await c.listApprovals()).items })),
    withFallback(primary, fallback, async (c) => {
      const { items } = await c.listPolicies();
      const first = items[0];
      return first ? { source: c.mode, detail: await c.getPolicy(first.policy_set) } : null;
    }),
    mock.getEvents(PREVIEW_CONVERSATION_ID),
  ]);
  return { results, approvals, policy, trace: events.events };
}
