#!/usr/bin/env bash
#
# Local development launcher for the Tender Intelligence Platform (POSIX twin of
# scripts/dev.ps1).
#
# Brings up Postgres + Qdrant in Docker, provisions the backend venv, applies
# Alembic migrations, and starts the API (:8000) and the frontend (:3000).
#
#   ./scripts/dev.sh                 # full stack
#   ./scripts/dev.sh --skip-frontend
#   ./scripts/dev.sh --infra-only    # just Postgres + Qdrant
#
# Run ./scripts/setup.sh --mode native first: this script assumes the .env files
# exist and are tuned for native mode.
#
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT="$(dirname "$SCRIPT_DIR")"
# shellcheck source=lib/envfile.sh
. "$SCRIPT_DIR/lib/envfile.sh"
cd "$ROOT"
REPO_ROOT="$ROOT"

SKIP_FRONTEND=0
INFRA_ONLY=0
while [ $# -gt 0 ]; do
    case "$1" in
        --skip-frontend) SKIP_FRONTEND=1; shift ;;
        --infra-only) INFRA_ONLY=1; shift ;;
        -h|--help) sed -n '3,15p' "${BASH_SOURCE[0]}" | sed 's/^# \{0,1\}//'; exit 0 ;;
        *) die "Unknown option: $1 (try --help)" ;;
    esac
done

# --- Per-app env files ---
copy_env_template "$ROOT/.env.backend.example"  "$ROOT/backend/.env"
copy_env_template "$ROOT/.env.frontend.example" "$ROOT/frontend/.env.local"

DB_URL="$(get_env_value "$ROOT/backend/.env" "DATABASE_URL")"
case "$DB_URL" in
    *@postgres:*)
        warn "backend/.env points DATABASE_URL at the Compose service 'postgres', which the host"
        warn "cannot resolve. Re-run ./scripts/setup.sh --mode native to switch it to localhost."
        ;;
esac

# --- Infra (Postgres + Qdrant) ---
step "Starting Postgres + Qdrant (Docker)"
docker compose up -d postgres qdrant

step "Waiting for Postgres to be healthy"
wait_postgres_healthy
ok "Postgres healthy."

if [ "$INFRA_ONLY" = "1" ]; then
    step "--infra-only: done."
    exit 0
fi

# --- Backend venv ---
cd "$ROOT/backend"
if [ ! -d ".venv" ]; then
    step "Creating backend virtualenv"
    python3 -m venv .venv
fi
PY="$ROOT/backend/.venv/bin/python"

step "Installing backend (editable + dev extras)"
"$PY" -m pip install --upgrade pip >/dev/null
"$PY" -m pip install -e ".[dev]"

step "Applying database migrations"
"$PY" -m alembic upgrade head

step "Starting API on http://localhost:8000"
"$PY" -m uvicorn tender_intel.api.app:app --reload --port 8000 &
API_PID=$!
# Stop the API when this script exits, however it exits — otherwise Ctrl+C on
# the frontend would leave a uvicorn holding :8000.
trap 'kill "$API_PID" 2>/dev/null || true' EXIT INT TERM

# --- Frontend ---
if [ "$SKIP_FRONTEND" = "0" ] && [ -f "$ROOT/frontend/package.json" ]; then
    cd "$ROOT/frontend"
    if [ ! -d "node_modules" ]; then
        step "Installing frontend deps"
        npm install
    fi
    step "Starting frontend on http://localhost:3000"
    npm run dev
else
    step "API running (PID $API_PID). Press Ctrl+C to stop."
    wait "$API_PID"
fi
