"use client";

import Link from "next/link";
import { m } from "framer-motion";
import type { LucideIcon } from "lucide-react";
import { SPRING } from "@/lib/motion";
import { cn } from "@/lib/utils";

export interface DockItem {
  href: string;
  label: string;
  icon: LucideIcon;
  external?: boolean;
}

const ITEM =
  "flex size-11 items-center justify-center rounded-2xl border border-glass-edge bg-glass-inset text-muted-foreground transition-colors hover:text-foreground focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-ring";

/** Floating glass dock; icons lift and scale on hover/focus (transforms are dropped under reduced motion). */
export function Dock({ items, label, className }: { items: readonly DockItem[]; label: string; className?: string }) {
  return (
    <nav aria-label={label} className={className}>
      <ul
        data-slot="dock"
        className="flex items-end gap-2 rounded-[1.75rem] border border-glass-edge bg-glass px-2.5 py-2.5 shadow-glass backdrop-blur-2xl backdrop-saturate-150"
      >
        {items.map(({ href, label: text, icon: Icon, external }) => (
          <li key={href} className="group/dock relative">
            <m.div whileHover={{ scale: 1.18, y: -6 }} whileTap={{ scale: 0.95 }} transition={SPRING}>
              {external ? (
                <a href={href} target="_blank" rel="noreferrer" aria-label={`${text} (opens in a new tab)`} className={ITEM}>
                  <Icon aria-hidden className="size-5" />
                </a>
              ) : (
                <Link href={href} aria-label={text} className={ITEM}>
                  <Icon aria-hidden className="size-5" />
                </Link>
              )}
            </m.div>
            <span
              aria-hidden
              className={cn(
                "pointer-events-none absolute -top-9 left-1/2 -translate-x-1/2 rounded-full border border-glass-edge bg-popover px-2.5 py-1 text-xs whitespace-nowrap text-popover-foreground opacity-0 shadow-glass-sm transition-opacity",
                "group-hover/dock:opacity-100 group-focus-within/dock:opacity-100",
              )}
            >
              {text}
            </span>
          </li>
        ))}
      </ul>
    </nav>
  );
}
