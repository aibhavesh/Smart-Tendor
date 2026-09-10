#!/usr/bin/env bash
#
# One-command setup for the Tender Intelligence Platform, from a fresh clone.
#
# Creates the three .env files from their committed templates, collects the
# administrator email, optionally configures Google and Gemini, generates
# service secrets, and starts the stack. Backend startup applies migrations,
# including the migration that seeds the first SUPER_ADMIN assignment.
#
# Modes:
#   --mode docker  (default)  every service in Compose; you use the app at :8080.
#   --mode native             Postgres + Qdrant in Docker, backend and frontend
#                             on the host; run ./scripts/dev.sh afterwards.
#
# Re-running is safe: values you have already set are never overwritten.
#
#   ./scripts/setup.sh
#   ./scripts/setup.sh --mode native
#   TI_ADMIN_EMAIL=ops@example.com ./scripts/setup.sh --non-interactive
#
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT="$(dirname "$SCRIPT_DIR")"
# shellcheck source=lib/envfile.sh
. "$SCRIPT_DIR/lib/envfile.sh"
cd "$ROOT"
REPO_ROOT="$ROOT"

MODE="docker"
NON_INTERACTIVE=0
SKIP_START=0

while [ $# -gt 0 ]; do
    case "$1" in
        --mode) MODE="${2:-}"; shift 2 ;;
        --mode=*) MODE="${1#*=}"; shift ;;
        --non-interactive) NON_INTERACTIVE=1; shift ;;
        --skip-start) SKIP_START=1; shift ;;
        -h|--help) sed -n '3,20p' "${BASH_SOURCE[0]}" | sed 's/^# \{0,1\}//'; exit 0 ;;
        *) die "Unknown option: $1 (try --help)" ;;
    esac
done
[ "$MODE" = "docker" ] || [ "$MODE" = "native" ] || die "--mode must be 'docker' or 'native'."

BACKEND_ENV="$ROOT/backend/.env"
FRONTEND_ENV="$ROOT/frontend/.env.local"
ROOT_ENV="$ROOT/.env"

echo
echo "Tender Intelligence Platform — setup ($MODE mode)"
echo

# ---------------------------------------------------------------------------
# 1. Preflight
# ---------------------------------------------------------------------------
step "Checking prerequisites"

command -v docker >/dev/null 2>&1 || die "Docker was not found on PATH. Install Docker Desktop (or the Docker engine) and start it, then re-run this script."
docker compose version >/dev/null 2>&1 || die "Docker Compose v2 is not available. Update Docker, or start Docker Desktop if it is not running. (Postgres and Qdrant run in Docker in both modes.)"
ok "Docker Compose found."

# Compares dotted versions without bc/sort -V, which are not universal.
version_at_least() {
    local have="$1" want="$2"
    [ "$(printf '%s\n%s\n' "$want" "$have" | sort -t. -k1,1n -k2,2n -k3,3n | head -n 1)" = "$want" ]
}

if [ "$MODE" = "native" ]; then
    command -v python3 >/dev/null 2>&1 || die "Python was not found on PATH. The native mode needs Python 3.12 or newer."
    PY_VERSION="$(python3 -c 'import platform; print(platform.python_version())')"
    version_at_least "$PY_VERSION" "3.12.0" || die "Python $PY_VERSION is too old — this project requires 3.12 or newer (backend/pyproject.toml)."
    ok "Python $PY_VERSION."

    command -v node >/dev/null 2>&1 || die "Node was not found on PATH. The native mode needs Node 22 or newer (see .nvmrc)."
    NODE_VERSION="$(node --version | sed 's/^v//')"
    version_at_least "$NODE_VERSION" "22.0.0" || die "Node $NODE_VERSION is too old — CI and both Dockerfiles use Node 22 (see .nvmrc)."
    ok "Node $NODE_VERSION."
fi

# ---------------------------------------------------------------------------
# 2. Environment files
# ---------------------------------------------------------------------------
step "Preparing environment files"
copy_env_template "$ROOT/.env.backend.example"  "$BACKEND_ENV"
copy_env_template "$ROOT/.env.frontend.example" "$FRONTEND_ENV"
copy_env_template "$ROOT/.env.example"          "$ROOT_ENV"

# ---------------------------------------------------------------------------
# 3. Required account bootstrap and optional integrations
# ---------------------------------------------------------------------------
step "Collecting credentials"

valid_email()     { printf '%s' "$1" | grep -qE '^[^@[:space:]]+@[^@[:space:]]+\.[^@[:space:]]+$'; }
valid_client_id() { printf '%s' "$1" | grep -qE '\.apps\.googleusercontent\.com$'; }

EXISTING_ADMIN="$(get_env_value "$BACKEND_ENV" "BOOTSTRAP_SUPER_ADMIN_EMAIL")"
if [ -z "$EXISTING_ADMIN" ]; then
    note "The first SUPER_ADMIN is seeded by a migration from this address."
    note "That address receives SUPER_ADMIN when it first registers or signs in."
    ADMIN_EMAIL="$(read_required "    Administrator email address: " TI_ADMIN_EMAIL "$NON_INTERACTIVE" \
        valid_email "That is not a valid email address.")"
else
    ADMIN_EMAIL="$EXISTING_ADMIN"
    note "Administrator already configured as $ADMIN_EMAIL."
fi
ADMIN_EMAIL="$(printf '%s' "$ADMIN_EMAIL" | tr '[:upper:]' '[:lower:]')"

EXISTING_CLIENT_ID="$(get_env_value "$BACKEND_ENV" "GOOGLE_CLIENT_ID")"
if [ -z "$EXISTING_CLIENT_ID" ]; then
    note "Google sign-in is optional; email/password works without it."
    CLIENT_ID="$(read_optional "    Google OAuth client ID (optional, press Enter to skip): " \
        TI_GOOGLE_CLIENT_ID "$NON_INTERACTIVE")"
    if [ -n "$CLIENT_ID" ] && ! valid_client_id "$CLIENT_ID"; then
        die "TI_GOOGLE_CLIENT_ID must be blank or end in '.apps.googleusercontent.com'."
    fi
else
    CLIENT_ID="$EXISTING_CLIENT_ID"
    note "Google client ID already configured."
fi

# Optional, and only asked while the rest is being configured for the first
# time - re-runs should not nag about a key that was deliberately skipped.
# Add it later by editing GEMINI_API_KEY in backend/.env.
GEMINI_KEY=""
if [ -z "$EXISTING_ADMIN" ] && [ -z "$(get_env_value "$BACKEND_ENV" "GEMINI_API_KEY")" ]; then
    GEMINI_KEY="$(read_optional "    Gemini API key for the AI Analyst (optional, press Enter to skip): " \
        TI_GEMINI_API_KEY "$NON_INTERACTIVE")"
fi

# ---------------------------------------------------------------------------
# 4. Write the configuration
# ---------------------------------------------------------------------------
step "Writing configuration"

set_env_value "$BACKEND_ENV" "BOOTSTRAP_SUPER_ADMIN_EMAIL" "$ADMIN_EMAIL"
set_env_value "$BACKEND_ENV" "GOOGLE_CLIENT_ID" "$CLIENT_ID"
if [ -n "$GEMINI_KEY" ]; then
    set_env_value "$BACKEND_ENV" "GEMINI_API_KEY" "$GEMINI_KEY" --keep
fi

# The administrator has to be admitted, or their own sign-in is refused. If the
# domain is not already an organisation domain, admit the single address rather
# than widening ALLOWED_EMAIL_DOMAINS — the config comments are explicit that
# listing a domain admits everyone who shares it.
ADMIN_DOMAIN="${ADMIN_EMAIL##*@}"
ALLOWED_DOMAINS="$(get_env_value "$BACKEND_ENV" "ALLOWED_EMAIL_DOMAINS")"
if printf '%s' ",$ALLOWED_DOMAINS," | tr -d '[:space:]' | tr '[:upper:]' '[:lower:]' | grep -q ",$ADMIN_DOMAIN,"; then
    ok "$ADMIN_DOMAIN is already an allowed organisation domain."
else
    EXCEPTIONS="$(get_env_value "$BACKEND_ENV" "ALLOWED_EMAIL_EXCEPTIONS" | tr -d '[:space:]' | tr '[:upper:]' '[:lower:]')"
    if ! printf '%s' ",$EXCEPTIONS," | grep -q ",$ADMIN_EMAIL,"; then
        if [ -n "$EXCEPTIONS" ]; then EXCEPTIONS="$EXCEPTIONS,$ADMIN_EMAIL"; else EXCEPTIONS="$ADMIN_EMAIL"; fi
        set_env_value "$BACKEND_ENV" "ALLOWED_EMAIL_EXCEPTIONS" "$EXCEPTIONS"
    fi
    ok "Admitted $ADMIN_EMAIL via ALLOWED_EMAIL_EXCEPTIONS."
    note "To admit everyone at $ADMIN_DOMAIN, add it to ALLOWED_EMAIL_DOMAINS in backend/.env."
fi

# Generated, never prompted. --keep leaves a secret from an earlier run alone
# but does replace the template's 'change-me-in-production'.
CURRENT_SECRET="$(get_env_value "$BACKEND_ENV" "JWT_SECRET")"
set_env_value "$BACKEND_ENV" "JWT_SECRET" "$(new_jwt_secret)" --keep
if [ -z "$CURRENT_SECRET" ] || [ "$CURRENT_SECRET" = "change-me-in-production" ]; then
    ok "Generated a JWT_SECRET."
else
    note "JWT_SECRET already set — left untouched."
fi

CURRENT_METRICS_SECRET="$(get_env_value "$BACKEND_ENV" "METRICS_PASSWORD")"
set_env_value "$BACKEND_ENV" "METRICS_PASSWORD" "$(new_jwt_secret)" --keep
if [ -z "$CURRENT_METRICS_SECRET" ] || [ "$CURRENT_METRICS_SECRET" = "change-me-in-production" ]; then
    ok "Generated a separate METRICS_PASSWORD."
else
    note "METRICS_PASSWORD already set — left untouched."
fi

# Mode-dependent hosts. Inside Compose the database and vector store answer to
# their service names; on the host they answer to localhost. Writing them here
# is what lets one backend/.env serve both modes without editing compose.
DB_URL="$(get_env_value "$BACKEND_ENV" "DATABASE_URL")"
if [ "$MODE" = "docker" ]; then
    DB_URL="$(printf '%s' "$DB_URL" | sed -e 's/@localhost:/@postgres:/' -e 's/@127\.0\.0\.1:/@postgres:/')"
    set_env_value "$BACKEND_ENV" "DATABASE_URL" "$DB_URL"
    set_env_value "$BACKEND_ENV" "QDRANT_URL" "http://qdrant:6333"
else
    DB_URL="$(printf '%s' "$DB_URL" | sed -e 's/@postgres:/@localhost:/')"
    set_env_value "$BACKEND_ENV" "DATABASE_URL" "$DB_URL"
    set_env_value "$BACKEND_ENV" "QDRANT_URL" "http://localhost:6333"
fi
ok "Hosts tuned for $MODE mode ($DB_URL)."

# The browser calls the API directly on :8000 natively, and through nginx on
# :8080 under Compose. Both origins are allowed either way so switching modes
# does not strand a running browser tab.
set_env_value "$BACKEND_ENV" "CORS_ALLOW_ORIGINS" "http://localhost:3000,http://localhost:8080"

# NEXT_PUBLIC_* is inlined by `next build`, so Compose reads these from the root
# .env as build args; frontend/.env.local serves `next dev` on the host.
if [ "$MODE" = "docker" ]; then API_BASE="http://localhost:8080/api"; else API_BASE="http://localhost:8000"; fi
set_env_value "$ROOT_ENV" "NEXT_PUBLIC_GOOGLE_CLIENT_ID" "$CLIENT_ID"
set_env_value "$ROOT_ENV" "NEXT_PUBLIC_API_BASE_URL" "http://localhost:8080/api"
set_env_value "$FRONTEND_ENV" "NEXT_PUBLIC_GOOGLE_CLIENT_ID" "$CLIENT_ID"
set_env_value "$FRONTEND_ENV" "NEXT_PUBLIC_API_BASE_URL" "$API_BASE"
ok "Frontend API base: $API_BASE"

if [ "$SKIP_START" = "1" ]; then
    echo
    step "--skip-start: configuration written, nothing started."
    exit 0
fi

# ---------------------------------------------------------------------------
# 5. Bring the stack up
# ---------------------------------------------------------------------------
if [ "$MODE" = "docker" ]; then
    step "Building and starting all services (this takes a few minutes the first time)"
    docker compose up -d --build --wait --wait-timeout 120
    ok "Services are healthy; backend startup applied the migrations."
else
    step "Starting Postgres + Qdrant"
    docker compose up -d postgres qdrant
    wait_postgres_healthy
    ok "Postgres healthy."

    cd "$ROOT/backend"
    if [ ! -d ".venv" ]; then
        step "Creating backend virtualenv"
        python3 -m venv .venv
    fi
    PY="$ROOT/backend/.venv/bin/python"
    step "Installing backend dependencies"
    "$PY" -m pip install --upgrade pip >/dev/null
    "$PY" -m pip install -e ".[dev]"

    step "Applying migrations and seeding the first SUPER_ADMIN"
    "$PY" -m alembic upgrade head

    cd "$ROOT/frontend"
    step "Installing frontend dependencies"
    npm ci
    cd "$ROOT"
fi

# ---------------------------------------------------------------------------
# 6. Summary
# ---------------------------------------------------------------------------
echo
printf '%sSetup complete.%s\n\n' "$_C_OK" "$_C_OFF"
if [ "$MODE" = "docker" ]; then
    echo "  Application    http://localhost:8080"
    echo "  API docs       http://localhost:8000/docs"
    echo "  Logs           docker compose logs -f"
    echo "  Stop           docker compose down"
else
    echo "  Start it       ./scripts/dev.sh"
    echo "  Frontend       http://localhost:3000"
    echo "  API docs       http://localhost:8000/docs"
fi
echo
echo "  Administrator  $ADMIN_EMAIL"
note "Register with email/password or use Google if configured; the account is born SUPER_ADMIN."
note "Pre-provision other roles with scripts/seed_role_assignments.example.sql."
echo
