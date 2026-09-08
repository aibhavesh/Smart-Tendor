import type { TokenResponse } from "./types";

/*
 * Token storage.
 *
 * The access token lives in memory only — it is short-lived (15 minutes) and keeping it
 * out of storage reduces the XSS blast radius. The refresh token is persisted so a
 * session survives a reload; losing it only costs a re-login.
 */

const REFRESH_KEY = "ti.refresh";

let accessToken: string | null = null;
let refreshInFlight: Promise<string | null> | null = null;

export function getAccessToken(): string | null {
  return accessToken;
}

export function getRefreshToken(): string | null {
  if (typeof window === "undefined") return null;
  return window.localStorage.getItem(REFRESH_KEY);
}

export function setTokens(tokens: TokenResponse): void {
  accessToken = tokens.access_token;
  if (typeof window !== "undefined") {
    window.localStorage.setItem(REFRESH_KEY, tokens.refresh_token);
  }
}

export function clearTokens(): void {
  accessToken = null;
  refreshInFlight = null;
  if (typeof window !== "undefined") {
    window.localStorage.removeItem(REFRESH_KEY);
  }
}

/**
 * Exchange the refresh token for a new pair.
 *
 * Deduplicated: several requests can 401 at once, and each must not fire its own
 * refresh — the first would rotate the token and the rest would fail with a token the
 * server has already invalidated.
 */
export function refreshAccessToken(apiBase: string): Promise<string | null> {
  if (refreshInFlight) return refreshInFlight;

  const refresh = getRefreshToken();
  if (!refresh) return Promise.resolve(null);

  refreshInFlight = (async () => {
    try {
      const res = await fetch(`${apiBase}/auth/refresh`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ refresh_token: refresh }),
      });
      if (!res.ok) {
        clearTokens();
        return null;
      }
      const tokens = (await res.json()) as TokenResponse;
      setTokens(tokens);
      return tokens.access_token;
    } catch {
      clearTokens();
      return null;
    } finally {
      refreshInFlight = null;
    }
  })();

  return refreshInFlight;
}
