import type { ApiClient, ApiMode } from "./client";
import { LiveClient } from "./live-client";
import { DEFAULT_MOCK_PASSCODE, MockClient } from "./mock-client";

export * from "./client";
export type * from "./types";

export const API_MODE: ApiMode = process.env.NEXT_PUBLIC_API_MODE === "live" ? "live" : "mock";
export const API_URL = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";
export const MOCK_PASSCODE = process.env.NEXT_PUBLIC_MOCK_PASSCODE || DEFAULT_MOCK_PASSCODE;

export function createApiClient(getToken: () => string | null, mode: ApiMode = API_MODE): ApiClient {
  if (mode === "live") return new LiveClient({ baseUrl: API_URL, getToken });
  return new MockClient({ passcode: MOCK_PASSCODE });
}
