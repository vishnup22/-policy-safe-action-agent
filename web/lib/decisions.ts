import type { Decision, DecisionOutcome, RuleResult } from "@/lib/api/types";

/** Mirrors psa.domain.decisions.OUTCOME_PRECEDENCE — higher wins. */
export const OUTCOME_PRECEDENCE: Record<DecisionOutcome, number> = {
  ALLOW: 0,
  REQUIRE_APPROVAL: 1,
  REQUIRE_VERIFICATION: 2,
  DENY: 3,
};

/** No outcomes (no applicable rule) fails closed to DENY, like the backend. */
export function strictest(outcomes: DecisionOutcome[]): DecisionOutcome {
  if (outcomes.length === 0) return "DENY";
  return outcomes.reduce((a, b) => (OUTCOME_PRECEDENCE[b] > OUTCOME_PRECEDENCE[a] ? b : a));
}

/** Rules whose outcome equals the final outcome — what the UI highlights. */
export function decidingRules(decision: Decision): RuleResult[] {
  return decision.rule_results.filter((r) => r.outcome === decision.outcome);
}

export function reasonCodes(decision: Decision): string[] {
  return decision.rule_results.flatMap((r) => (r.reason_code ? [r.reason_code] : []));
}
