"use client";

import { useMutation, useQuery, useQueryClient, type QueryKey } from "@tanstack/react-query";
import { useApi } from "@/lib/auth";
import { ApiError } from "./client";
import type { Approval, ApprovalList, ApprovalResolution, ApprovalStatus } from "./types";

export const queryKeys = {
  conversations: ["conversations"] as const,
  events: (id: string) => ["events", id] as const,
  approvals: (status?: ApprovalStatus) => ["approvals", status ?? "all"] as const,
  approvalsRoot: ["approvals"] as const,
  evalRuns: ["evals", "runs"] as const,
  evalRun: (id: string) => ["evals", "run", id] as const,
  policies: ["policies"] as const,
  policy: (set: string) => ["policies", "detail", set] as const,
  policyDiff: (set: string, from: string, to: string) => ["policies", "diff", set, from, to] as const,
};

export function useConversations() {
  const api = useApi();
  return useQuery({ queryKey: queryKeys.conversations, queryFn: () => api.listConversations() });
}

export function useConversationEvents(id: string) {
  const api = useApi();
  return useQuery({ queryKey: queryKeys.events(id), queryFn: () => api.getEvents(id), enabled: !!id });
}

export function useApprovals(status?: ApprovalStatus) {
  const api = useApi();
  return useQuery({ queryKey: queryKeys.approvals(status), queryFn: () => api.listApprovals(status) });
}

export function useEvalRuns() {
  const api = useApi();
  return useQuery({ queryKey: queryKeys.evalRuns, queryFn: () => api.listEvalRuns() });
}

export function useEvalRun(id: string) {
  const api = useApi();
  return useQuery({ queryKey: queryKeys.evalRun(id), queryFn: () => api.getEvalRun(id), enabled: !!id });
}

export function usePolicies() {
  const api = useApi();
  return useQuery({ queryKey: queryKeys.policies, queryFn: () => api.listPolicies() });
}

export function usePolicy(set: string) {
  const api = useApi();
  return useQuery({ queryKey: queryKeys.policy(set), queryFn: () => api.getPolicy(set), enabled: !!set });
}

export function usePolicyDiff(set: string, versions: { from: string; to: string } | null) {
  const api = useApi();
  return useQuery({
    queryKey: queryKeys.policyDiff(set, versions?.from ?? "", versions?.to ?? ""),
    queryFn: () => api.getPolicyDiff(set, versions!),
    enabled: !!set && !!versions,
  });
}

export interface ResolveVars {
  approval: Approval;
  resolution: ApprovalResolution;
  note: string;
}

type Snapshot = Array<[QueryKey, ApprovalList | undefined]>;

/**
 * Resolve an approval with an optimistic move between the status lists.
 * Any error rolls the cache back; a 409 means someone else already resolved it,
 * so we also refetch to show the real state.
 */
export function useResolveApproval(callbacks: {
  onConflict?: (err: ApiError) => void;
  onError?: (err: Error) => void;
  onSuccess?: (approval: Approval) => void;
} = {}) {
  const api = useApi();
  const qc = useQueryClient();

  return useMutation<Approval, Error, ResolveVars, { snapshot: Snapshot }>({
    mutationFn: ({ approval, resolution, note }) =>
      api.resolveApproval(approval.approval_id, { resolution, note: note.trim() || null }),

    onMutate: async ({ approval, resolution, note }) => {
      await qc.cancelQueries({ queryKey: queryKeys.approvalsRoot });
      const snapshot = qc.getQueriesData<ApprovalList>({ queryKey: queryKeys.approvalsRoot });
      const optimistic: Approval = {
        ...approval,
        status: resolution,
        note: note.trim() || null,
        resolved_at: new Date().toISOString(),
      };
      for (const [key, data] of snapshot) {
        if (!data) continue;
        const filter = key[1] as ApprovalStatus | "all";
        const rest = data.items.filter((a) => a.approval_id !== approval.approval_id);
        const items =
          filter === "all" ? [optimistic, ...rest] : filter === resolution ? [optimistic, ...rest] : rest;
        qc.setQueryData<ApprovalList>(key, { items });
      }
      return { snapshot };
    },

    onError: (err, _vars, ctx) => {
      ctx?.snapshot.forEach(([key, data]) => qc.setQueryData(key, data));
      if (err instanceof ApiError && err.status === 409) callbacks.onConflict?.(err);
      else callbacks.onError?.(err);
    },

    onSuccess: (approval) => callbacks.onSuccess?.(approval),

    onSettled: (_data, _err, vars) => {
      void qc.invalidateQueries({ queryKey: queryKeys.approvalsRoot });
      void qc.invalidateQueries({ queryKey: queryKeys.conversations });
      void qc.invalidateQueries({ queryKey: queryKeys.events(vars.approval.conversation_id) });
    },
  });
}
