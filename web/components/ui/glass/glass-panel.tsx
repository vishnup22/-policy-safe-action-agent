"use client";

import type { HTMLAttributes, PointerEvent, ReactNode } from "react";
import { cva, type VariantProps } from "class-variance-authority";
import { cn } from "@/lib/utils";

/**
 * Only `default` and `strong` use backdrop-filter. Nest `inset` inside them so no
 * point on screen stacks more than three blur layers (nav + panel + sheet).
 */
export const glassVariants = cva(
  "group/glass relative isolate border transition-[border-color,background-color] duration-300",
  {
    variants: {
      variant: {
        default: "border-glass-edge bg-glass shadow-glass backdrop-blur-2xl backdrop-saturate-150",
        strong: "border-glass-edge bg-glass-strong shadow-glass backdrop-blur-2xl backdrop-saturate-150",
        inset: "border-glass-edge bg-glass-inset",
      },
      radius: {
        "3xl": "rounded-3xl",
        "2xl": "rounded-2xl",
        xl: "rounded-xl",
        full: "rounded-full",
      },
      interactive: {
        true: "hover:border-glass-edge-hover",
        false: "",
      },
    },
    defaultVariants: { variant: "default", radius: "3xl", interactive: false },
  },
);

type Tag = "div" | "section" | "article" | "aside" | "figure" | "header" | "li" | "nav";

export interface GlassPanelProps
  extends HTMLAttributes<HTMLElement>,
    VariantProps<typeof glassVariants> {
  as?: Tag;
  /** Cursor-tracking highlight; implies `interactive`. */
  spotlight?: boolean;
  children?: ReactNode;
}

function trackPointer(e: PointerEvent<HTMLElement>) {
  const el = e.currentTarget;
  const rect = el.getBoundingClientRect();
  el.style.setProperty("--spot-x", `${e.clientX - rect.left}px`);
  el.style.setProperty("--spot-y", `${e.clientY - rect.top}px`);
}

export function GlassPanel({
  as: Comp = "div",
  variant,
  radius,
  interactive,
  spotlight = false,
  className,
  children,
  onPointerMove,
  ...props
}: GlassPanelProps) {
  return (
    <Comp
      data-slot="glass"
      data-variant={variant ?? "default"}
      className={cn(glassVariants({ variant, radius, interactive: interactive ?? spotlight }), className)}
      onPointerMove={
        spotlight
          ? (e: PointerEvent<HTMLElement>) => {
              trackPointer(e);
              onPointerMove?.(e);
            }
          : onPointerMove
      }
      {...props}
    >
      {spotlight && (
        <span
          aria-hidden
          data-slot="glass-spotlight"
          className="pointer-events-none absolute inset-0 -z-10 rounded-[inherit] opacity-0 transition-opacity duration-300 group-hover/glass:opacity-100"
          style={{
            background:
              "radial-gradient(420px circle at var(--spot-x, 50%) var(--spot-y, 0%), var(--spotlight), transparent 45%)",
          }}
        />
      )}
      {children}
    </Comp>
  );
}
