"use client";

import type { ReactNode } from "react";
import { m, useReducedMotion } from "framer-motion";
import { Tabs, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { layoutTransition } from "@/lib/motion";
import { cn } from "@/lib/utils";

/** Glass segmented control on top of base-ui Tabs, with a spring-animated active pill. */
export function SegmentedTabs<T extends string>({
  value,
  onValueChange,
  items,
  layoutId,
  className,
}: {
  value: T;
  onValueChange: (value: T) => void;
  items: ReadonlyArray<{ value: T; label: ReactNode }>;
  layoutId: string;
  className?: string;
}) {
  const reduced = useReducedMotion() ?? false;
  return (
    <Tabs value={value} onValueChange={(v) => onValueChange(v as T)} className={className}>
      <TabsList className="h-auto rounded-full border border-glass-edge bg-glass-inset p-1">
        {items.map((item) => (
          <TabsTrigger
            key={item.value}
            value={item.value}
            className={cn(
              "relative isolate h-auto rounded-full px-3.5 py-1.5",
              "data-active:border-transparent data-active:bg-transparent data-active:shadow-none dark:data-active:border-transparent dark:data-active:bg-transparent",
            )}
          >
            {value === item.value && (
              <m.span
                layoutId={layoutId}
                aria-hidden
                data-slot="tab-indicator"
                transition={layoutTransition(reduced)}
                className="absolute inset-0 -z-10 rounded-full border border-glass-edge bg-background/70 shadow-glass-sm dark:bg-white/[0.12]"
              />
            )}
            {item.label}
          </TabsTrigger>
        ))}
      </TabsList>
    </Tabs>
  );
}
