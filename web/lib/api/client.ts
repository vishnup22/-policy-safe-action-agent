import type {
  Approval,
  ApprovalList,
  ApprovalStatus,
  ConversationEvents,
  ConversationList,
  CreateConversationRequest,
  CreateConversationResponse,
  EvalRunList,
  EvalRunReport,
  Health,
  LoginResponse,
  PolicyDetail,
  PolicyDiff,
  PolicyList,
  ResolveApprovalRequest,
  SendMessageResponse,
} from "./types";

export type ApiMode = "mock" | "live";

export class ApiError extends Error {
  readonly status: number;
  readonly code: string;

  constructor(status: number, code: string, message: string) {
    super(message);
    this.name = "ApiError";
    this.status = status;
    this.code = code;
  }
}

export interface ApiClient {
  readonly mode: ApiMode;
  login(passcode: string): Promise<LoginResponse>;
  health(): Promise<Health>;

  createConversation(req: CreateConversationRequest): Promise<CreateConversationResponse>;
  listConversations(params?: { limit?: number; cursor?: string }): Promise<ConversationList>;
  sendMessage(conversationId: string, text: string): Promise<SendMessageResponse>;
  getEvents(conversationId: string): Promise<ConversationEvents>;

  listApprovals(status?: ApprovalStatus): Promise<ApprovalList>;
  resolveApproval(approvalId: string, req: ResolveApprovalRequest): Promise<Approval>;

  listPolicies(): Promise<PolicyList>;
  getPolicy(policySet: string): Promise<PolicyDetail>;
  /** `404` when either version is unknown. */
  getPolicyDiff(policySet: string, versions: { from: string; to: string }): Promise<PolicyDiff>;

  listEvalRuns(params?: { limit?: number }): Promise<EvalRunList>;
  getEvalRun(runId: string): Promise<EvalRunReport>;
}
