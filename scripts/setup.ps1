#Requires -Version 5.1
<#
.SYNOPSIS
    One-command setup for the Tender Intelligence Platform, from a fresh clone.

.DESCRIPTION
    Creates the three .env files from their committed templates, collects the
    administrator email, optionally configures Google and Gemini, generates
    service secrets, and brings the stack up. Backend startup applies migrations,
    including the migration that seeds the first SUPER_ADMIN assignment.

    Two modes:
      docker  (default)  every service in Compose; you use the app at :8080.
      native             Postgres + Qdrant in Docker, backend and frontend on
                         the host; run ./scripts/dev.ps1 afterwards.

    Re-running is safe: values you have already set are never overwritten.

.PARAMETER Mode
    'docker' or 'native'. Default 'docker'.

.PARAMETER NonInteractive
    Never prompt. Reads required TI_ADMIN_EMAIL plus optional
    TI_GOOGLE_CLIENT_ID and TI_GEMINI_API_KEY from the environment.

.PARAMETER SkipStart
    Write the configuration and stop, without touching Docker.

.EXAMPLE
    ./scripts/setup.ps1
    ./scripts/setup.ps1 -Mode native
    $env:TI_ADMIN_EMAIL='ops@example.com'; ./scripts/setup.ps1 -NonInteractive
#>
[CmdletBinding()]
param(
    [ValidateSet("docker", "native")][string]$Mode = "docker",
    [switch]$NonInteractive,
    [switch]$SkipStart
)

$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $PSScriptRoot
. "$PSScriptRoot/lib/envfile.ps1"
Set-Location $root
$script:RepoRoot = $root

$backendEnv = Join-Path $root "backend/.env"
$frontendEnv = Join-Path $root "frontend/.env.local"
$rootEnv = Join-Path $root ".env"

Write-Host ""
Write-Host "Tender Intelligence Platform - setup ($Mode mode)" -ForegroundColor White
Write-Host ""

# ---------------------------------------------------------------------------
# 1. Preflight
# ---------------------------------------------------------------------------
Write-Step "Checking prerequisites"

docker compose version *> $null
if ($LASTEXITCODE -ne 0) {
    throw "Docker Compose is not available. Install Docker Desktop and make sure it is running, then re-run this script. (Postgres and Qdrant run in Docker in both modes.)"
}
Write-Ok "Docker Compose found."

if ($Mode -eq "native") {
    $pyVersion = (python --version 2>&1) -replace '^Python\s+', ''
    if ($LASTEXITCODE -ne 0) { throw "Python was not found on PATH. The native mode needs Python 3.12 or newer." }
    if ([version]($pyVersion -replace '(\d+\.\d+\.\d+).*', '$1') -lt [version]"3.12.0") {
        throw "Python $pyVersion is too old - this project requires 3.12 or newer (backend/pyproject.toml)."
    }
    Write-Ok "Python $pyVersion."

    $nodeVersion = (node --version 2>&1) -replace '^v', ''
    if ($LASTEXITCODE -ne 0) { throw "Node was not found on PATH. The native mode needs Node 22 or newer (see .nvmrc)." }
    if ([version]($nodeVersion -replace '(\d+\.\d+\.\d+).*', '$1') -lt [version]"22.0.0") {
        throw "Node $nodeVersion is too old - CI and both Dockerfiles use Node 22 (see .nvmrc)."
    }
    Write-Ok "Node $nodeVersion."
}

# ---------------------------------------------------------------------------
# 2. Environment files
# ---------------------------------------------------------------------------
Write-Step "Preparing environment files"
Copy-EnvTemplate -Template "$root/.env.backend.example"  -Destination $backendEnv  | Out-Null
Copy-EnvTemplate -Template "$root/.env.frontend.example" -Destination $frontendEnv | Out-Null
Copy-EnvTemplate -Template "$root/.env.example"          -Destination $rootEnv     | Out-Null

# ---------------------------------------------------------------------------
# 3. Required account bootstrap and optional integrations
# ---------------------------------------------------------------------------
Write-Step "Collecting credentials"

$existingClientId = Get-EnvValue -Path $backendEnv -Key "GOOGLE_CLIENT_ID"
$existingAdmin = Get-EnvValue -Path $backendEnv -Key "BOOTSTRAP_SUPER_ADMIN_EMAIL"

if ([string]::IsNullOrWhiteSpace($existingAdmin)) {
    Write-Note "The first SUPER_ADMIN is seeded by a migration from this address."
    Write-Note "That address receives SUPER_ADMIN when it first registers or signs in."
    $adminEmail = Read-Required `
        -Prompt "    Administrator email address" `
        -EnvFallback "TI_ADMIN_EMAIL" `
        -NonInteractive:$NonInteractive `
        -Validator { param($v) $v -match '^[^@\s]+@[^@\s]+\.[^@\s]+$' } `
        -ValidationMessage "That is not a valid email address."
    $adminEmail = $adminEmail.ToLowerInvariant()
}
else {
    $adminEmail = $existingAdmin.ToLowerInvariant()
    Write-Note "Administrator already configured as $adminEmail."
}

if ([string]::IsNullOrWhiteSpace($existingClientId)) {
    Write-Note "Google sign-in is optional; email/password works without it."
    $clientId = Read-Optional `
        -Prompt "    Google OAuth client ID (optional, press Enter to skip)" `
        -EnvFallback "TI_GOOGLE_CLIENT_ID" `
        -NonInteractive:$NonInteractive
    if (-not [string]::IsNullOrWhiteSpace($clientId) -and
        $clientId -notmatch '\.apps\.googleusercontent\.com$') {
        throw "TI_GOOGLE_CLIENT_ID must be blank or end in '.apps.googleusercontent.com'."
    }
}
else {
    $clientId = $existingClientId
    Write-Note "Google client ID already configured."
}

# Optional, and only asked while the rest is being configured for the first
# time - re-runs should not nag about a key that was deliberately skipped.
# Add it later by editing GEMINI_API_KEY in backend/.env.
$geminiKey = ""
if ([string]::IsNullOrWhiteSpace($existingAdmin) -and
    [string]::IsNullOrWhiteSpace((Get-EnvValue -Path $backendEnv -Key "GEMINI_API_KEY"))) {
    $geminiKey = Read-Optional `
        -Prompt "    Gemini API key for the AI Analyst (optional, press Enter to skip)" `
        -EnvFallback "TI_GEMINI_API_KEY" `
        -NonInteractive:$NonInteractive
}

# ---------------------------------------------------------------------------
# 4. Write the configuration
# ---------------------------------------------------------------------------
Write-Step "Writing configuration"

Set-EnvValue -Path $backendEnv -Key "BOOTSTRAP_SUPER_ADMIN_EMAIL" -Value $adminEmail | Out-Null
Set-EnvValue -Path $backendEnv -Key "GOOGLE_CLIENT_ID" -Value $clientId | Out-Null
if (-not [string]::IsNullOrWhiteSpace($geminiKey)) {
    Set-EnvValue -Path $backendEnv -Key "GEMINI_API_KEY" -Value $geminiKey -KeepExisting | Out-Null
}

# The administrator has to be admitted, or their own sign-in is refused. If the
# domain is not already an organisation domain, admit the single address rather
# than widening ALLOWED_EMAIL_DOMAINS - the config comments are explicit that
# listing a domain admits everyone who shares it.
$adminDomain = $adminEmail.Split("@")[-1]
$allowedDomains = (Get-EnvValue -Path $backendEnv -Key "ALLOWED_EMAIL_DOMAINS")
$domainList = @($allowedDomains -split "," | ForEach-Object { $_.Trim().ToLowerInvariant() } | Where-Object { $_ })

if ($domainList -contains $adminDomain) {
    Write-Ok "$adminDomain is already an allowed organisation domain."
}
else {
    $exceptions = (Get-EnvValue -Path $backendEnv -Key "ALLOWED_EMAIL_EXCEPTIONS")
    $exceptionList = @($exceptions -split "," | ForEach-Object { $_.Trim().ToLowerInvariant() } | Where-Object { $_ })
    if ($exceptionList -notcontains $adminEmail) {
        $exceptionList += $adminEmail
        Set-EnvValue -Path $backendEnv -Key "ALLOWED_EMAIL_EXCEPTIONS" -Value ($exceptionList -join ",") | Out-Null
    }
    Write-Ok "Admitted $adminEmail via ALLOWED_EMAIL_EXCEPTIONS."
    Write-Note "To admit everyone at $adminDomain, add it to ALLOWED_EMAIL_DOMAINS in backend/.env."
}

# Generated, never prompted. -KeepExisting leaves a secret from an earlier run
# alone but does replace the template's 'change-me-in-production'.
if (Set-EnvValue -Path $backendEnv -Key "JWT_SECRET" -Value (New-JwtSecret) -KeepExisting) {
    Write-Ok "Generated a JWT_SECRET."
}
else {
    Write-Note "JWT_SECRET already set - left untouched."
}

if (Set-EnvValue -Path $backendEnv -Key "METRICS_PASSWORD" -Value (New-JwtSecret) -KeepExisting) {
    Write-Ok "Generated a separate METRICS_PASSWORD."
}
else {
    Write-Note "METRICS_PASSWORD already set - left untouched."
}

# Mode-dependent hosts. Inside Compose the database and vector store answer to
# their service names; on the host they answer to localhost. Writing them here
# is what lets one backend/.env serve both modes without editing compose.
$dbUrl = Get-EnvValue -Path $backendEnv -Key "DATABASE_URL"
if ($Mode -eq "docker") {
    $dbUrl = $dbUrl -replace '@localhost:', '@postgres:' -replace '@127\.0\.0\.1:', '@postgres:'
    Set-EnvValue -Path $backendEnv -Key "DATABASE_URL" -Value $dbUrl | Out-Null
    Set-EnvValue -Path $backendEnv -Key "QDRANT_URL" -Value "http://qdrant:6333" | Out-Null
}
else {
    $dbUrl = $dbUrl -replace '@postgres:', '@localhost:'
    Set-EnvValue -Path $backendEnv -Key "DATABASE_URL" -Value $dbUrl | Out-Null
    Set-EnvValue -Path $backendEnv -Key "QDRANT_URL" -Value "http://localhost:6333" | Out-Null
}
Write-Ok "Hosts tuned for $Mode mode ($dbUrl)."

# The browser calls the API directly on :8000 natively, and through nginx on
# :8080 under Compose. Both origins are allowed either way so switching modes
# does not strand a running browser tab.
Set-EnvValue -Path $backendEnv -Key "CORS_ALLOW_ORIGINS" -Value "http://localhost:3000,http://localhost:8080" | Out-Null

# NEXT_PUBLIC_* is inlined by `next build`, so Compose reads these from the root
# .env as build args; frontend/.env.local serves `next dev` on the host.
$apiBase = if ($Mode -eq "docker") { "http://localhost:8080/api" } else { "http://localhost:8000" }
Set-EnvValue -Path $rootEnv -Key "NEXT_PUBLIC_GOOGLE_CLIENT_ID" -Value $clientId | Out-Null
Set-EnvValue -Path $rootEnv -Key "NEXT_PUBLIC_API_BASE_URL" -Value "http://localhost:8080/api" | Out-Null
Set-EnvValue -Path $frontendEnv -Key "NEXT_PUBLIC_GOOGLE_CLIENT_ID" -Value $clientId | Out-Null
Set-EnvValue -Path $frontendEnv -Key "NEXT_PUBLIC_API_BASE_URL" -Value $apiBase | Out-Null
Write-Ok "Frontend API base: $apiBase"

if ($SkipStart) {
    Write-Host ""
    Write-Step "-SkipStart: configuration written, nothing started."
    return
}

# ---------------------------------------------------------------------------
# 5. Bring the stack up
# ---------------------------------------------------------------------------
if ($Mode -eq "docker") {
    Write-Step "Building and starting all services (this takes a few minutes the first time)"
    docker compose up -d --build --wait --wait-timeout 120
    if ($LASTEXITCODE -ne 0) { throw "docker compose up failed. See the output above." }
    Write-Ok "Services are healthy; backend startup applied the migrations."
}
else {
    Write-Step "Starting Postgres + Qdrant"
    docker compose up -d postgres qdrant
    if ($LASTEXITCODE -ne 0) { throw "docker compose up failed. See the output above." }
    Wait-PostgresHealthy
    Write-Ok "Postgres healthy."

    Set-Location "$root/backend"
    if (-not (Test-Path ".venv")) {
        Write-Step "Creating backend virtualenv"
        python -m venv .venv
    }
    $py = "$root/backend/.venv/Scripts/python.exe"
    Write-Step "Installing backend dependencies"
    & $py -m pip install --upgrade pip | Out-Null
    & $py -m pip install -e ".[dev]"
    if ($LASTEXITCODE -ne 0) { throw "pip install failed. See the output above." }

    Write-Step "Applying migrations and seeding the first SUPER_ADMIN"
    & $py -m alembic upgrade head
    if ($LASTEXITCODE -ne 0) { throw "alembic upgrade head failed. See the output above." }

    Set-Location "$root/frontend"
    Write-Step "Installing frontend dependencies"
    npm.cmd ci
    if ($LASTEXITCODE -ne 0) { throw "npm ci failed. See the output above." }
    Set-Location $root
}

# ---------------------------------------------------------------------------
# 6. Summary
# ---------------------------------------------------------------------------
Write-Host ""
Write-Host "Setup complete." -ForegroundColor Green
Write-Host ""
if ($Mode -eq "docker") {
    Write-Host "  Application    http://localhost:8080" -ForegroundColor White
    Write-Host "  API docs       http://localhost:8000/docs"
    Write-Host "  Logs           docker compose logs -f"
    Write-Host "  Stop           docker compose down"
}
else {
    Write-Host "  Start it       ./scripts/dev.ps1" -ForegroundColor White
    Write-Host "  Frontend       http://localhost:3000"
    Write-Host "  API docs       http://localhost:8000/docs"
}
Write-Host ""
Write-Host "  Administrator  $adminEmail"
Write-Note "Register with email/password or use Google if configured; the account is born SUPER_ADMIN."
Write-Note "Pre-provision other roles with scripts/seed_role_assignments.example.sql."
Write-Host ""
