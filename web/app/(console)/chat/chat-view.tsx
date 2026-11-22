"use client";

import { useEffect, useRef, useState, type FormEvent, type KeyboardEvent } from "react";
import Link from "next/link";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { Bot, History, Loader2, Plus, Send, User } from "lucide-react";
import { toast } from "sonner";
import { ActionCard } from "@/components/action-card";
import { DecisionBadge, OUTCOME_META } from "@/components/decision-badge";
import { Button, buttonVariants } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import { ApiError, type DecisionOutcome } from "@/lib/api";
import { DEMO_CUSTOMERS, DEMO_PROMPTS } from "@/lib/api/mock/stories";
import { queryKeys } from "@/lib/api/queries";
import { useApi } from "@/lib/auth";
import { extractActions, type ActionView } from "@/lib/events";
import { cn, formatTime } from "@/lib/utils";

interface Turn {
  key: string;
  role: "user" | "agent";
  text: string;
  at: string;
  actions: ActionView[];
}

interface Session {
  conversationId: string;
  email: string | null;
}

export function ChatView() {
  const api = useApi();
  const qc = useQueryClient();
  const [email, setEmail] = useState(DEMO_CUSTOMERS[0].email);
  const [session, setSession] = useState<Session | null>(null);
  const [turns, setTurns] = useState<Turn[]>([]);
  const [draft, setDraft] = useState("");
  const bottomRef = useRef<HTMLLIElement>(null);

  useEffect(() => {
    bottomRef.current?.scrollIntoView?.({ behavior: "smooth", block: "end" });
  }, [turns]);

  const start = useMutation({
    mutationFn: (customerEmail: string | null) =>
      api.createConversation(customerEmail ? { customer_email: customerEmail } : {}),
    onSuccess: (res, customerEmail) => {
      setSession({ conversationId: res.conversation_id, email: customerEmail });
      setTurns([]);
      void qc.invalidateQueries({ queryKey: queryKeys.conversations });
    },
    onError: (err) => toast.error(err instanceof ApiError ? err.message : "Couldn't start a conversation"),
  });

  const send = useMutation({
    mutationFn: async (text: string) => {
      let current = session;
      if (!current) {
        const customerEmail = email.trim() || null;
        const res = await start.mutateAsync(customerEmail);
        current = { conversationId: res.conversation_id, email: customerEmail };
      }
      return api.sendMessage(current.conversationId, text);
    },
    onMutate: (text) => {
      setTurns((t) => [
        ...t,
        { key: `u${t.length}`, role: "user", text, at: new Date().toISOString(), actions: [] },
      ]);
      setDraft("");
    },
    onSuccess: (res) => {
      setTurns((t) => [
        ...t,
        {
          key: `a${t.length}`,
          role: "agent",
          text: res.reply.text,
          at: res.reply.at,
          actions: extractActions(res.events),
        },
      ]);
      void qc.invalidateQueries({ queryKey: queryKeys.conversations });
      if (res.pending_approval_id) {
        void qc.invalidateQueries({ queryKey: queryKeys.approvalsRoot });
        toast.info("Sent to the approvals queue", { description: res.pending_approval_id });
      }
    },
    onError: (err, text) => {
      setTurns((t) => t.slice(0, -1));
      setDraft(text);
      toast.error(err instanceof ApiError ? err.message : "Message failed to send");
    },
  });

  const busy = send.isPending || start.isPending;

  function submit(text: string) {
    const trimmed = text.trim();
    if (!trimmed || busy) return;
    send.mutate(trimmed);
  }

  function onSubmit(e: FormEvent) {
    e.preventDefault();
    submit(draft);
  }

  function onKeyDown(e: KeyboardEvent<HTMLTextAreaElement>) {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      submit(draft);
    }
  }

  function reset() {
    setSession(null);
    setTurns([]);
    setDraft("");
  }

  return (
    <div className="grid flex-1 gap-4 lg:grid-cols-[minmax(0,1fr)_320px]">
      <section aria-label="Conversation" className="flex min-h-[70dvh] flex-col rounded-xl border bg-card">
        <header className="flex flex-wrap items-center justify-between gap-2 border-b px-4 py-3">
          <div className="min-w-0">
            <h1 className="font-semibold">Customer chat</h1>
            <p className="truncate text-xs text-muted-foreground">
              {session ? (
                <>
                  <span className="font-mono">{session.conversationId}</span> ·{" "}
                  {session.email ?? "anonymous (unverified)"}
                </>
              ) : (
                "Send a message to start a conversation"
              )}
            </p>
          </div>
          {session && (
            <div className="flex gap-2">
              <Link
                href={`/conversations/${session.conversationId}`}
                className={buttonVariants({ variant: "outline", size: "sm" })}
              >
                <History aria-hidden /> Replay
              </Link>
              <Button variant="outline" size="sm" onClick={reset}>
                <Plus aria-hidden /> New
              </Button>
            </div>
          )}
        </header>

        <ol aria-live="polite" className="flex-1 space-y-4 overflow-y-auto px-3 py-4 sm:px-4">
          {turns.length === 0 && (
            <li className="mx-auto max-w-md py-10 text-center text-sm text-muted-foreground">
              Pick a demo story or type a message. The agent can only <em>propose</em> actions — the policy
              engine decides, and every decision shows up inline.
            </li>
          )}
          {turns.map((turn) => (
            <li key={turn.key} className={cn("flex gap-2.5", turn.role === "user" && "flex-row-reverse")}>
              <span
                aria-hidden
                className={cn(
                  "mt-0.5 flex size-7 shrink-0 items-center justify-center rounded-full",
                  turn.role === "user" ? "bg-primary text-primary-foreground" : "bg-muted",
                )}
              >
                {turn.role === "user" ? <User className="size-4" /> : <Bot className="size-4" />}
              </span>
              <div className={cn("flex max-w-[min(42rem,100%)] min-w-0 flex-col gap-2", turn.role === "user" && "items-end")}>
                <div
                  className={cn(
                    "rounded-2xl px-3.5 py-2 text-sm leading-relaxed",
                    turn.role === "user" ? "rounded-tr-sm bg-primary text-primary-foreground" : "rounded-tl-sm bg-muted",
                  )}
                >
                  <span className="sr-only">{turn.role === "user" ? "Customer: " : "Agent: "}</span>
                  {turn.text}
                </div>
                {turn.actions.map((view) => (
                  <div key={view.intent.intent_id} className="w-full">
                    <ActionCard view={view} />
                  </div>
                ))}
                <time className="text-[11px] text-muted-foreground" dateTime={turn.at}>
                  {formatTime(turn.at)} UTC
                </time>
              </div>
            </li>
          ))}
          {send.isPending && (
            <li className="flex items-center gap-2 text-sm text-muted-foreground" role="status">
              <Loader2 aria-hidden className="size-4 animate-spin" /> Agent is working…
            </li>
          )}
          <li aria-hidden ref={bottomRef} />
        </ol>

        <div className="border-t p-3">
          <div className="mb-2 flex gap-1.5 overflow-x-auto pb-1" role="group" aria-label="Demo stories">
            {DEMO_PROMPTS.map((p) => (
              <Button
                key={p.story}
                type="button"
                variant="outline"
                size="xs"
                disabled={busy}
                onClick={() => submit(p.text)}
                title={p.text}
              >
                {p.label}
              </Button>
            ))}
          </div>
          <form onSubmit={onSubmit} className="flex items-end gap-2">
            <Label htmlFor="chat-input" className="sr-only">
              Message
            </Label>
            <Textarea
              id="chat-input"
              rows={2}
              value={draft}
              onChange={(e) => setDraft(e.target.value)}
              onKeyDown={onKeyDown}
              placeholder="Type a customer message… (Enter to send, Shift+Enter for a new line)"
              className="min-h-11 resize-none"
            />
            <Button type="submit" size="icon-lg" disabled={busy || !draft.trim()} aria-label="Send message">
              {busy ? <Loader2 aria-hidden className="animate-spin" /> : <Send aria-hidden />}
            </Button>
          </form>
        </div>
      </section>

      <aside className="space-y-4">
        <Card size="sm">
          <CardHeader>
            <CardTitle>Session</CardTitle>
          </CardHeader>
          <CardContent className="space-y-2">
            <Label htmlFor="customer-email">Customer email (optional)</Label>
            <Input
              id="customer-email"
              type="email"
              list="demo-customers"
              placeholder="Leave empty for an unverified visitor"
              value={email}
              disabled={!!session}
              onChange={(e) => setEmail(e.target.value)}
            />
            <datalist id="demo-customers">
              {DEMO_CUSTOMERS.map((c) => (
                <option key={c.customer_id} value={c.email}>
                  {c.full_name}
                </option>
              ))}
            </datalist>
            <p className="text-xs text-muted-foreground">
              A known email simulates a logged-in, verified customer. Leave it empty to see{" "}
              <code className="font-mono">REQUIRE_VERIFICATION</code>.
            </p>
            {!session && (
              <Button
                variant="secondary"
                size="sm"
                className="w-full"
                disabled={busy}
                onClick={() => start.mutate(email.trim() || null)}
              >
                Start conversation
              </Button>
            )}
          </CardContent>
        </Card>

        <Card size="sm">
          <CardHeader>
            <CardTitle>Decision outcomes</CardTitle>
          </CardHeader>
          <CardContent>
            <ul className="space-y-2 text-xs">
              {(Object.keys(OUTCOME_META) as DecisionOutcome[]).map((o) => (
                <li key={o} className="flex items-center justify-between gap-2">
                  <DecisionBadge outcome={o} size="sm" />
                  <span className="text-muted-foreground">{OUTCOME_META[o].label}</span>
                </li>
              ))}
            </ul>
            <p className="mt-3 text-xs text-muted-foreground">
              Precedence: DENY &gt; REQUIRE_VERIFICATION &gt; REQUIRE_APPROVAL &gt; ALLOW.
            </p>
          </CardContent>
        </Card>
      </aside>
    </div>
  );
}
