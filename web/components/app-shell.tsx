"use client";

import { useState, type ReactNode } from "react";
import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { useTheme } from "next-themes";
import {
  ClipboardCheck,
  FlaskConical,
  History,
  LogOut,
  Menu,
  MessageSquare,
  Moon,
  ShieldCheck,
  Sun,
} from "lucide-react";
import { Button } from "@/components/ui/button";
import { Sheet, SheetContent, SheetHeader, SheetTitle } from "@/components/ui/sheet";
import { useApprovals } from "@/lib/api/queries";
import { useAuth } from "@/lib/auth";
import { cn } from "@/lib/utils";

const NAV = [
  { href: "/chat", label: "Chat", icon: MessageSquare },
  { href: "/conversations", label: "Conversations", icon: History },
  { href: "/approvals", label: "Approvals", icon: ClipboardCheck },
  { href: "/evals", label: "Evals", icon: FlaskConical },
] as const;

function NavLinks({ onNavigate, vertical = false }: { onNavigate?: () => void; vertical?: boolean }) {
  const pathname = usePathname();
  const { data } = useApprovals("pending");
  const pending = data?.items.length ?? 0;
  return (
    <nav aria-label="Main" className={cn("flex gap-1", vertical && "flex-col")}>
      {NAV.map(({ href, label, icon: Icon }) => {
        const active = pathname === href || pathname.startsWith(`${href}/`);
        return (
          <Link
            key={href}
            href={href}
            onClick={onNavigate}
            aria-current={active ? "page" : undefined}
            className={cn(
              "flex items-center gap-2 rounded-lg px-3 py-1.5 text-sm font-medium text-muted-foreground transition-colors hover:bg-muted hover:text-foreground focus-visible:outline-2 focus-visible:outline-ring",
              active && "bg-muted text-foreground",
            )}
          >
            <Icon aria-hidden className="size-4" />
            {label}
            {href === "/approvals" && pending > 0 && (
              <span className="ml-auto rounded-full bg-amber-500 px-1.5 text-[11px] leading-5 font-semibold text-white tabular-nums">
                {pending}
                <span className="sr-only"> pending</span>
              </span>
            )}
          </Link>
        );
      })}
    </nav>
  );
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

  function handleLogout() {
    logout();
    router.replace("/login");
  }

  return (
    <div className="flex min-h-dvh flex-col">
      <header className="sticky top-0 z-40 border-b bg-background/90 backdrop-blur supports-backdrop-filter:bg-background/70">
        <div className="mx-auto flex h-14 max-w-7xl items-center gap-3 px-3 sm:px-6">
          <Button
            variant="ghost"
            size="icon"
            className="md:hidden"
            aria-label="Open navigation"
            onClick={() => setOpen(true)}
          >
            <Menu aria-hidden />
          </Button>
          <Link href="/chat" className="flex items-center gap-2 font-semibold tracking-tight">
            <ShieldCheck aria-hidden className="size-5 text-emerald-600 dark:text-emerald-400" />
            <span className="hidden sm:inline">Larkspur</span>
            <span className="text-muted-foreground font-normal">Policy Console</span>
          </Link>
          <div className="ml-4 hidden md:block">
            <NavLinks />
          </div>
          <div className="ml-auto flex items-center gap-1">
            <span
              className={cn(
                "rounded-md border px-1.5 py-0.5 font-mono text-[11px] font-semibold uppercase",
                client.mode === "mock"
                  ? "border-violet-500/40 text-violet-700 dark:text-violet-300"
                  : "border-emerald-500/40 text-emerald-700 dark:text-emerald-300",
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
        </div>
      </header>

      <Sheet open={open} onOpenChange={setOpen}>
        <SheetContent side="left" className="w-72">
          <SheetHeader>
            <SheetTitle>Navigation</SheetTitle>
          </SheetHeader>
          <div className="px-3">
            <NavLinks vertical onNavigate={() => setOpen(false)} />
          </div>
        </SheetContent>
      </Sheet>

      <main id="main" className="mx-auto flex w-full max-w-7xl flex-1 flex-col px-3 py-4 sm:px-6 sm:py-6">
        {children}
      </main>
    </div>
  );
}
