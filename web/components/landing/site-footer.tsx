"use client";

import { ArrowUp, ClipboardCheck, FlaskConical, GitBranch, History, MessageSquare } from "lucide-react";
import { Dock, type DockItem } from "@/components/ui/glass";
import { REPO_URL } from "@/lib/site";

const ITEMS: DockItem[] = [
  { href: "/chat", label: "Chat console", icon: MessageSquare },
  { href: "/conversations", label: "Replay conversations", icon: History },
  { href: "/approvals", label: "Approvals queue", icon: ClipboardCheck },
  { href: "/evals", label: "Eval runs", icon: FlaskConical },
  { href: REPO_URL, label: "Source on GitHub", icon: GitBranch, external: true },
  { href: "#top", label: "Back to top", icon: ArrowUp },
];

export function SiteFooter() {
  return (
    <footer className="flex flex-col items-center gap-5 px-4 pt-6 pb-10">
      <Dock items={ITEMS} label="Footer" />
      <p className="max-w-md text-center text-xs leading-relaxed text-muted-foreground">
        Policy-Safe Action Agent — a portfolio proof of concept. Larkspur Goods is fictional; all data is synthetic.
      </p>
    </footer>
  );
}
