# Deploy the frontend to Netlify

The repository root `netlify.toml` sets this directory as the build base, runs
`npm run build`, publishes `.next`, and enables Netlify's Next.js adapter.

## Build variables

Set these before the first production deploy:

```dotenv
NEXT_PUBLIC_API_BASE_URL=https://your-api.onrender.com
NEXT_PUBLIC_GOOGLE_CLIENT_ID=
NEXT_PUBLIC_HERO_VIDEO=/video/hero.mp4
```

Google sign-in is optional. When enabled, use the same client ID in the backend
`GOOGLE_CLIENT_ID` setting and add the Netlify/custom origins to the OAuth Web
Client's Authorized JavaScript origins.

All `NEXT_PUBLIC_*` values are compiled into the browser bundle during
`npm run build`. Changing one requires a new production deploy; restarting or
republishing the same artifact does not update it.

## Deploy and verify

1. In Netlify choose **Add new project > Import an existing project** and connect
   this repository.
2. Confirm the detected base is `frontend`, build command is `npm run build`, and
   publish directory is `.next`.
3. Add the build variables and deploy.
4. Copy the resulting `https://...netlify.app` origin into the backend's
   `CORS_ALLOW_ORIGINS`, then redeploy the backend.
5. Hard-refresh the frontend. Register with email/password or use Google when
   configured.
6. In browser DevTools confirm API requests target the Render origin, never
   localhost, and that the preflight response echoes the exact frontend origin.

## Rollback

In Netlify Deploys, select the previous known-good production deploy and publish
it. If `NEXT_PUBLIC_API_BASE_URL` or another public variable changed, trigger a
new build with the corrected value instead of republishing an artifact that has
the old value embedded.
