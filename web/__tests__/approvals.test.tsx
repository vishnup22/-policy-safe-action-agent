import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it } from "vitest";
import { ApprovalsView } from "@/app/(console)/approvals/approvals-view";
import { Providers } from "@/components/providers";
import { ApiError } from "@/lib/api/client";
import { MockClient } from "@/lib/api/mock-client";
import type { Approval, ResolveApprovalRequest } from "@/lib/api/types";

/** MockClient whose resolveApproval is controlled by the test. */
class ControlledClient extends MockClient {
  resolveCalls: Array<{ id: string; req: ResolveApprovalRequest }> = [];
  private pending: { resolve: (a: Approval) => void; reject: (e: Error) => void } | null = null;

  constructor() {
    super({ latencyMs: [0, 0] });
  }

  override resolveApproval(id: string, req: ResolveApprovalRequest): Promise<Approval> {
    this.resolveCalls.push({ id, req });
    return new Promise((resolve, reject) => {
      this.pending = { resolve, reject };
    });
  }

  fail(err: Error) {
    this.pending?.reject(err);
  }

  succeed(a: Approval) {
    this.pending?.resolve(a);
  }
}

function setup() {
  const client = new ControlledClient();
  const user = userEvent.setup();
  render(
    <Providers client={client}>
      <ApprovalsView />
    </Providers>,
  );
  return { client, user };
}

async function approveFirstPending(user: ReturnType<typeof userEvent.setup>) {
  const list = await screen.findByRole("list", { name: "pending approvals" });
  const item = within(list).getByRole("button", { name: /Issue refund/ });
  await user.click(item);
  const drawer = await screen.findByRole("dialog");
  await user.type(within(drawer).getByLabelText(/Reviewer note/), "Photo verified");
  await user.click(within(drawer).getByRole("button", { name: /Approve/ }));
}

describe("Approvals queue", () => {
  it("removes the item optimistically, then rolls back on error", async () => {
    const { client, user } = setup();
    await approveFirstPending(user);

    expect(client.resolveCalls[0]).toEqual({
      id: "apr_5t6y7u8i",
      req: { resolution: "approved", note: "Photo verified" },
    });
    await waitFor(() => expect(screen.getByText("No pending approvals.")).toBeInTheDocument());

    client.fail(new ApiError(500, "INTERNAL", "Executor unavailable"));
    expect(await screen.findByText(/changes rolled back/)).toBeInTheDocument();
    const list = await screen.findByRole("list", { name: "pending approvals" });
    expect(within(list).getByRole("button", { name: /Issue refund/ })).toBeInTheDocument();
  });

  it("explains a 409 conflict and keeps the queue consistent", async () => {
    const { client, user } = setup();
    await approveFirstPending(user);
    client.fail(new ApiError(409, "APPROVAL_ALREADY_RESOLVED", "Approval was already approved."));
    expect(await screen.findByText("Already resolved")).toBeInTheDocument();
  });

  it("keeps the optimistic state when the server confirms", async () => {
    const { client, user } = setup();
    await approveFirstPending(user);
    const original = (await new MockClient({ latencyMs: [0, 0] }).listApprovals("pending")).items[0];
    client.succeed({ ...original, status: "approved", note: "Photo verified", reviewer: "me", resolved_at: original.requested_at });
    expect(await screen.findByText("Approval approved")).toBeInTheDocument();
  });

  it("shows resolved approvals in their tabs", async () => {
    const { user } = setup();
    await screen.findByRole("list", { name: "pending approvals" });
    await user.click(screen.getByRole("tab", { name: /Rejected/ }));
    const list = await screen.findByRole("list", { name: "rejected approvals" });
    expect(within(list).getByText(/\$260\.00 on ord_w1x2y3/)).toBeInTheDocument();
  });
});
