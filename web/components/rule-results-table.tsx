import Link from "next/link";
import type { Decision } from "@/lib/api/types";
import { policyDiffHref } from "@/lib/policy-diff";
import { cn } from "@/lib/utils";
import { DecisionBadge } from "./decision-badge";

export function RuleResultsTable({ decision }: { decision: Decision }) {
  return (
    <div className="overflow-x-auto rounded-xl border border-glass-edge">
      <table className="w-full text-left text-xs">
        <caption className="sr-only">
          Rule results for intent {decision.intent_id}; final outcome {decision.outcome}
        </caption>
        <thead className="bg-muted text-muted-foreground">
          <tr>
            <th scope="col" className="px-3 py-2 font-medium">Rule</th>
            <th scope="col" className="px-3 py-2 font-medium">Outcome</th>
            <th scope="col" className="px-3 py-2 font-medium">Reason code</th>
            <th scope="col" className="px-3 py-2 font-medium">Message</th>
          </tr>
        </thead>
        <tbody>
          {decision.rule_results.map((r) => {
            const deciding = r.outcome === decision.outcome;
            return (
              <tr
                key={r.rule_id}
                data-deciding={deciding || undefined}
                className={cn("border-t align-top", deciding && "bg-muted")}
              >
                <td className="px-3 py-2 font-mono font-medium">
                  <Link
                    href={policyDiffHref(decision.policy_set, { from: decision.policy_version, rule: r.rule_id })}
                    title={`How ${r.rule_id} changed since policy ${decision.policy_version}`}
                    className="underline decoration-muted-foreground/40 underline-offset-4 hover:decoration-foreground focus-visible:outline-2 focus-visible:outline-ring"
                  >
                    {r.rule_id}
                  </Link>
                  {deciding && <span className="ml-1.5 text-[10px] font-sans font-normal text-muted-foreground uppercase">deciding</span>}
                </td>
                <td className="px-3 py-2"><DecisionBadge outcome={r.outcome} size="sm" /></td>
                <td className="px-3 py-2 font-mono">{r.reason_code ?? <span className="text-muted-foreground">—</span>}</td>
                <td className="px-3 py-2">{r.message}</td>
              </tr>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}
