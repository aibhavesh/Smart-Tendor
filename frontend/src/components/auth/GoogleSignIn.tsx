"use client";

import { useEffect, useRef, useState } from "react";
import { useAuth } from "@/lib/auth";
import { ApiError, describeError } from "@/lib/api";

/*
 * Google sign-in — one of two ways into this application, alongside the
 * email/password form that sits beside it on /login and /register.
 *
 * `POST /auth/google` verifies the id_token against `google_client_id`, checks the
 * address (and Google's `hd` claim, when present) against the allowed organisation
 * domains, links it to an existing account by email, or creates a new EMPLOYEE. The
 * frontend needs the *same* client ID to obtain that token.
 *
 * Google is optional at the platform level, so this fails soft: with no
 * NEXT_PUBLIC_GOOGLE_CLIENT_ID configured, or if the Google script cannot load
 * (an extension, a content blocker, no network), the component renders
 * nothing rather than an error banner — the email/password form beside it is
 * a complete way to sign in on its own.
 */

const CLIENT_ID = process.env.NEXT_PUBLIC_GOOGLE_CLIENT_ID;
const GSI_SRC = "https://accounts.google.com/gsi/client";

interface GoogleCredentialResponse {
  credential?: string;
}

interface GoogleIdentity {
  accounts: {
    id: {
      initialize: (config: {
        client_id: string;
        callback: (response: GoogleCredentialResponse) => void;
        use_fedcm_for_button?: boolean;
      }) => void;
      renderButton: (parent: HTMLElement, options: Record<string, unknown>) => void;
    };
  };
}

/** Loaded once per document — both /login and /register mount this component. */
let scriptPromise: Promise<GoogleIdentity> | null = null;

function loadGsi(): Promise<GoogleIdentity> {
  if (scriptPromise) return scriptPromise;

  scriptPromise = new Promise<GoogleIdentity>((resolve, reject) => {
    const win = window as unknown as { google?: GoogleIdentity };
    if (win.google?.accounts?.id) {
      resolve(win.google);
      return;
    }

    const existing = document.querySelector<HTMLScriptElement>(`script[src="${GSI_SRC}"]`);
    const script = existing ?? document.createElement("script");

    const onLoad = () => {
      const g = (window as unknown as { google?: GoogleIdentity }).google;
      if (g?.accounts?.id) resolve(g);
      else reject(new Error("Google Identity Services loaded but did not initialise."));
    };

    script.addEventListener("load", onLoad, { once: true });
    script.addEventListener(
      "error",
      () => {
        // Let a later attempt retry rather than caching the rejection forever. The dead
        // node has to go with it: left in place, the retry adopts it as `existing` and
        // waits on a "load" that already fired, so the promise would never settle.
        script.remove();
        scriptPromise = null;
        reject(new Error("Could not load Google Identity Services."));
      },
      { once: true },
    );

    if (!existing) {
      script.src = GSI_SRC;
      script.async = true;
      script.defer = true;
      document.head.appendChild(script);
    }
  });

  return scriptPromise;
}

/*
 * Sign-in rejections need to be told apart, and the status code alone cannot do it:
 * a refused domain and a deactivated account are both 403. The server's own wording
 * distinguishes them clearly, so it is passed through and then acted on — one of these
 * is a "you will never get in with this address", the other is "ask an administrator".
 * Getting them the wrong way round sends people to the wrong place.
 */
function describeSignInError(err: unknown): string {
  if (err instanceof ApiError && err.status === 403) {
    if (/domain/i.test(err.detail)) {
      return "That Google account is not on the organisation's email domain. Sign in with your work account instead.";
    }
    return "This account has been deactivated. Contact an administrator.";
  }
  return describeError(err, {
    401: "Google could not verify that account. Try again, or use a different account.",
  });
}

export function GoogleSignIn({
  label,
  onError,
  onSuccess,
}: {
  label: string;
  onError: (message: string) => void;
  /** Called once the credential has been exchanged and the session is live. The caller
   *  owns the destination, exactly as it does for the password form. */
  onSuccess: () => void;
}) {
  const { loginWithGoogle } = useAuth();
  const hostRef = useRef<HTMLDivElement>(null);
  const [unavailable, setUnavailable] = useState(false);

  /* Held in refs so an inline arrow from the caller does not re-run the effect below:
     a second renderButton on the same host would stack a duplicate Google button. */
  const callbacks = useRef({ onError, onSuccess });
  useEffect(() => {
    callbacks.current = { onError, onSuccess };
  });

  useEffect(() => {
    if (!CLIENT_ID) return;
    let cancelled = false;

    void (async () => {
      try {
        const google = await loadGsi();
        if (cancelled || !hostRef.current) return;

        google.accounts.id.initialize({
          client_id: CLIENT_ID,
          use_fedcm_for_button: true,
          callback: (response) => {
            if (!response.credential) {
              callbacks.current.onError("Google did not return a credential. Try again.");
              return;
            }
            void loginWithGoogle(response.credential).then(
              () => callbacks.current.onSuccess(),
              (err: unknown) => {
                callbacks.current.onError(describeSignInError(err));
              },
            );
          },
        });

        google.accounts.id.renderButton(hostRef.current, {
          type: "standard",
          theme: "outline",
          size: "large",
          shape: "pill",
          text: "continue_with",
          logo_alignment: "center",
          width: hostRef.current.clientWidth || 320,
        });
      } catch {
        // Blocked by an extension, CSP, or offline. Say so rather than leaving a gap.
        if (!cancelled) setUnavailable(true);
      }
    })();

    return () => {
      cancelled = true;
    };
  }, [loginWithGoogle]);

  // Build-time configuration: no client ID means this build never offers Google at
  // all. Email/password sits beside this component, so the right move is to quietly
  // not render rather than block the page on a method nobody enabled.
  if (!CLIENT_ID) {
    return null;
  }

  return (
    <div className="flex flex-col gap-3">
      {unavailable ? (
        <p role="alert" className="text-caption text-ink-muted text-center">
          Google sign-in could not load — an extension, a content blocker, or a lost
          connection is the usual cause. Use email and password below instead, or retry
          once the connection is back.
        </p>
      ) : (
        <div ref={hostRef} aria-label={label} className="flex justify-center min-h-11" />
      )}
    </div>
  );
}
