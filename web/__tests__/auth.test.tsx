import { useState } from "react";
import { QueryClient, QueryClientProvider, useQuery } from "@tanstack/react-query";
import { act, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it } from "vitest";
import { Providers } from "@/components/providers";
import { ApiError } from "@/lib/api";
import { MockClient } from "@/lib/api/mock-client";
import { AuthProvider, notifyUnauthorized, useAuth } from "@/lib/auth";

function Probe({ passcode }: { passcode: string }) {
  const { token, login, logout } = useAuth();
  const [error, setError] = useState<string | null>(null);
  return (
    <div>
      <p>{token ? `signed-in:${token}` : "signed-out"}</p>
      {error && <p role="alert">{error}</p>}
      <button onClick={() => login(passcode).catch((e: Error) => setError(e.message))}>login</button>
      <button onClick={logout}>logout</button>
    </div>
  );
}

function renderProbe(passcode: string) {
  render(
    <AuthProvider client={new MockClient({ latencyMs: [0, 0] })}>
      <Probe passcode={passcode} />
    </AuthProvider>,
  );
  return userEvent.setup();
}

describe("AuthProvider", () => {
  it("keeps the token in memory + sessionStorage and clears it on logout", async () => {
    const user = renderProbe("larkspur-demo");
    expect(screen.getByText("signed-out")).toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: "login" }));
    const status = await screen.findByText(/^signed-in:/);
    const token = status.textContent!.replace("signed-in:", "");
    expect(window.sessionStorage.getItem("psa.session")).toContain(token);
    expect(window.localStorage.length).toBe(0);

    await user.click(screen.getByRole("button", { name: "logout" }));
    expect(screen.getByText("signed-out")).toBeInTheDocument();
    expect(window.sessionStorage.getItem("psa.session")).toBeNull();
  });

  it("surfaces a bad passcode and stays signed out", async () => {
    const user = renderProbe("wrong");
    await user.click(screen.getByRole("button", { name: "login" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("That passcode isn't right.");
    expect(screen.getByText("signed-out")).toBeInTheDocument();
  });
});

describe("401 handling", () => {
  function UnauthorizedProbe() {
    const { token, sessionExpired } = useAuth();
    const { error } = useQuery({
      queryKey: ["probe", token],
      queryFn: () => Promise.reject(new ApiError(401, "UNAUTHORIZED", "Token expired")),
      enabled: !!token,
    });
    return (
      <p>
        {token ? "signed-in" : "signed-out"} · {sessionExpired ? "expired" : "fresh"} · {error ? "errored" : "ok"}
      </p>
    );
  }

  it("a 401 from any query drops the session and flags it as expired", async () => {
    window.sessionStorage.setItem(
      "psa.session",
      JSON.stringify({ token: "tok_old", expires_at: new Date(Date.now() + 3_600_000).toISOString() }),
    );
    render(
      <Providers client={new MockClient({ latencyMs: [0, 0] })}>
        <UnauthorizedProbe />
      </Providers>,
    );
    expect(await screen.findByText(/signed-out · expired/)).toBeInTheDocument();
    expect(window.sessionStorage.getItem("psa.session")).toBeNull();
  });

  it("ignores 401s when nobody is signed in", () => {
    render(
      <QueryClientProvider client={new QueryClient()}>
        <AuthProvider client={new MockClient({ latencyMs: [0, 0] })}>
          <UnauthorizedProbe />
        </AuthProvider>
      </QueryClientProvider>,
    );
    act(() => notifyUnauthorized());
    expect(screen.getByText(/signed-out · fresh/)).toBeInTheDocument();
  });
});
