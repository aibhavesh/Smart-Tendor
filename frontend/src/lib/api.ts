import { clearTokens, getAccessToken, refreshAccessToken } from "./auth-store";

/*
 * Typed fetch client with transparent refresh-on-401.
 *
 * A 15-minute access token means expiry is routine, not exceptional, so it must never
 * surface to the user. One retry only: if the refreshed token also 401s, the session is
 * genuinely finished and pretending otherwise would loop.
 */

/*
 * API base URL resolution.
 *
 * NEXT_PUBLIC_* values are inlined into the browser bundle by `next build`, so this is
 * frozen into whatever artifact was built (see the Next.js env-var docs). The build must
 * therefore never *depend* on the variable being set. It used to: this module threw at
 * evaluation time when it was missing, and because `api.ts` is imported by `telemetry.ts`
 * -> `States.tsx` -> `RequireAuth.tsx` -> the page modules, that single throw surfaced as
 * "Error occurred prerendering page /_not-found" and failed the entire build. One forgotten
 * CI build variable became an undeployable commit with an error that pointed nowhere near
 * the actual cause.
 *
 * Resolution order:
 *   1. NEXT_PUBLIC_API_BASE_URL - authoritative. Set in every real deployment (Docker
 *      Compose, native dev, Netlify), so existing behaviour is unchanged.
 *   2. A localStorage override, consulted ONLY when step 1 found nothing. This is the escape
 *      hatch for a URL that was unknown or wrong at build time: an already-deployed site can
 *      be pointed at the real API from the browser with no rebuild. Because it is only read
 *      when the env var is absent, it can never shadow a correctly configured deployment.
 *   3. "" - same-origin, for hosting the API behind a reverse proxy on the same host.
 *
 * A missing value is then reported as an ordinary request error (see requireApiBase) so a
 * misconfigured site renders and explains itself instead of crashing the build.
 */

/** localStorage key for the build-time-override escape hatch. See step 2 above. */
export const RUNTIME_API_BASE_KEY = "ti.apiBase";

function readRuntimeOverride(): string | null {
  // Server-side prerender has no window and no storage; the env var covers that path.
  if (typeof window === "undefined") return null;
  try {
    return window.localStorage.getItem(RUNTIME_API_BASE_KEY)?.trim() || null;
  } catch {
    // Storage disabled (private mode, blocked cookies). Fall through to same-origin.
    return null;
  }
}

const rawBuildTimeApiBase = process.env.NEXT_PUBLIC_API_BASE_URL?.trim() || null;

function normaliseApiBase(value: string | null): string | null {
  // Trim a trailing slash so every request below has exactly one path separator.
  const base = (value ?? "").replace(/\/+$/, "");
  if (!base) return null;

  try {
    const url = new URL(base);
    if (url.protocol !== "http:" && url.protocol !== "https:") return null;
    const isLocalDockerGateway =
      url.protocol === "http:" &&
      url.hostname === "localhost" &&
      url.port === "8080" &&
      url.pathname === "/api";

    // Docker Compose routes browser requests through Nginx at /api and strips that
    // prefix before forwarding to FastAPI. Railway exposes FastAPI directly, where
    // /api/auth/register does not exist. Tolerate a copied Docker suffix for a
    // deployed API without changing the intentionally proxied local configuration.
    if (!isLocalDockerGateway && url.pathname === "/api") return url.origin;
  } catch {
    // A literal variable name would otherwise become a same-origin browser request.
    return null;
  }

  return base;
}

const buildTimeApiBase = normaliseApiBase(rawBuildTimeApiBase);
const runtimeApiBase = normaliseApiBase(readRuntimeOverride());
const hasInvalidBuildTimeApiBase = Boolean(rawBuildTimeApiBase && !buildTimeApiBase);

export const API_BASE = buildTimeApiBase ?? runtimeApiBase ?? "";

/**
 * Refuse to issue a request when no API base was resolved.
 *
 * Throwing here (rather than at module load) keeps `next build` green and produces an error
 * the user can act on. The same-origin fallback is allowed, so this only fires when there is
 * genuinely nothing to call.
 */
function requireApiBase(): string {
  if (API_BASE) return API_BASE;
  if (hasInvalidBuildTimeApiBase) {
    throw new ApiError(
      0,
      "The deployed API address is invalid. Set NEXT_PUBLIC_API_BASE_URL in Netlify to the full Railway API origin, then trigger a new build.",
    );
  }
  throw new ApiError(
    0,
    "The API address is not configured. Set NEXT_PUBLIC_API_BASE_URL in your build " +
      `environment and redeploy, or set localStorage.${RUNTIME_API_BASE_KEY} to the API ` +
      "origin (for example https://your-api.onrender.com) to fix this without rebuilding.",
  );
}

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

  return fetch(`${requireApiBase()}${path}`, {
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
