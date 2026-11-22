"use client";

import type { ReactNode } from "react";
import { usePathname } from "next/navigation";
import { m, useReducedMotion } from "framer-motion";
import { pageMotion } from "@/lib/motion";

/** Spring enter on every console route change; a plain fade under reduced motion. */
export function PageTransition({ children }: { children: ReactNode }) {
  const pathname = usePathname();
  const motion = pageMotion(useReducedMotion() ?? false);
  return (
    <m.div key={pathname} {...motion} className="flex flex-1 flex-col">
      {children}
    </m.div>
  );
}
