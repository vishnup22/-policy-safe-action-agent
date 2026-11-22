import { describe, expect, it, vi } from "vitest";
import { ApiError } from "@/lib/api/client";
import { LiveClient } from "@/lib/api/live-client";
import { MockClient } from "@/lib/api/mock-client";
import { DEMO_PROMPTS, routeStory } from "@/lib/api/mock/stories";
import { extractActions } from "@/lib/events";

const fast = () => new MockClient({ latencyMs: [0, 0] });

describe("MockClient", () => {
  it("rejects a wrong passcode with 401 and accepts the demo passcode", async () => {
    const api = fast();
    await expect(api.login("nope")).rejects.toMatchObject({ status: 401, code: "INVALID_PASSCODE" });
    await expect(api.login("larkspur-demo")).resolves.toMatchObject({ token: expect.any(String) });
  });

  it("routes each demo prompt to its story", () => {
    for (const p of DEMO_PROMPTS) expect(routeStory(p.text)).toBe(p.story);
    expect(routeStory("hello there")).toBeNull();
  });

  it.each([
    ["in_window", "ALLOW"],
    ["out_of_window", "DENY"],
    ["high_value", "REQUIRE_APPROVAL"],
    ["injection", "DENY"],
    ["follow_up", "ALLOW"],
  ] as const)("chat story %s → %s for a verified customer", async (story, outcome) => {
    const api = fast();
    const { conversation_id } = await api.createConversation({ customer_email: "maya.r@example.com" });
    const text = DEMO_PROMPTS.find((p) => p.story === story)!.text;
    const res = await api.sendMessage(conversation_id, text);
    const [action] = extractActions(res.events);
    expect(action.decision?.outcome).toBe(outcome);
    expect(res.events[0].seq).toBe(1);
    expect(Boolean(res.pending_approval_id)).toBe(outcome === "REQUIRE_APPROVAL");
    const log = await api.getEvents(conversation_id);
    expect(log.events.map((e) => e.seq)).toEqual(log.events.map((_, i) => i));
  });

  it("asks an anonymous visitor to verify before refunding", async () => {
    const api = fast();
    const { conversation_id } = await api.createConversation({});
    const res = await api.sendMessage(conversation_id, DEMO_PROMPTS[0].text);
    expect(extractActions(res.events)[0].decision?.outcome).toBe("REQUIRE_VERIFICATION");
    expect(res.events.some((e) => e.type === "action_executed")).toBe(false);
  });

  it("falls back to a help reply without proposing actions", async () => {
    const api = fast();
    const { conversation_id } = await api.createConversation({});
    const res = await api.sendMessage(conversation_id, "hello");
    expect(extractActions(res.events)).toHaveLength(0);
    expect(res.reply.text).toMatch(/order number/);
  });

  it("approving executes the action once; resolving again is a 409", async () => {
    const api = fast();
    const pending = (await api.listApprovals("pending")).items[0];
    const updated = await api.resolveApproval(pending.approval_id, { resolution: "approved", note: "ok" });
    expect(updated).toMatchObject({ status: "approved", note: "ok" });

    const log = await api.getEvents(pending.conversation_id);
    const executed = log.events.filter((e) => e.type === "action_executed");
    expect(executed).toHaveLength(1);
    expect(log.events.some((e) => e.type === "approval_resolved")).toBe(true);

    await expect(api.resolveApproval(pending.approval_id, { resolution: "rejected" })).rejects.toMatchObject({
      status: 409,
      code: "APPROVAL_ALREADY_RESOLVED",
    });
    expect((await api.listApprovals("pending")).items.find((a) => a.approval_id === pending.approval_id)).toBeUndefined();
  });

  it("summarizes conversations with status and counts", async () => {
    const api = fast();
    const { items } = await api.listConversations();
    const byId = Object.fromEntries(items.map((c) => [c.conversation_id, c]));
    expect(byId.conv_8f3k2l1m).toMatchObject({ status: "ended", actions_executed: 1, actions_blocked: 0 });
    expect(byId.conv_b2n7c4x9).toMatchObject({ actions_executed: 0, actions_blocked: 1 });
    expect(byId.conv_l4mp9q2w.status).toBe("awaiting_approval");
  });

  it("404s on unknown resources", async () => {
    const api = fast();
    await expect(api.getEvents("conv_missing")).rejects.toBeInstanceOf(ApiError);
    await expect(api.getEvalRun("run_missing")).rejects.toMatchObject({ status: 404 });
  });
});

function jsonResponse(status: number, body: unknown) {
  return new Response(JSON.stringify(body), { status, headers: { "Content-Type": "application/json" } });
}

describe("LiveClient", () => {
  it("sends the bearer token and parses responses", async () => {
    const fetchImpl = vi.fn(async () =>
      jsonResponse(200, { status: "ok", version: "0.1.0", policy_version: "2026.11.21-1" }),
    );
    const api = new LiveClient({ baseUrl: "http://api.test/", getToken: () => "tok_123", fetchImpl });
    await api.listPolicies().catch(() => undefined);
    const [url, init] = fetchImpl.mock.calls[0] as unknown as [string, RequestInit];
    expect(url).toBe("http://api.test/api/policies");
    expect((init.headers as Record<string, string>).Authorization).toBe("Bearer tok_123");
  });

  it("does not send a token to the login endpoint", async () => {
    const fetchImpl = vi.fn(async () => jsonResponse(200, { token: "t", expires_at: "2026-11-22T12:00:00Z" }));
    const api = new LiveClient({ baseUrl: "http://api.test", getToken: () => "tok_123", fetchImpl });
    await expect(api.login("pass")).resolves.toEqual({ token: "t", expires_at: "2026-11-22T12:00:00Z" });
    const [, init] = fetchImpl.mock.calls[0] as unknown as [string, RequestInit];
    expect((init.headers as Record<string, string>).Authorization).toBeUndefined();
    expect(init.body).toBe(JSON.stringify({ passcode: "pass" }));
  });

  it("maps the error envelope to ApiError", async () => {
    const fetchImpl = vi.fn(async () =>
      jsonResponse(409, { error: { code: "APPROVAL_ALREADY_RESOLVED", message: "Already approved" } }),
    );
    const api = new LiveClient({ baseUrl: "http://api.test", getToken: () => "t", fetchImpl });
    await expect(api.resolveApproval("apr_1", { resolution: "approved" })).rejects.toMatchObject({
      status: 409,
      code: "APPROVAL_ALREADY_RESOLVED",
      message: "Already approved",
    });
  });

  it("flags responses that do not match the contract", async () => {
    const fetchImpl = vi.fn(async () => jsonResponse(200, { items: [{ nope: true }] }));
    const api = new LiveClient({ baseUrl: "http://api.test", getToken: () => "t", fetchImpl });
    await expect(api.listApprovals()).rejects.toMatchObject({ code: "CONTRACT_MISMATCH" });
  });

  it("reports network failures", async () => {
    const fetchImpl = vi.fn(async () => {
      throw new TypeError("Failed to fetch");
    });
    const api = new LiveClient({ baseUrl: "http://api.test", getToken: () => null, fetchImpl });
    await expect(api.health()).rejects.toMatchObject({ status: 0, code: "NETWORK_ERROR" });
  });
});
