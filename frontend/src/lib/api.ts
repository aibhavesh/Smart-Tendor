import { clearTokens, getAccessToken, refreshAccessToken } from "./auth-store";

/*
 * Typed fetch client with transparent refresh-on-401.
 *
 * A 15-minute access token means expiry is routine, not exceptional, so it must never
 * surface to the user. One retry only: if the refreshed token also 401s, the session is
 * genuinely finished and pretending otherwise would loop.
 */

const configuredApiBase = process.env.NEXT_PUBLIC_API_BASE_URL?.trim();
if (!configuredApiBase) {
  throw new Error(
    "NEXT_PUBLIC_API_BASE_URL is required. Set it before running next dev or next build.",
  );
}

// Trim a trailing slash so every request below has exactly one path separator.
export const API_BASE = configuredApiBase.replace(/\/+$/, "");

export class ApiError extends Error {
  constructor(
    public status: number,
    public detail: string,
  ) {
    super(detail);
    this.name = "ApiError";
  }
}

/**
 * Turn an ApiError into something specific enough to act on.
 *
 * Two things about this API's error map (api/errors.py), both confirmed against a live
 * server rather than read off the plan:
 *
 *   - There is no **400**. The plan's §8 "400 unparsed tender" does not exist.
 *   - **422 is overloaded.** It is FastAPI's request-validation status *and* the mapping
 *     for `DomainValidationError` ("Invalid request."), which is what you get for asking
 *     a tender to analyse before it is parsed. So a 422 may mean "your input was wrong"
 *     or "this record is not at the right stage" — callers that know which should pass a
 *     context override rather than rely on the generic wording below.
 */
export function describeError(error: unknown, context?: Partial<Record<number, string>>): string {
  if (!(error instanceof ApiError)) {
    return "Could not reach the server. Check your connection and try again.";
  }
  const override = context?.[error.status];
  if (override) return override;

  switch (error.status) {
    case 401:
      return "Your session has expired. Please sign in again.";
    case 403:
      return "You do not have permission to do that.";
    case 404:
      return "That record no longer exists.";
    case 409:
      return error.detail || "That conflicts with the current state of the record.";
    case 422:
      return "That could not be processed. Check the values, or the record may not be at the right stage yet.";
    default:
      return error.detail || "Something went wrong. Please try again.";
  }
}

interface RequestOptions {
  method?: string;
  body?: unknown;
  /** false for the public auth endpoints, which must not carry a stale bearer token. */
  auth?: boolean;
  formData?: FormData;
  signal?: AbortSignal;
  /**
   * Ask the browser to finish this request even if the page is being torn down.
   * Used for logout: the revoke must land, and it is issued immediately before the
   * redirect that unmounts the screen.
   */
  keepalive?: boolean;
}

async function send(path: string, opts: RequestOptions, token: string | null): Promise<Response> {
  const headers: Record<string, string> = {};
  if (opts.auth !== false && token) headers.Authorization = `Bearer ${token}`;

  let body: BodyInit | undefined;
  if (opts.formData) {
    // Deliberately no Content-Type: the browser must set the multipart boundary.
    body = opts.formData;
  } else if (opts.body !== undefined) {
    headers["Content-Type"] = "application/json";
    body = JSON.stringify(opts.body);
  }

  return fetch(`${API_BASE}${path}`, {
    method: opts.method ?? "GET",
    headers,
    body,
    signal: opts.signal,
    keepalive: opts.keepalive,
  });
}

export async function apiRequest<T>(path: string, opts: RequestOptions = {}): Promise<T> {
  let response = await send(path, opts, getAccessToken());

  if (response.status === 401 && opts.auth !== false) {
    const refreshed = await refreshAccessToken(API_BASE);
    if (refreshed) {
      response = await send(path, opts, refreshed);
    } else {
      clearTokens();
    }
  }

  if (response.status === 204) return undefined as T;

  const text = await response.text();
  let data: unknown;
  try {
    data = text ? JSON.parse(text) : undefined;
  } catch {
    data = undefined;
  }

  if (!response.ok) {
    const detail =
      (data as { detail?: string } | undefined)?.detail ?? response.statusText ?? "Request failed";
    throw new ApiError(response.status, detail);
  }

  return data as T;
}

/** Build a query string, dropping empty values so the API sees no blank filters. */
export function query(params: Record<string, string | number | undefined | null>): string {
  const search = new URLSearchParams();
  for (const [key, value] of Object.entries(params)) {
    if (value === undefined || value === null || value === "") continue;
    search.set(key, String(value));
  }
  const s = search.toString();
  return s ? `?${s}` : "";
}

export const api = {
  get: <T>(path: string, signal?: AbortSignal) => apiRequest<T>(path, { signal }),
  post: <T>(path: string, body?: unknown) => apiRequest<T>(path, { method: "POST", body }),
  patch: <T>(path: string, body?: unknown) => apiRequest<T>(path, { method: "PATCH", body }),
  del: <T>(path: string) => apiRequest<T>(path, { method: "DELETE" }),
  upload: <T>(path: string, formData: FormData) =>
    apiRequest<T>(path, { method: "POST", formData }),
  /** The three unauthenticated endpoints: Google sign-in, refresh, logout. */
  public: {
    post: <T>(path: string, body?: unknown, options?: { keepalive?: boolean }) =>
      apiRequest<T>(path, { method: "POST", body, auth: false, ...options }),
  },
};
