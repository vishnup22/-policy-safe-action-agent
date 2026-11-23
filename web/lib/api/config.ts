import type { ApiClient, ApiMode } from "./client";
import { LazyClient } from "./lazy-client";

export const DEFAULT_MOCK_PASSCODE = "larkspur-demo";

export const API_MODE: ApiMode = process.env.NEXT_PUBLIC_API_MODE === "live" ? "live" : "mock";
export const API_URL = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";
export const MOCK_PASSCODE = process.env.NEXT_PUBLIC_MOCK_PASSCODE || DEFAULT_MOCK_PASSCODE;

export function createApiClient(getToken: () => string | null, mode: ApiMode = API_MODE): ApiClient {
  if (mode === "live") {
    return new LazyClient("live", async () => {
      const { LiveClient } = await import("./live-client");
      return new LiveClient({ baseUrl: API_URL, getToken });
    });
  }
  return new LazyClient("mock", async () => {
    const { MockClient } = await import("./mock-client");
    return new MockClient({ passcode: MOCK_PASSCODE });
  });
}
