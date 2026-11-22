"use client";

import { useEffect, useState, type FormEvent } from "react";
import { useRouter, useSearchParams } from "next/navigation";
import { ShieldCheck } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { ApiError, MOCK_PASSCODE } from "@/lib/api";
import { useAuth } from "@/lib/auth";

function safeNext(raw: string | null): string {
  return raw && raw.startsWith("/") && !raw.startsWith("//") ? raw : "/chat";
}

export function LoginForm() {
  const { client, token, ready, login } = useAuth();
  const router = useRouter();
  const next = safeNext(useSearchParams().get("next"));
  const [passcode, setPasscode] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);

  useEffect(() => {
    if (ready && token) router.replace(next);
  }, [ready, token, next, router]);

  async function onSubmit(e: FormEvent) {
    e.preventDefault();
    setError(null);
    setSubmitting(true);
    try {
      await login(passcode);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Sign-in failed. Try again.");
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <Card className="w-full max-w-sm">
      <CardHeader>
        <div className="mb-2 flex size-10 items-center justify-center rounded-xl bg-emerald-600/10">
          <ShieldCheck aria-hidden className="size-5 text-emerald-700 dark:text-emerald-400" />
        </div>
        <CardTitle className="text-lg">Larkspur Policy Console</CardTitle>
        <CardDescription>Enter the demo passcode to continue.</CardDescription>
      </CardHeader>
      <CardContent>
        <form onSubmit={onSubmit} className="space-y-4" noValidate>
          <div className="space-y-1.5">
            <Label htmlFor="passcode">Passcode</Label>
            <Input
              id="passcode"
              type="password"
              autoComplete="current-password"
              autoFocus
              required
              value={passcode}
              onChange={(e) => setPasscode(e.target.value)}
              aria-invalid={error ? true : undefined}
              aria-describedby={error ? "passcode-error" : undefined}
            />
            {error && (
              <p id="passcode-error" role="alert" className="text-sm text-destructive">
                {error}
              </p>
            )}
          </div>
          <Button type="submit" className="w-full" disabled={submitting || !passcode}>
            {submitting ? "Signing in…" : "Sign in"}
          </Button>
          {client.mode === "mock" && (
            <p className="text-xs text-muted-foreground">
              Mock mode — passcode is <code className="font-mono">{MOCK_PASSCODE}</code>.
            </p>
          )}
        </form>
      </CardContent>
    </Card>
  );
}
