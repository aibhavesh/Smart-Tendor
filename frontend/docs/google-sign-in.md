# Google sign-in — setup

Google Identity Services is an optional sign-in method alongside email/password.
Both methods use the same organisation-domain and exact-address admission rules.
There is no password-reset flow.

The code is complete on both sides. What remains is one credential, which only you can
create: a Google OAuth **Web application** client ID.

## What already exists

| Half | State |
|---|---|
| Backend `POST /auth/google` | Complete. Verifies the `id_token` against `google_client_id`, requires `email_verified`, checks the address (and Google's `hd` claim when present) against `ALLOWED_EMAIL_DOMAINS`, links it to an existing account by email, or creates a new user at role **EMPLOYEE** — or at a pre-provisioned role, if an administrator set one for that address. |
| Frontend `GoogleSignIn` | Complete. Loads Google Identity Services, renders the official button, exchanges the credential and signs the user in. |

With no `NEXT_PUBLIC_GOOGLE_CLIENT_ID`, the Google control is omitted and the
email/password form remains available.

## One-time setup

1. In the [Google Cloud console](https://console.cloud.google.com/apis/credentials),
   create an OAuth client ID of type **Web application**.
2. Add your origins under **Authorised JavaScript origins** — the exact scheme, host and
   port, no trailing slash:

   ```
   http://localhost:3000
   ```

   Google matches these exactly. A trailing slash, `127.0.0.1` instead of `localhost`, or
   the wrong port all fail silently with an unrendered button.
3. **Leave "Authorised redirect URIs" empty.** See below for why.
4. Copy the client ID (it ends in `.apps.googleusercontent.com`).

## Why no redirect URI

Google's console offers two fields because it covers two different flows:

| Flow | Uses | Needs |
|---|---|---|
| **Authorization code** — Google redirects the browser back to your server with a `code`, which the server swaps for tokens | server-side web apps | redirect URIs **and** a client secret |
| **ID token** (Google Identity Services) — the button returns a signed JWT straight to the page; no redirect ever happens | this project | JavaScript origins **only** |

This project uses the second. `GoogleSignIn.tsx` calls `google.accounts.id.renderButton`,
which hands the `id_token` to a JavaScript callback in the same page — the browser is
never sent anywhere, so there is no URL to come back to. The field is not applicable.

If the console refuses to save with the field blank, putting `http://localhost:3000` in it
is harmless: nothing in this codebase will ever use it.

## You do not need the client secret

`backend/src/tender_intel/infrastructure/security/google.py` verifies the token by calling
Google's public `tokeninfo` endpoint and checking that the token's `aud` equals your client
ID. `google_client_secret` is declared in `core/config.py` and **never read anywhere**.

So leave it unset. A secret you do not need is a secret you cannot leak.

## Wiring it up

**Both** halves need the *same* client ID, because the backend verifies that the token's
audience matches.

Backend — `backend/.env`:

```
GOOGLE_CLIENT_ID=<id>.apps.googleusercontent.com
```

(No `GOOGLE_CLIENT_SECRET` — see above. It is unused by this flow.)

Frontend — `frontend/.env.local` for local dev:

```
NEXT_PUBLIC_GOOGLE_CLIENT_ID=<id>.apps.googleusercontent.com
```

`NEXT_PUBLIC_*` is **inlined at build time**, not read at runtime. In Docker it must be
passed as a build argument, not only as an `env_file` entry. The checked-in Compose file
already forwards `NEXT_PUBLIC_GOOGLE_CLIENT_ID` as a frontend build argument.

## Behaviour worth knowing

- **Only organisation addresses are admitted.** The domain must be in the backend's
  `ALLOWED_EMAIL_DOMAINS`. A personal Gmail is refused with 403 before any account row is
  created. When Google supplies an `hd` (hosted domain) claim it is checked too.
- **New users land at role EMPLOYEE**, unless an administrator pre-provisioned a higher
  role for that address first — see *Pre-provisioned roles* in the administration console.
  The list is consulted once, at account creation, and never again.
- **Existing accounts link by email.** Signing in with Google using an address that already
  has an account attaches the Google identity to it rather than creating a duplicate, and
  leaves its role untouched.
- **A deactivated account is refused** — 403. Deactivation is the offboarding control; the
  domain check does not expire when somebody leaves.
- **A refused domain and a deactivated account are both 403.** The frontend tells them
  apart by the server's message, because they need different advice.
- If the GIS script is blocked (extension, CSP, offline), the control says so and invites a
  retry, rather than leaving an empty gap.
- The **audience check is the security boundary**: a token minted for someone else's client
  ID is rejected with `InvalidTokenError`, so publishing your client ID is safe (and
  unavoidable — it is in the page source).
- Unverified Google emails are refused outright.

## Checking it works

With the ID set, rebuild (`npm run build` — build-time inlining) and load `/login`. You
should see Google's button below the divider. If the space is empty, the usual cause is
origin mismatch in step 2; check the browser console for a GSI origin error.
