# Shared dotenv helpers for scripts/setup.ps1 and scripts/dev.ps1.
# Dot-source it:  . "$PSScriptRoot/lib/envfile.ps1"

Set-StrictMode -Version Latest

# Values a template ships as "not filled in yet". Set-EnvValue overwrites these
# but never a real answer, which is what makes re-running setup safe.
$script:PlaceholderValues = @("", "change-me-in-production")

# Set by the calling script so messages can name files relative to the repo.
$script:RepoRoot = ""

function Show-Path($path) {
    if ($script:RepoRoot -and $path.StartsWith($script:RepoRoot, [StringComparison]::OrdinalIgnoreCase)) {
        return $path.Substring($script:RepoRoot.Length).TrimStart('\', '/').Replace('\', '/')
    }
    return $path
}

function Write-Step($msg) { Write-Host "==> $msg" -ForegroundColor Cyan }
function Write-Note($msg) { Write-Host "    $msg" -ForegroundColor DarkGray }
function Write-Ok($msg) { Write-Host "    $msg" -ForegroundColor Green }
function Write-Warn($msg) { Write-Host "    $msg" -ForegroundColor Yellow }

function Get-EnvValue {
    <#
    .SYNOPSIS
        Read KEY from a dotenv file. Returns $null when the file or key is absent.
    #>
    param(
        [Parameter(Mandatory)][string]$Path,
        [Parameter(Mandatory)][string]$Key
    )
    if (-not (Test-Path $Path)) { return $null }
    foreach ($line in Get-Content -LiteralPath $Path) {
        if ($line -match "^\s*$([regex]::Escape($Key))\s*=(.*)$") {
            return $Matches[1].Trim()
        }
    }
    return $null
}

function Set-EnvValue {
    <#
    .SYNOPSIS
        Upsert KEY=value in a dotenv file, preserving comments and line order.
    .DESCRIPTION
        Rewrites the KEY= line in place when it exists, appends it otherwise.
        With -KeepExisting the write is skipped when the key already holds a
        real (non-placeholder) value, so a contributor's own edits survive a
        re-run of setup.
    #>
    param(
        [Parameter(Mandatory)][string]$Path,
        [Parameter(Mandatory)][string]$Key,
        [Parameter(Mandatory)][AllowEmptyString()][string]$Value,
        [switch]$KeepExisting
    )

    $current = Get-EnvValue -Path $Path -Key $Key
    if ($KeepExisting -and $null -ne $current -and $script:PlaceholderValues -notcontains $current) {
        return $false
    }

    $lines = if (Test-Path $Path) { @(Get-Content -LiteralPath $Path) } else { @() }
    $pattern = "^\s*$([regex]::Escape($Key))\s*="
    $replaced = $false
    $out = foreach ($line in $lines) {
        if (-not $replaced -and $line -match $pattern) {
            $replaced = $true
            "$Key=$Value"
        }
        else { $line }
    }
    if (-not $replaced) { $out = @($out) + "$Key=$Value" }

    # UTF-8 without BOM: pydantic-settings reads the file as plain utf-8 and a
    # BOM would corrupt the first key's name.
    $text = ($out -join "`n") + "`n"
    [System.IO.File]::WriteAllText($Path, $text, (New-Object System.Text.UTF8Encoding($false)))
    return $true
}

function Copy-EnvTemplate {
    <#
    .SYNOPSIS
        Create a dotenv file from its committed template if it does not exist yet.
    #>
    param(
        [Parameter(Mandatory)][string]$Template,
        [Parameter(Mandatory)][string]$Destination
    )
    if (Test-Path $Destination) {
        Write-Note "$(Show-Path $Destination) already exists - keeping it."
        return $false
    }
    if (-not (Test-Path $Template)) {
        throw "Missing template $(Show-Path $Template). Is this a complete clone of the repository?"
    }
    Copy-Item -LiteralPath $Template -Destination $Destination
    Write-Ok "Created $(Show-Path $Destination) from $(Show-Path $Template)"
    return $true
}

function New-JwtSecret {
    <#
    .SYNOPSIS
        48 random bytes, URL-safe base64 - the value .env.backend.example tells
        you to generate. Uses .NET, so it needs neither python nor openssl.
        Create()/GetBytes rather than the newer static Fill(), which does not
        exist on the .NET Framework that Windows PowerShell 5.1 runs on.
    #>
    $bytes = New-Object byte[] 48
    $rng = [System.Security.Cryptography.RandomNumberGenerator]::Create()
    try { $rng.GetBytes($bytes) } finally { $rng.Dispose() }
    return [Convert]::ToBase64String($bytes).TrimEnd('=').Replace('+', '-').Replace('/', '_')
}

function Read-Required {
    <#
    .SYNOPSIS
        Prompt until a non-empty answer is given, or fail immediately when
        non-interactive.
    .PARAMETER EnvFallback
        Name of an environment variable consulted first - this is how
        -NonInteractive supplies the answer.
    #>
    param(
        [Parameter(Mandatory)][string]$Prompt,
        [Parameter(Mandatory)][string]$EnvFallback,
        [switch]$NonInteractive,
        [scriptblock]$Validator,
        [string]$ValidationMessage = "That value does not look right."
    )

    $preset = [Environment]::GetEnvironmentVariable($EnvFallback)
    if (-not [string]::IsNullOrWhiteSpace($preset)) {
        $preset = $preset.Trim()
        if ($Validator -and -not (& $Validator $preset)) {
            throw "$EnvFallback is set but invalid. $ValidationMessage"
        }
        Write-Note "$EnvFallback supplied from the environment."
        return $preset
    }

    if ($NonInteractive) {
        throw "$EnvFallback is required in -NonInteractive mode but is not set."
    }

    while ($true) {
        try { $answer = (Read-Host $Prompt).Trim() }
        catch {
            throw "This value must be entered, but the console cannot prompt (PowerShell is running non-interactively). Set $EnvFallback and re-run with -NonInteractive."
        }
        if ([string]::IsNullOrWhiteSpace($answer)) {
            Write-Warn "This value is required."
            continue
        }
        if ($Validator -and -not (& $Validator $answer)) {
            Write-Warn $ValidationMessage
            continue
        }
        return $answer
    }
}

function Read-Optional {
    <#
    .SYNOPSIS
        Prompt for a value that may be left blank. Returns "" when skipped.
    #>
    param(
        [Parameter(Mandatory)][string]$Prompt,
        [Parameter(Mandatory)][string]$EnvFallback,
        [switch]$NonInteractive
    )
    $preset = [Environment]::GetEnvironmentVariable($EnvFallback)
    if (-not [string]::IsNullOrWhiteSpace($preset)) { return $preset.Trim() }
    if ($NonInteractive) { return "" }
    # A host with no console (a CI runner, an IDE task) throws rather than
    # returning empty. Skipping an optional value is the right answer there.
    try { return (Read-Host $Prompt).Trim() } catch { return "" }
}

function Wait-PostgresHealthy {
    <#
    .SYNOPSIS
        Block until the compose `postgres` service reports healthy.
    .DESCRIPTION
        Resolves the container id through `docker compose ps -q`, so it does not
        depend on the generated container name.
    #>
    param([int]$TimeoutSeconds = 120)

    $deadline = (Get-Date).AddSeconds($TimeoutSeconds)
    while ($true) {
        $id = (docker compose ps -q postgres 2>$null | Select-Object -First 1)
        if ($id) {
            $state = (docker inspect -f '{{.State.Health.Status}}' $id 2>$null)
            if ($state -eq "healthy") { return }
            if ($state -eq "unhealthy") { throw "The postgres container reports unhealthy. Check 'docker compose logs postgres'." }
        }
        if ((Get-Date) -gt $deadline) {
            throw "Postgres did not become healthy within ${TimeoutSeconds}s. Check 'docker compose logs postgres'."
        }
        Start-Sleep -Seconds 2
    }
}
