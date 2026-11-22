"use client";

import {
  createContext,
  useCallback,
  useContext,
  useMemo,
  useState,
  useSyncExternalStore,
  type ReactNode,
} from "react";
import { createApiClient, type ApiClient } from "@/lib/api";

const STORAGE_KEY = "psa.session";

interface Session {
  token: string;
  expires_at: string;
}

/**
 * Token store: the in-memory value is authoritative; sessionStorage only lets a
 * reload in the same tab keep the session. Nothing is written to localStorage.
 */
function createTokenStore() {
  let session: Session | null | undefined;
  const listeners = new Set<() => void>();

  function read(): Session | null {
    if (session !== undefined) return session;
    if (typeof window === "undefined") return null;
    try {
      const raw = window.sessionStorage.getItem(STORAGE_KEY);
      const parsed = raw ? (JSON.parse(raw) as Session) : null;
      session = parsed && Date.parse(parsed.expires_at) > Date.now() ? parsed : null;
    } catch {
      session = null;
    }
    return session;
  }

  function write(next: Session | null) {
    session = next;
    if (typeof window !== "undefined") {
      if (next) window.sessionStorage.setItem(STORAGE_KEY, JSON.stringify(next));
      else window.sessionStorage.removeItem(STORAGE_KEY);
    }
    listeners.forEach((l) => l());
  }

  return {
    read,
    write,
    subscribe(listener: () => void) {
      listeners.add(listener);
      return () => listeners.delete(listener);
    },
  };
}

type TokenStore = ReturnType<typeof createTokenStore>;

interface AuthValue {
  client: ApiClient;
  token: string | null;
  /** False during SSR / before the session has been read on the client. */
  ready: boolean;
  login: (passcode: string) => Promise<void>;
  logout: () => void;
}

const AuthContext = createContext<AuthValue | null>(null);

export function AuthProvider({ children, client }: { children: ReactNode; client?: ApiClient }) {
  const [store] = useState<TokenStore>(createTokenStore);
  const [api] = useState<ApiClient>(
    () => client ?? createApiClient(() => store.read()?.token ?? null),
  );

  const session = useSyncExternalStore<Session | null | undefined>(
    store.subscribe,
    store.read,
    () => undefined,
  );
  const ready = session !== undefined;

  const login = useCallback(
    async (passcode: string) => {
      const res = await api.login(passcode);
      store.write({ token: res.token, expires_at: res.expires_at });
    },
    [api, store],
  );

  const logout = useCallback(() => store.write(null), [store]);

  const value = useMemo<AuthValue>(
    () => ({ client: api, token: session?.token ?? null, ready, login, logout }),
    [api, session, ready, login, logout],
  );

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth(): AuthValue {
  const ctx = useContext(AuthContext);
  if (!ctx) throw new Error("useAuth must be used inside <AuthProvider>");
  return ctx;
}

export function useApi(): ApiClient {
  return useAuth().client;
}
