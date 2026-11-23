import type { z } from "zod";
import { ApiError, type ApiClient } from "./client";
import * as s from "./schemas";
import type { ApprovalStatus, CreateConversationRequest, ResolveApprovalRequest } from "./types";

export interface LiveClientOptions {
  baseUrl: string;
  getToken: () => string | null;
  fetchImpl?: typeof fetch;
}

export class LiveClient implements ApiClient {
  readonly mode = "live" as const;
  private readonly baseUrl: string;
  private readonly getToken: () => string | null;
  private readonly fetchImpl: typeof fetch;

  constructor({ baseUrl, getToken, fetchImpl }: LiveClientOptions) {
    this.baseUrl = baseUrl.replace(/\/+$/, "");
    this.getToken = getToken;
    this.fetchImpl = fetchImpl ?? ((...args) => fetch(...args));
  }

  private async request<S extends z.ZodType>(
    schema: S,
    path: string,
    init: { method?: string; body?: unknown; auth?: boolean } = {},
  ): Promise<z.infer<S>> {
    const headers: Record<string, string> = { Accept: "application/json" };
    if (init.body !== undefined) headers["Content-Type"] = "application/json";
    if (init.auth !== false) {
      const token = this.getToken();
      if (token) headers.Authorization = `Bearer ${token}`;
    }

    let res: Response;
    try {
      res = await this.fetchImpl(`${this.baseUrl}/api${path}`, {
        method: init.method ?? "GET",
        headers,
        body: init.body === undefined ? undefined : JSON.stringify(init.body),
      });
    } catch (err) {
      throw new ApiError(0, "NETWORK_ERROR", err instanceof Error ? err.message : "Network error");
    }

    const body: unknown = await res.json().catch(() => null);
    if (!res.ok) {
      const envelope = s.ApiErrorEnvelopeSchema.safeParse(body);
      if (envelope.success) {
        throw new ApiError(res.status, envelope.data.error.code, envelope.data.error.message);
      }
      throw new ApiError(res.status, `HTTP_${res.status}`, res.statusText || "Request failed");
    }

    const parsed = schema.safeParse(body);
    if (!parsed.success) {
      throw new ApiError(res.status, "CONTRACT_MISMATCH", `Unexpected response from ${path}`);
    }
    return parsed.data;
  }

  login(passcode: string) {
    return this.request(s.LoginResponseSchema, "/auth/demo-login", {
      method: "POST",
      body: { passcode },
      auth: false,
    });
  }

  health() {
    return this.request(s.HealthSchema, "/health", { auth: false });
  }

  createConversation(req: CreateConversationRequest) {
    return this.request(s.CreateConversationResponseSchema, "/conversations", {
      method: "POST",
      body: req,
    });
  }

  listConversations(params: { limit?: number; cursor?: string } = {}) {
    const q = new URLSearchParams({ limit: String(params.limit ?? 50) });
    if (params.cursor) q.set("cursor", params.cursor);
    return this.request(s.ConversationListSchema, `/conversations?${q}`);
  }

  sendMessage(conversationId: string, text: string) {
    return this.request(
      s.SendMessageResponseSchema,
      `/conversations/${encodeURIComponent(conversationId)}/messages`,
      { method: "POST", body: { text } },
    );
  }

  getEvents(conversationId: string) {
    return this.request(
      s.ConversationEventsSchema,
      `/conversations/${encodeURIComponent(conversationId)}/events`,
    );
  }

  listApprovals(status?: ApprovalStatus) {
    const q = status ? `?status=${status}` : "";
    return this.request(s.ApprovalListSchema, `/approvals${q}`);
  }

  resolveApproval(approvalId: string, req: ResolveApprovalRequest) {
    return this.request(s.ApprovalSchema, `/approvals/${encodeURIComponent(approvalId)}/resolve`, {
      method: "POST",
      body: req,
    });
  }

  listPolicies() {
    return this.request(s.PolicyListSchema, "/policies");
  }

  getPolicy(policySet: string) {
    return this.request(s.PolicyDetailSchema, `/policies/${encodeURIComponent(policySet)}`);
  }

  listEvalRuns(params: { limit?: number } = {}) {
    return this.request(s.EvalRunListSchema, `/evals/runs?limit=${params.limit ?? 20}`);
  }

  getEvalRun(runId: string) {
    return this.request(s.EvalRunReportSchema, `/evals/runs/${encodeURIComponent(runId)}`);
  }
}
