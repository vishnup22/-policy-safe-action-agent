import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it } from "vitest";
import { ActionCard } from "@/components/action-card";
import { DecisionBadge } from "@/components/decision-badge";
import { RuleResultsTable } from "@/components/rule-results-table";
import { buildSeed } from "@/lib/api/mock/seed";
import type { DecisionOutcome } from "@/lib/api/types";
import { extractActions } from "@/lib/events";

const seed = buildSeed();
const actionFor = (story: string) => extractActions(seed.conversations.find((c) => c.story === story)!.events)[0];

describe("DecisionBadge", () => {
  it.each([
    ["ALLOW", "Allowed"],
    ["REQUIRE_APPROVAL", "Needs approval"],
    ["REQUIRE_VERIFICATION", "Needs verification"],
    ["DENY", "Denied"],
  ] as Array<[DecisionOutcome, string]>)("%s renders text, icon and an accessible label", (outcome, label) => {
    const { container } = render(<DecisionBadge outcome={outcome} />);
    const badge = container.querySelector(`[data-outcome="${outcome}"]`)!;
    expect(badge).toHaveTextContent(outcome);
    expect(badge).toHaveTextContent(label);
    expect(badge.querySelector("svg")).not.toBeNull();
  });

  it("uses a distinct style per outcome", () => {
    const outcomes: DecisionOutcome[] = ["ALLOW", "REQUIRE_APPROVAL", "REQUIRE_VERIFICATION", "DENY"];
    const classes = outcomes.map((o) => {
      const { container } = render(<DecisionBadge outcome={o} />);
      return container.firstElementChild!.className;
    });
    expect(new Set(classes).size).toBe(4);
  });
});

describe("RuleResultsTable", () => {
  it("lists every rule and marks the deciding ones", () => {
    const view = actionFor("injection");
    render(<RuleResultsTable decision={view.decision!} />);
    const rows = screen.getAllByRole("row").slice(1);
    expect(rows).toHaveLength(view.decision!.rule_results.length);
    const deciding = rows.filter((r) => r.hasAttribute("data-deciding"));
    expect(deciding.map((r) => within(r).getAllByRole("cell")[0].textContent)).toEqual([
      "REFUND_WINDOWdeciding",
      "REFUND_AMOUNT_LIMITdeciding",
    ]);
    expect(screen.getByText("AMOUNT_EXCEEDS_REFUNDABLE")).toBeInTheDocument();
  });
});

describe("ActionCard", () => {
  it("shows action, args, decision, deciding rules, reason codes, messages and policy version", () => {
    render(<ActionCard view={actionFor("out_of_window")} />);
    const card = screen.getByRole("article", { name: /Issue refund/ });
    expect(within(card).getByText("ord_b8c9d0")).toBeInTheDocument();
    expect(card.querySelector('[data-outcome="DENY"]')).not.toBeNull();
    expect(within(card).getByText("REFUND_WINDOW")).toBeInTheDocument();
    expect(within(card).getByText("OUTSIDE_RETURN_WINDOW")).toBeInTheDocument();
    expect(within(card).getByText("Delivered 41 days ago; return window is 30 days")).toBeInTheDocument();
    expect(within(card).getByText("v2026.11.21-1")).toBeInTheDocument();
    expect(within(card).getByText("Not executed")).toBeInTheDocument();
  });

  it("shows the idempotency key once executed", () => {
    const view = actionFor("in_window");
    render(<ActionCard view={view} />);
    expect(screen.getByText(view.intent.idempotency_key)).toBeInTheDocument();
  });

  it("shows pending approval state", () => {
    render(<ActionCard view={actionFor("high_value")} />);
    expect(screen.getByText(/Awaiting human approval/)).toBeInTheDocument();
  });

  it("expands to the full rule table and facts snapshot", async () => {
    const user = userEvent.setup();
    render(<ActionCard view={actionFor("in_window")} />);
    const toggle = screen.getByRole("button", { name: /Show all \d+ rules/ });
    expect(toggle).toHaveAttribute("aria-expanded", "false");
    await user.click(toggle);
    expect(toggle).toHaveAttribute("aria-expanded", "true");
    expect(screen.getByRole("table")).toBeInTheDocument();
    expect(screen.getByText("order.days_since_delivery")).toBeInTheDocument();
    expect(screen.getByText(/not used as a fact/)).toBeInTheDocument();
  });
});
