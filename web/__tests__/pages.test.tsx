import type { ComponentProps, ReactNode } from "react";
import { fireEvent, render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";
import { ChatView } from "@/app/(console)/chat/chat-view";
import { ConversationList } from "@/app/(console)/conversations/conversation-list";
import { ReplayView } from "@/app/(console)/conversations/[id]/replay-view";
import { EvalRunDetail } from "@/app/(console)/evals/[runId]/eval-run-detail";
import { EvalRunList } from "@/app/(console)/evals/eval-run-list";
import { Providers } from "@/components/providers";
import { MockClient } from "@/lib/api/mock-client";

vi.mock("next/link", () => ({
  default: ({ href, children, ...rest }: ComponentProps<"a"> & { href: string }) => (
    <a href={href} {...rest}>
      {children}
    </a>
  ),
}));

class ResizeObserverStub {
  observe() {}
  unobserve() {}
  disconnect() {}
}
globalThis.ResizeObserver ??= ResizeObserverStub as unknown as typeof ResizeObserver;

function renderWithMock(ui: ReactNode) {
  render(<Providers client={new MockClient({ latencyMs: [0, 0] })}>{ui}</Providers>);
  return userEvent.setup();
}

describe("Chat page", () => {
  it("runs a demo story and shows the inline action card", async () => {
    const user = renderWithMock(<ChatView />);
    await user.click(screen.getByRole("button", { name: "Out-of-window refund" }));
    const card = await screen.findByRole("article", { name: /Issue refund/ });
    expect(card.querySelector('[data-outcome="DENY"]')).not.toBeNull();
    expect(within(card).getByText("OUTSIDE_RETURN_WINDOW")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: /Replay/ })).toHaveAttribute("href", expect.stringMatching(/^\/conversations\/conv_/));
  });

  it("sends a typed message with Enter", async () => {
    const user = renderWithMock(<ChatView />);
    await user.type(screen.getByLabelText("Message"), "The walnut lamp arrived broken{Enter}");
    const card = await screen.findByRole("article", { name: /Issue refund/ });
    expect(card.querySelector('[data-outcome="REQUIRE_APPROVAL"]')).not.toBeNull();
  });
});

describe("Conversations", () => {
  it("lists conversations with status and counts", async () => {
    renderWithMock(<ConversationList />);
    const link = await screen.findByRole("link", { name: "conv_l4mp9q2w" });
    const row = link.closest("tr")!;
    expect(within(row).getByText("Awaiting approval")).toBeInTheDocument();
  });

  it("replay: steps with the keyboard, filters by type, and links executions to decisions", async () => {
    const user = renderWithMock(<ReplayView conversationId="conv_8f3k2l1m" />);
    const timeline = await screen.findByRole("region", { name: "Event timeline" });
    const detail = screen.getByRole("region", { name: "Event detail" });
    expect(within(detail).getByRole("heading", { name: "Conversation started" })).toBeInTheDocument();

    fireEvent.keyDown(window, { key: "ArrowRight" });
    expect(within(detail).getByRole("heading", { name: "User message" })).toBeInTheDocument();
    fireEvent.keyDown(window, { key: "ArrowLeft" });
    expect(within(detail).getByRole("heading", { name: "Conversation started" })).toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: /allowed by decision #\d+/ }));
    expect(within(detail).getByRole("heading", { name: "Policy decision" })).toBeInTheDocument();
    expect(within(detail).getByText("order.days_since_delivery")).toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: "Model call" }));
    expect(screen.getByRole("button", { name: "Model call" })).toHaveAttribute("aria-pressed", "false");
    expect(within(timeline).queryByText("Model call")).toBeNull();
  });

  it("replay flags untrusted order notes", async () => {
    const user = renderWithMock(<ReplayView conversationId="conv_h7nj3c5t" />);
    const timeline = await screen.findByRole("region", { name: "Event timeline" });
    await user.click(within(timeline).getByText("Tool result"));
    expect(screen.getByRole("note")).toHaveTextContent(/Untrusted customer text/);
  });
});

describe("Evals", () => {
  it("lists runs", async () => {
    renderWithMock(<EvalRunList />);
    expect(await screen.findByRole("link", { name: /run_20261121_1200/ })).toBeInTheDocument();
    expect(screen.getByRole("link", { name: /run_20261120_1800/ })).toBeInTheDocument();
  });

  it("shows headline cards, pass^k table and scenario drill-down", async () => {
    const user = renderWithMock(<EvalRunDetail runId="run_20261121_1200" />);
    const card = await screen.findByRole("region", { name: "Unauthorized action rate" });
    expect(within(card).getByText(/lower is better/)).toBeInTheDocument();
    expect(screen.getByRole("img", { name: /pass\^k line chart/ })).toBeInTheDocument();
    expect(screen.getByRole("table", { name: "pass^k values" })).toBeInTheDocument();

    const toggle = screen.getByRole("button", { name: "injection-order-notes-refund" });
    await user.click(toggle);
    expect(toggle).toHaveAttribute("aria-expanded", "true");
    expect(screen.getAllByRole("heading", { name: /baseline|guarded/i }).length).toBeGreaterThanOrEqual(2);
  });
});
