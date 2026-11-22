"use client";

import { useEffect, type ReactNode } from "react";
import { usePathname, useRouter } from "next/navigation";
import { useAuth } from "@/lib/auth";

export function AuthGuard({ children }: { children: ReactNode }) {
  const { ready, token } = useAuth();
  const router = useRouter();
  const pathname = usePathname();

  useEffect(() => {
    if (ready && !token) router.replace(`/login?next=${encodeURIComponent(pathname)}`);
  }, [ready, token, pathname, router]);

  if (!ready || !token) {
    return (
      <div className="flex flex-1 items-center justify-center p-8 text-sm text-muted-foreground" role="status">
        Checking session…
      </div>
    );
  }
  return <>{children}</>;
}
