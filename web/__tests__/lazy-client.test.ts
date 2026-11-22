import { describe, expect, it, vi } from "vitest";
import { createApiClient } from "@/lib/api/config";
import { LazyClient } from "@/lib/api/lazy-client";
import { MockClient } from "@/lib/api/mock-client";

describe("LazyClient", () => {
  it("loads the implementation once, on first use, and forwards calls", async () => {
    const real = new MockClient({ latencyMs: [0, 0] });
    const load = vi.fn(async () => real);
    const client = new LazyClient("mock", load);

    expect(load).not.toHaveBeenCalled();
    const [runs, policies] = await Promise.all([client.listEvalRuns(), client.listPolicies()]);
    expect(load).toHaveBeenCalledTimes(1);
    expect(runs.items.length).toBeGreaterThan(0);
    expect(policies.items.length).toBeGreaterThan(0);
  });

  it("retries the load after a failed chunk download", async () => {
    const real = new MockClient({ latencyMs: [0, 0] });
    const load = vi.fn<() => Promise<MockClient>>().mockRejectedValueOnce(new Error("chunk failed")).mockResolvedValue(real);
    const client = new LazyClient("mock", load);

    await expect(client.health()).rejects.toThrow("chunk failed");
    await expect(client.health()).resolves.toBeDefined();
    expect(load).toHaveBeenCalledTimes(2);
  });

  it("keeps one stateful mock world per client", async () => {
    const client = createApiClient(() => null, "mock");
    expect(client.mode).toBe("mock");
    const { token } = await client.login(process.env.NEXT_PUBLIC_MOCK_PASSCODE || "larkspur-demo");
    expect(token).toBeTruthy();
    const pending = await client.listApprovals("pending");
    const first = pending.items[0];
    expect(first).toBeDefined();
    await client.resolveApproval(first!.approval_id, { resolution: "approved", note: "ok" });
    const after = await client.listApprovals("pending");
    expect(after.items.map((a) => a.approval_id)).not.toContain(first!.approval_id);
  });
});
