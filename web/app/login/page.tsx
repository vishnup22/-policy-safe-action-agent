import type { Metadata } from "next";
import { Suspense } from "react";
import Link from "next/link";
import { ArrowLeft } from "lucide-react";
import { buttonVariants } from "@/components/ui/button";
import { LoginForm } from "./login-form";

export const metadata: Metadata = { title: "Sign in" };

export default function LoginPage() {
  return (
    <main id="main" className="flex flex-1 flex-col items-center justify-center gap-6 p-4">
      <Suspense>
        <LoginForm />
      </Suspense>
      <Link href="/" className={buttonVariants({ variant: "ghost", size: "sm" })}>
        <ArrowLeft aria-hidden /> Back to overview
      </Link>
    </main>
  );
}
