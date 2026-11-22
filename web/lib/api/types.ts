import type { z } from "zod";
import type * as s from "./schemas";

export type ActionName = z.infer<typeof s.ActionNameSchema>;
export type DecisionOutcome = z.infer<typeof s.DecisionOutcomeSchema>;
export type ReasonCode = z.infer<typeof s.ReasonCodeSchema>;
export type EventType = z.infer<typeof s.EventTypeSchema>;
export type ConversationStatus = z.infer<typeof s.ConversationStatusSchema>;
export type ApprovalStatus = z.infer<typeof s.ApprovalStatusSchema>;
export type ApprovalResolution = z.infer<typeof s.ApprovalResolutionSchema>;
export type SystemUnderTest = z.infer<typeof s.SystemUnderTestSchema>;
export type ScenarioCategory = z.infer<typeof s.ScenarioCategorySchema>;

export type Address = z.infer<typeof s.AddressSchema>;
export type ActionArgs = z.infer<typeof s.ActionArgsSchema>;
export type ActionIntent = z.infer<typeof s.ActionIntentSchema>;
export type RuleResult = z.infer<typeof s.RuleResultSchema>;
export type Decision = z.infer<typeof s.DecisionSchema>;

export type Event = z.infer<typeof s.EventSchema>;
export type EventOf<T extends EventType> = Extract<Event, { type: T }>;

export type LoginResponse = z.infer<typeof s.LoginResponseSchema>;
export type Health = z.infer<typeof s.HealthSchema>;
export type CreateConversationRequest = z.infer<typeof s.CreateConversationRequestSchema>;
export type CreateConversationResponse = z.infer<typeof s.CreateConversationResponseSchema>;
export type ConversationSummary = z.infer<typeof s.ConversationSummarySchema>;
export type ConversationList = z.infer<typeof s.ConversationListSchema>;
export type SendMessageResponse = z.infer<typeof s.SendMessageResponseSchema>;
export type ConversationEvents = z.infer<typeof s.ConversationEventsSchema>;

export type Approval = z.infer<typeof s.ApprovalSchema>;
export type ApprovalList = z.infer<typeof s.ApprovalListSchema>;
export type ResolveApprovalRequest = z.infer<typeof s.ResolveApprovalRequestSchema>;

export type PolicySummary = z.infer<typeof s.PolicySummarySchema>;
export type PolicyList = z.infer<typeof s.PolicyListSchema>;
export type PolicyDetail = z.infer<typeof s.PolicyDetailSchema>;

export type EvalRunSummary = z.infer<typeof s.EvalRunSummarySchema>;
export type EvalRunList = z.infer<typeof s.EvalRunListSchema>;
export type TrialResult = z.infer<typeof s.TrialResultSchema>;
export type ScenarioResult = z.infer<typeof s.ScenarioResultSchema>;
export type SystemMetrics = z.infer<typeof s.SystemMetricsSchema>;
export type EvalRunReport = z.infer<typeof s.EvalRunReportSchema>;
