<#
.SYNOPSIS
  Install the billables `daily` skill into your Claude Code skills folder.

.DESCRIPTION
  Copies skills\daily from this repo to ~\.claude\skills\daily.
  Never copies a .env (yours stays local) or __pycache__. Safe to re-run - it
  refreshes the skill files in place.

.EXAMPLE
  pwsh -File install\install_skill.ps1
#>
[CmdletBinding()]
param(
  # Where Claude Code looks for global skills. Override only if yours is non-standard.
  [string]$SkillsDir = (Join-Path $HOME ".claude\skills")
)

$ErrorActionPreference = "Stop"

$repoRoot = Split-Path -Parent $PSScriptRoot
$source   = Join-Path $repoRoot "skills\daily"
$dest     = Join-Path $SkillsDir "daily"

if (-not (Test-Path $source)) {
  throw "Cannot find skill source at: $source"
}

New-Item -ItemType Directory -Force -Path $SkillsDir | Out-Null

$version = (Get-Content (Join-Path $source "VERSION") -Raw).Trim()

Write-Host "Installing the billables daily skill v$version..." -ForegroundColor Cyan
Write-Host "  from: $source"
Write-Host "  to:   $dest"

# robocopy mirrors the tree; /XF .env keeps any local secrets out, /XD skips build
# and test scratch directories. Exit codes 0-7 are success for robocopy; 8+ are real errors.
robocopy $source $dest /E /XF .env /XD __pycache__ .pytest_cache | Out-Null
if ($LASTEXITCODE -ge 8) { throw "robocopy failed with exit code $LASTEXITCODE" }

Write-Host "Done. daily v$version installed to $dest" -ForegroundColor Green

# The skill used to install under its old name. Left in place it is a second, stale copy
# of the same skill, and either one can answer.
$stale = Join-Path $SkillsDir "daily-timesheet"
if (Test-Path $stale) {
  Write-Host ""
  Write-Host "NOTE: an older copy of this skill is still at $stale." -ForegroundColor Yellow
  Write-Host "      Move any .env you filled in there across, then delete that folder."
}

Write-Host ""
Write-Host "Next steps:" -ForegroundColor Yellow
Write-Host "  1. Scaffold your workspace:  pwsh -File install\setup_workspace.ps1"
Write-Host "  2. Add your Harvest creds:   copy '$dest\.env.example' to '$dest\.env' and fill it in"
Write-Host "  3. Set up screenshots:       pwsh -File '$dest\scripts\setup_screenshot_pipeline.ps1'"
