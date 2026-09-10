"use client";

import { createContext, useCallback, useContext, useEffect, useMemo, useState } from "react";
import type { ReactNode } from "react";
import { API_BASE, api } from "./api";
import { clearTokens, getRefreshToken, refreshAccessToken, setTokens } from "./auth-store";
import type { TokenResponse, User } from "./types";

/*
 * Auth state.
 *
 * Sign-in supports two methods, both on an allowlisted organisation domain: Google
 * (`loginWithGoogle`) and email/password (`loginWithPassword`, `register`). Neither is
 * required — Google is optional at the platform level, and a manual account works
 * whether or not Google is configured. An account is born EMPLOYEE unless an
 * administrator pre-provisioned a higher role for that address, regardless of which
 * method created it.
 *
 * On mount the access token is always absent — it lives in memory and a reload clears
 * it. If a refresh token is persisted we exchange it before deciding the user is signed
 * out, so `status` stays "loading" until that resolves. Rendering a signed-out shell
 * first would flash the login screen at every refresh.
 */

type Status = "loading" | "authenticated" | "anonymous";

interface AuthValue {
  status: Status;
  user: User | null;
  loginWithGoogle: (idToken: string) => Promise<void>;
  loginWithPassword: (email: string, password: string) => Promise<void>;
  register: (email: string, password: string, fullName: string) => Promise<void>;
  logout: () => Promise<void>;
  refreshUser: () => Promise<void>;
}

const AuthContext = createContext<AuthValue | null>(null);

export function AuthProvider({ children }: { children: ReactNode }) {
  const [status, setStatus] = useState<Status>("loading");
  const [user, setUser] = useState<User | null>(null);

  const loadUser = useCallback(async () => {
    const me = await api.get<User>("/auth/me");
    setUser(me);
    setStatus("authenticated");
  }, []);

  useEffect(() => {
    let cancelled = false;

    (async () => {
      if (!getRefreshToken()) {
        if (!cancelled) setStatus("anonymous");
        return;
      }
      const token = await refreshAccessToken(API_BASE);
      if (cancelled) return;
      if (!token) {
        setStatus("anonymous");
        return;
      }
      try {
        await loadUser();
      } catch {
        if (!cancelled) {
          clearTokens();
          setStatus("anonymous");
        }
      }
    })();

    return () => {
      cancelled = true;
    };
  }, [loadUser]);

  const loginWithGoogle = useCallback(
    async (idToken: string) => {
      const tokens = await api.public.post<TokenResponse>("/auth/google", { id_token: idToken });
      setTokens(tokens);
      await loadUser();
    },
    [loadUser],
  );

  const loginWithPassword = useCallback(
    async (email: string, password: string) => {
      const tokens = await api.public.post<TokenResponse>("/auth/login", { email, password });
      setTokens(tokens);
      await loadUser();
    },
    [loadUser],
  );

  const register = useCallback(
    async (email: string, password: string, fullName: string) => {
      const tokens = await api.public.post<TokenResponse>("/auth/register", {
        email,
        password,
        full_name: fullName,
      });
      setTokens(tokens);
      await loadUser();
    },
    [loadUser],
  );

  const logout = useCallback(async () => {
    const refresh = getRefreshToken();
    try {
      // keepalive: the redirect that follows tears the page down, and without it the
      // browser cancels the socket mid-flight. The server had been processing it anyway,
      // but a security-relevant revoke should not depend on winning that race.
      if (refresh) {
        await api.public.post<void>("/auth/logout", { refresh_token: refresh }, { keepalive: true });
      }
    } catch {
      // A failed revoke must not strand the user in a signed-in shell.
    } finally {
      clearTokens();
      setUser(null);
      setStatus("anonymous");
    }
  }, []);

  const value = useMemo<AuthValue>(
    () => ({
      status,
      user,
      loginWithGoogle,
      loginWithPassword,
      register,
      logout,
      refreshUser: loadUser,
    }),
    [status, user, loginWithGoogle, loginWithPassword, register, logout, loadUser],
  );

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth(): AuthValue {
  const ctx = useContext(AuthContext);
  if (!ctx) throw new Error("useAuth must be used inside <AuthProvider>");
  return ctx;
}
