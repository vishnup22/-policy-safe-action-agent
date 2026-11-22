import { useState } from "react";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it } from "vitest";
import { MockClient } from "@/lib/api/mock-client";
import { AuthProvider, useAuth } from "@/lib/auth";

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
