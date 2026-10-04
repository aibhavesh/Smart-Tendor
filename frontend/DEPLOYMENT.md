# Deploy the frontend to Netlify

The repository root `netlify.toml` is the single source of truth. It sets the build
base to `frontend`, runs `npm run build`, publishes `.next`, and leaves the Next.js
runtime to Netlify's own adapter.

Do not add a second `netlify.toml` inside `frontend/`. Netlify resolves config from
the base directory first and the repo root second, so two files make the effective
configuration depend on lookup order.

Do not add an `[[plugins]]` block for `@netlify/plugin-nextjs`. This is a Next.js 16
application and Netlify provisions the correct runtime automatically through its
OpenNext adapter. Declaring that plugin opts the site **out** of those automatic
updates, and because the package is not in `package.json`, Netlify resolves it itself
ΓÇö where the old v4.x line fails against Next 16 with *"outdated version of the Next.js
Runtime"*.

## Build variables

Set these under **Site configuration > Environment variables > Production build
environment** before the first production deploy:

```dotenv
NEXT_PUBLIC_API_BASE_URL=https://your-api.onrender.com
NEXT_PUBLIC_GOOGLE_CLIENT_ID=
NEXT_PUBLIC_HERO_VIDEO=/video/hero.mp4
```

### `NEXT_PUBLIC_API_BASE_URL` must be the bare origin

Use scheme and host only, with **no trailing `/api`**:

```
https://your-api.onrender.com        <- correct
https://your-api.onrender.com/api    <- wrong
```

The backend mounts its routers under two different prefixes ΓÇö `/tenders/...` and
`/api/v1/tenders/...` ΓÇö and the client appends both verbatim to this base. Only the
bare origin resolves both families. The `/api` suffix is a Docker Compose convention
where nginx strips one `/api/` segment before proxying; pointing straight at the
deployed API must not include it.

### Only `NEXT_PUBLIC_*` belongs here

Everything else is a backend secret and belongs in Render's environment settings,
never in Netlify or in source control. `NEXT_PUBLIC_*` values are public by design ΓÇö
they are compiled into the browser bundle.

### Changing one requires a new build

`NEXT_PUBLIC_*` values are inlined by `next build`, so the deployed artifact is frozen.
Republishing an existing deploy does **not** update them; trigger a new build.

## Deploy

1. Netlify ΓåÆ **Add new project > Import an existing project**, connect this repository.
2. Confirm the detected base directory is `frontend`, build command `npm run build`,
   and publish directory `.next`. The checked-in `netlify.toml` supplies all three.
3. Add the build variables above and deploy.
4. Copy the resulting `https://...netlify.app` origin into the backend's
   `CORS_ALLOW_ORIGINS` (scheme and host only, no trailing slash), then redeploy the
   backend.
5. Hard-refresh and register with email/password, or use Google when configured.

## Verify a deployed build

Run the bundled check against the live site. It drives a real browser, so it proves
rendering, hydration, and which origin the API calls actually reach:

```bash
npm run start                                   # or point at any running build
node scripts/verify-deploy.mjs https://your-site.netlify.app https://your-api.onrender.com
```

It asserts that the landing page renders without console errors, that anonymous access
to `/dashboard` redirects to `/login`, and that every API request is dialled at the
configured origin with no doubled slashes.

Playwright's browser is a prerequisite: `npx playwright install chromium`.

Then confirm by hand:

- Browser DevTools shows API requests targeting the Render origin, never `localhost`.
- The preflight response echoes the exact frontend origin in
  `Access-Control-Allow-Origin`.
- The first request after idle time is slow while Render wakes from its cold start.

## If the API URL was wrong at build time

A build with no `NEXT_PUBLIC_API_BASE_URL` still succeeds and still serves ΓÇö the client
falls back to same-origin ΓÇö so a wrong value can be corrected without a rebuild:

```js
// DevTools console, on the deployed site
localStorage.setItem("ti.apiBase", "https://your-api.onrender.com");
location.reload();
```

The override is read **only** when the build had no `NEXT_PUBLIC_API_BASE_URL`, so it can
never shadow a correctly configured deployment. The proper fix is still to set the build
variable and redeploy; the override is for unblocking and for confirming a URL before
committing it to a build. Clear it with
`localStorage.removeItem("ti.apiBase")`.

## Rollback

In Netlify **Deploys**, select the previous known-good production deploy and publish it.
If `NEXT_PUBLIC_API_BASE_URL` or another public variable changed, trigger a new build with
the corrected value instead of republishing an artifact that still has the old value
embedded in its bundle.
