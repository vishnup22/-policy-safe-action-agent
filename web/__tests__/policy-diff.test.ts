import { describe, expect, it } from "vitest";
import { diffMockPolicy, MOCK_POLICY_SUMMARY, POLICY_VERSION_V2 } from "@/lib/api/mock/policies";
import type { EvalRunSummary } from "@/lib/api/types";
import { fieldChanges, isMissing, policyDiffHref, resolveVersions, ruleLines, runsForVersions } from "@/lib/policy-diff";

const refundWindow = diffMockPolicy("larkspur-returns", MOCK_POLICY_SUMMARY.version, POLICY_VERSION_V2)!.changed[0];

describe("fieldChanges", () => {
  it("lists exactly the leaf fields that differ", () => {
    const changes = fieldChanges(refundWindow.before, refundWindow.after);
    expect(changes.map((c) => c.path)).toEqual(["description", "when.value", "else.message"]);
    expect(changes[1]).toEqual({ path: "when.value", before: 30, after: 14 });
  });

  it("reports fields that only exist on one side", () => {
    const changes = fieldChanges({ id: "R", then: { decision: "ALLOW" } }, { id: "R", only_if: { fact: "x", op: "eq", value: true } });
    expect(changes.map((c) => c.path)).toEqual(["only_if.fact", "only_if.op", "only_if.value", "then.decision"]);
    expect(isMissing(changes[0].before)).toBe(true);
    expect(isMissing(changes[3].after)).toBe(true);
  });

  it("treats a scalar list as one field", () => {
    const changes = fieldChanges({ applies_to: ["a", "b"] }, { applies_to: ["a", "c"] });
    expect(changes).toEqual([{ path: "applies_to", before: ["a", "b"], after: ["a", "c"] }]);
  });
});

describe("ruleLines", () => {
  it("renders block YAML and tags only the changed lines", () => {
    const after = ruleLines(refundWindow.after, "after", refundWindow.before);
    const changed = after.filter((l) => l.change !== "same").map((l) => l.path);
    expect(changed).toEqual(["description", "when.value", "else.message"]);
    expect(after.find((l) => l.path === "when.value")).toMatchObject({ depth: 1, key: "value", value: "14" });
    expect(after.find((l) => l.path === "applies_to")?.value).toBe("[issue_refund]");
    const firstCondition = after.find((l) => l.path === "only_if.all[0].fact");
    expect(firstCondition).toMatchObject({ bullet: true, depth: 2, value: "order.exists" });
  });

  it("marks every line of an added rule as added", () => {
    const lines = ruleLines({ id: "NEW", when: { fact: "x", op: "eq", value: 1 } }, "after");
    expect(new Set(lines.map((l) => l.change))).toEqual(new Set(["added"]));
  });
});

describe("resolveVersions", () => {
  const versions = ["2026.11.21-1", "2026.11.21-2", "2026.11.21-10"];

  it("defaults to the newest version and the one before it", () => {
    expect(resolveVersions(versions, null, null)).toEqual({ from: "2026.11.21-2", to: "2026.11.21-10" });
  });

  it("keeps explicit choices and fills only what is missing", () => {
    expect(resolveVersions(versions, "2026.11.21-1", null)).toEqual({ from: "2026.11.21-1", to: "2026.11.21-10" });
    expect(resolveVersions(versions, null, "2026.11.21-2")).toEqual({ from: "2026.11.21-1", to: "2026.11.21-2" });
  });

  it("compares a single version with itself, and gives up with none", () => {
    expect(resolveVersions(["v1"], null, null)).toEqual({ from: "v1", to: "v1" });
    expect(resolveVersions([], null, null)).toBeNull();
  });
});

describe("runsForVersions", () => {
  const run = (run_id: string, suite: string, policy_version: string, started_at: string): EvalRunSummary => ({
    run_id,
    suite,
    policy_version,
    started_at,
    finished_at: started_at,
    git_sha: "abc1234",
    headline: {
      baseline: { task_success_rate: 0.5, unauthorized_action_rate: 0.1 },
      guarded: { task_success_rate: 0.8, unauthorized_action_rate: 0 },
    },
  });

  it("prefers the newest pair from a suite run on both versions over a newer unpaired run", () => {
    const runs = [
      run("full-v1", "full", "v1", "2026-11-21T12:00:00Z"),
      run("reg-v1", "regression", "v1", "2026-11-20T18:00:00Z"),
      run("reg-v2", "regression", "v2", "2026-11-21T09:30:00Z"),
    ];
    const pair = runsForVersions(runs, "v1", "v2");
    expect(pair).toMatchObject({ sameSuite: true, from: { run_id: "reg-v1" }, to: { run_id: "reg-v2" } });
  });

  it("falls back to the newest run per version and says the suites differ", () => {
    const runs = [run("full-v1", "full", "v1", "2026-11-21T12:00:00Z"), run("reg-v2", "regression", "v2", "2026-11-21T09:30:00Z")];
    expect(runsForVersions(runs, "v1", "v2")).toMatchObject({ sameSuite: false, from: { run_id: "full-v1" }, to: { run_id: "reg-v2" } });
    expect(runsForVersions(runs, "v1", "v3")).toMatchObject({ to: null });
  });
});

describe("policyDiffHref", () => {
  it("encodes the set and only includes the params given", () => {
    expect(policyDiffHref("larkspur-returns")).toBe("/policies/larkspur-returns/diff");
    expect(policyDiffHref("larkspur-returns", { from: "2026.11.21-1", rule: "REFUND_WINDOW" })).toBe(
      "/policies/larkspur-returns/diff?from=2026.11.21-1&rule=REFUND_WINDOW",
    );
  });
});
