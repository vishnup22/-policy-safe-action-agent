import type { ApiClient, ApiMode } from "./client";

/**
 * Forwards every call to a client that is loaded on first use, so pages that never
 * call the API (the landing hero, the login form before submit) don't download the
 * Zod schemas or the mock world.
 */
export class LazyClient implements ApiClient {
  private client: Promise<ApiClient> | undefined;

  constructor(
    readonly mode: ApiMode,
    private readonly load: () => Promise<ApiClient>,
  ) {}

  private resolve(): Promise<ApiClient> {
    this.client ??= this.load().catch((err: unknown) => {
      this.client = undefined;
      throw err;
    });
    return this.client;
  }

  login: ApiClient["login"] = (...args) => this.resolve().then((c) => c.login(...args));
  health: ApiClient["health"] = (...args) => this.resolve().then((c) => c.health(...args));
  createConversation: ApiClient["createConversation"] = (...args) =>
    this.resolve().then((c) => c.createConversation(...args));
  listConversations: ApiClient["listConversations"] = (...args) =>
    this.resolve().then((c) => c.listConversations(...args));
  sendMessage: ApiClient["sendMessage"] = (...args) => this.resolve().then((c) => c.sendMessage(...args));
  getEvents: ApiClient["getEvents"] = (...args) => this.resolve().then((c) => c.getEvents(...args));
  listApprovals: ApiClient["listApprovals"] = (...args) => this.resolve().then((c) => c.listApprovals(...args));
  resolveApproval: ApiClient["resolveApproval"] = (...args) =>
    this.resolve().then((c) => c.resolveApproval(...args));
  listPolicies: ApiClient["listPolicies"] = (...args) => this.resolve().then((c) => c.listPolicies(...args));
  getPolicy: ApiClient["getPolicy"] = (...args) => this.resolve().then((c) => c.getPolicy(...args));
  listEvalRuns: ApiClient["listEvalRuns"] = (...args) => this.resolve().then((c) => c.listEvalRuns(...args));
  getEvalRun: ApiClient["getEvalRun"] = (...args) => this.resolve().then((c) => c.getEvalRun(...args));
}
