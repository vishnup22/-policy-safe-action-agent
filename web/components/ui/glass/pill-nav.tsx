"use client";

import type { ReactNode } from "react";
import Link from "next/link";
import { m, useReducedMotion } from "framer-motion";
import type { LucideIcon } from "lucide-react";
import { layoutTransition } from "@/lib/motion";
import { cn } from "@/lib/utils";

export interface PillNavItem {
  href: string;
  label: string;
  icon?: LucideIcon;
  /** Rendered after the label (e.g. a count). */
  badge?: ReactNode;
}

/**
 * Row of links with a single active pill that springs between items via a
 * shared `layoutId`.
 */
export function PillNav({
  items,
  activeHref,
  layoutId,
  label,
  current = "page",
  onNavigate,
  vertical = false,
  className,
}: {
  items: readonly PillNavItem[];
  activeHref: string | null;
  layoutId: string;
  label: string;
  /** `aria-current` value for the active item: "page" for routes, "location" for in-page anchors. */
  current?: "page" | "location";
  onNavigate?: (href: string) => void;
  vertical?: boolean;
  className?: string;
}) {
  const reduced = useReducedMotion() ?? false;
  return (
    <nav aria-label={label} className={className}>
      <ul className={cn("flex gap-1", vertical ? "flex-col" : "items-center")}>
        {items.map(({ href, label: text, icon: Icon, badge }) => {
          const active = href === activeHref;
          return (
            <li key={href} className="relative isolate">
              {active && (
                <m.span
                  layoutId={layoutId}
                  aria-hidden
                  data-slot="pill-indicator"
                  transition={layoutTransition(reduced)}
                  className="absolute inset-0 -z-10 rounded-full bg-foreground/[0.08] shadow-[inset_0_1px_0_0_var(--glass-highlight)] dark:bg-white/[0.12]"
                />
              )}
              <Link
                href={href}
                aria-current={active ? current : undefined}
                onClick={() => onNavigate?.(href)}
                className={cn(
                  "flex items-center gap-1.5 rounded-full px-3.5 py-1.5 text-sm font-medium whitespace-nowrap text-muted-foreground transition-colors hover:text-foreground focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-ring",
                  active && "text-foreground",
                )}
              >
                {Icon && <Icon aria-hidden className="size-4" />}
                {text}
                {badge}
              </Link>
            </li>
          );
        })}
      </ul>
    </nav>
  );
}
