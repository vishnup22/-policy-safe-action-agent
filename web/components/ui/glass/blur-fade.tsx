"use client";

import type { ReactNode } from "react";
import { m, useReducedMotion } from "framer-motion";
import { revealTransition, revealVariants } from "@/lib/motion";

const TAGS = { div: m.div, section: m.section, li: m.li } as const;

/** Scroll-triggered blur-fade (opacity 0 / y 20 / blur 8 → resting state). */
export function BlurFade({
  children,
  delay = 0,
  as = "div",
  className,
  id,
  "aria-labelledby": labelledBy,
}: {
  children: ReactNode;
  delay?: number;
  as?: keyof typeof TAGS;
  className?: string;
  id?: string;
  "aria-labelledby"?: string;
}) {
  const reduced = useReducedMotion() ?? false;
  const Comp = TAGS[as];
  return (
    <Comp
      id={id}
      aria-labelledby={labelledBy}
      data-reveal
      className={className}
      initial="hidden"
      whileInView="visible"
      viewport={{ once: true, margin: "0px 0px -8% 0px" }}
      variants={revealVariants}
      transition={revealTransition(reduced, delay)}
    >
      {children}
    </Comp>
  );
}
