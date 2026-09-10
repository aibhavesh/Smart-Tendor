#Requires -Version 5.1
<#
.SYNOPSIS
    Local development launcher for the Tender Intelligence Platform.

.DESCRIPTION
    Brings up Postgres + Qdrant in Docker, provisions the backend venv, applies
    Alembic migrations, and starts the API (:8000) and the frontend (:3000).

.EXAMPLE
    ./scripts/dev.ps1              # full stack
    ./scripts/dev.ps1 -SkipFrontend
    ./scripts/dev.ps1 -InfraOnly   # just Postgres + Qdrant

.NOTES
    Run ./scripts/setup.ps1 -Mode native first: this script assumes the .env
    files exist and are tuned for native mode.
#>
[CmdletBinding()]
param(
    [switch]$SkipFrontend,
    [switch]$InfraOnly
)

$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $PSScriptRoot
. "$PSScriptRoot/lib/envfile.ps1"
Set-Location $root
$script:RepoRoot = $root

Set-Alias Step Write-Step

# --- Per-app env files ---
Copy-EnvTemplate -Template "$root/.env.backend.example"  -Destination "$root/backend/.env"       | Out-Null
Copy-EnvTemplate -Template "$root/.env.frontend.example" -Destination "$root/frontend/.env.local" | Out-Null

$dbUrl = Get-EnvValue -Path "$root/backend/.env" -Key "DATABASE_URL"
if ($dbUrl -match '@postgres:') {
    Write-Warn "backend/.env points DATABASE_URL at the Compose service 'postgres', which the host"
    Write-Warn "cannot resolve. Re-run ./scripts/setup.ps1 -Mode native to switch it to localhost."
}

# --- Infra (Postgres + Qdrant) ---
Step "Starting Postgres + Qdrant (Docker)"
docker compose up -d postgres qdrant

Step "Waiting for Postgres to be healthy"
Wait-PostgresHealthy
Write-Ok "Postgres healthy."

if ($InfraOnly) { Step "InfraOnly: done."; return }

# --- Backend venv ---
Set-Location "$root/backend"
if (-not (Test-Path ".venv")) {
    Step "Creating backend virtualenv"
    python -m venv .venv
}
$py = "$root/backend/.venv/Scripts/python.exe"
Step "Installing backend (editable + dev extras)"
& $py -m pip install --upgrade pip | Out-Null
& $py -m pip install -e ".[dev]"

Step "Applying database migrations"
& $py -m alembic upgrade head

Step "Starting API on http://localhost:8000"
$api = Start-Process -PassThru -FilePath $py `
    -ArgumentList "-m", "uvicorn", "tender_intel.api.app:app", "--reload", "--port", "8000" `
    -WindowStyle Hidden

# --- Frontend ---
if (-not $SkipFrontend -and (Test-Path "$root/frontend/package.json")) {
    Set-Location "$root/frontend"
    if (-not (Test-Path "node_modules")) { Step "Installing frontend deps"; npm.cmd ci }
    Step "Starting frontend on http://localhost:3000"
    npm.cmd run dev
} else {
    Step "API running (PID $($api.Id)). Press Ctrl+C to stop."
    Wait-Process -Id $api.Id
}
