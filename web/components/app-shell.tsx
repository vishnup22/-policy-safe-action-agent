"use client";

import { useState, type ReactNode } from "react";
import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { useTheme } from "next-themes";
import {
  ClipboardCheck,
  FileCode2,
  FlaskConical,
  History,
  LogOut,
  Menu,
  MessageSquare,
  Moon,
  ShieldCheck,
  Sun,
} from "lucide-react";
import { PageTransition } from "@/components/page-transition";
import { Button } from "@/components/ui/button";
import { GlassPanel, PillNav, type PillNavItem } from "@/components/ui/glass";
import { Sheet, SheetContent, SheetHeader, SheetTitle } from "@/components/ui/sheet";
import { useApprovals } from "@/lib/api/queries";
import { useAuth } from "@/lib/auth";
import { cn } from "@/lib/utils";

const NAV = [
  { href: "/chat", label: "Chat", icon: MessageSquare },
  { href: "/conversations", label: "Conversations", icon: History },
  { href: "/approvals", label: "Approvals", icon: ClipboardCheck },
  { href: "/policies", label: "Policies", icon: FileCode2 },
  { href: "/evals", label: "Evals", icon: FlaskConical },
] as const;

function useNavItems(): { items: PillNavItem[]; activeHref: string | null } {
  const pathname = usePathname();
  const { data } = useApprovals("pending");
  const pending = data?.items.length ?? 0;
  const items = NAV.map((item) => ({
    ...item,
    badge:
      item.href === "/approvals" && pending > 0 ? (
        <span className="ml-0.5 rounded-full bg-amber-400 px-1.5 text-[11px] leading-5 font-semibold text-amber-950 tabular-nums">
          {pending}
          <span className="sr-only"> pending</span>
        </span>
      ) : undefined,
  }));
  const active = NAV.find(({ href }) => pathname === href || pathname.startsWith(`${href}/`));
  return { items, activeHref: active?.href ?? null };
}

function ThemeToggle() {
  const { resolvedTheme, setTheme } = useTheme();
  return (
    <Button
      variant="ghost"
      size="icon"
      aria-label="Toggle dark mode"
      onClick={() => setTheme(resolvedTheme === "dark" ? "light" : "dark")}
    >
      <Sun aria-hidden className="hidden dark:block" />
      <Moon aria-hidden className="dark:hidden" />
    </Button>
  );
}

export function AppShell({ children }: { children: ReactNode }) {
  const { client, logout } = useAuth();
  const router = useRouter();
  const [open, setOpen] = useState(false);
  const { items, activeHref } = useNavItems();

  function handleLogout() {
    logout();
    router.replace("/login");
  }

  return (
    <div className="flex min-h-dvh flex-col">
      <header className="pointer-events-none fixed inset-x-0 top-3 z-40 flex justify-center px-3 sm:top-6">
        <GlassPanel
          radius="full"
          className="pointer-events-auto flex w-full max-w-5xl items-center gap-1 py-1.5 pr-1.5 pl-2 sm:gap-2 sm:pl-4"
        >
          <Button
            variant="ghost"
            size="icon"
            className="md:hidden"
            aria-label="Open navigation"
            onClick={() => setOpen(true)}
          >
            <Menu aria-hidden />
          </Button>
          <Link
            href="/"
            className="flex shrink-0 items-center gap-2 rounded-full pr-1 text-sm font-semibold tracking-tight focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-ring"
          >
            <ShieldCheck aria-hidden className="size-5 text-emerald-600 dark:text-emerald-300" />
            <span>Larkspur</span>
            <span className="hidden font-normal text-muted-foreground lg:inline">Policy Console</span>
          </Link>
          <PillNav
            items={items}
            activeHref={activeHref}
            layoutId="console-nav-pill"
            label="Main"
            className="ml-2 hidden md:block"
          />
          <div className="ml-auto flex items-center gap-0.5">
            <span
              className={cn(
                "mr-1 rounded-full border px-2 py-0.5 font-mono text-[11px] font-semibold uppercase",
                client.mode === "mock"
                  ? "border-violet-500/40 text-violet-700 dark:border-violet-300/30 dark:text-violet-200"
                  : "border-emerald-500/40 text-emerald-700 dark:border-emerald-300/30 dark:text-emerald-200",
              )}
              title={client.mode === "mock" ? "Using in-memory demo data" : "Connected to the live API"}
            >
              {client.mode}
            </span>
            <ThemeToggle />
            <Button variant="ghost" size="icon" aria-label="Log out" onClick={handleLogout}>
              <LogOut aria-hidden />
            </Button>
          </div>
        </GlassPanel>
      </header>

      <Sheet open={open} onOpenChange={setOpen}>
        <SheetContent side="left" className="w-72">
          <SheetHeader>
            <SheetTitle>Navigation</SheetTitle>
          </SheetHeader>
          <div className="px-3">
            <PillNav
              items={items}
              activeHref={activeHref}
              layoutId="console-nav-pill-mobile"
              label="Main"
              vertical
              onNavigate={() => setOpen(false)}
            />
          </div>
        </SheetContent>
      </Sheet>

      <main id="main" className="mx-auto flex w-full max-w-7xl flex-1 flex-col px-3 pt-20 pb-10 sm:px-6 sm:pt-28">
        <PageTransition>{children}</PageTransition>
      </main>
    </div>
  );
}
