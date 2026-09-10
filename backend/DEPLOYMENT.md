# Deploy the API to Render

The repository root contains `render.yaml`, which deploys this directory as a
Docker web service. The container runs as a non-root user, applies Alembic
migrations, listens on Render's `PORT`, and exposes `/health` for deployment
health checks.

## Required services

The recommended no-cost demo topology uses:

- Neon Free for PostgreSQL.
- Qdrant Cloud Free for vectors.
- Render Free for this API.

Free Render storage is ephemeral. Tender files written under `STORAGE_DIR` are
lost whenever the service restarts, redeploys, or spins down. Use this topology
only for a demo or replace local storage with durable object storage before
handling irreplaceable documents.

## Blueprint variables

In Render choose **New > Blueprint**, connect the repository, and select the
root `render.yaml`. Enter the prompted values:

```dotenv
DATABASE_URL=<Neon pooled connection string>
CORS_ALLOW_ORIGINS=https://your-frontend.netlify.app
ALLOWED_EMAIL_DOMAINS=example.com
BOOTSTRAP_SUPER_ADMIN_EMAIL=admin@example.com
QDRANT_URL=https://your-cluster.cloud.qdrant.io
QDRANT_API_KEY=<Qdrant API key>
```

The Blueprint generates `JWT_SECRET`, disables metrics, selects hash embeddings
to fit the free instance, and disables embedding warm-up. Add these optional
variables in Render when needed:

```dotenv
ALLOWED_EMAIL_EXCEPTIONS=consultant@example.net
GOOGLE_CLIENT_ID=<public OAuth web client ID>
GEMINI_API_KEY=<secret>
SENTRY_DSN=<secret DSN>
OTEL_EXPORTER_OTLP_ENDPOINT=<collector URL>
```

Production startup fails closed if `DATABASE_URL` or `CORS_ALLOW_ORIGINS` is
implicit, the database is not PostgreSQL, the JWT secret is weak, the domain
allowlist is empty, or enabled metrics use a weak password.

## Deploy and verify

1. Deploy the Blueprint and wait for `/health` to pass.
2. Confirm `GET https://your-api.onrender.com/health` returns status `ok`.
3. Set the frontend's `NEXT_PUBLIC_API_BASE_URL` to the API origin and deploy it.
4. Replace `CORS_ALLOW_ORIGINS` with the exact deployed frontend origin and
   redeploy this service.
5. Register or Google-sign-in with `BOOTSTRAP_SUPER_ADMIN_EMAIL`; its role
   assignment was seeded by the migration run during startup.
6. Create a tender and inspect Render logs for structured request entries.

For a paid multi-replica deployment, move `alembic upgrade head` from the image
startup command into Render's single pre-deploy command before increasing the
replica count. Attach durable storage or implement an object-storage adapter.

## Rollback

Use Render Events to roll back to a retained known-good deploy, then verify
`/health` and an authenticated route. Prefer a Neon restore or recovery branch
for database rollback. Do not run `alembic downgrade` against production without
a backup and migration-specific data-loss review.
