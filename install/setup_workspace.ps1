<#
.SYNOPSIS
  Scaffold a workspace for the daily-timesheet skill.

.DESCRIPTION
  Creates the folders the skill reads/writes (Timesheets\, daily_exports\, .mcp\)
  in the chosen workspace, and seeds Timesheets\.context.md from the bundled
  template if it doesn't already exist. Never overwrites an existing .context.md.

.EXAMPLE
  pwsh -File install\setup_workspace.ps1
  pwsh -File install\setup_workspace.ps1 -Workspace C:\Users\me\Work
#>
[CmdletBinding()]
param(
  # Workspace root. Defaults to the current directory.
  [string]$Workspace = (Get-Location).Path
)

$ErrorActionPreference = "Stop"

$repoRoot = Split-Path -Parent $PSScriptRoot
$template = Join-Path $repoRoot "skill\daily-timesheet\references\context.md.example"

Write-Host "Scaffolding workspace at: $Workspace" -ForegroundColor Cyan

foreach ($d in @("Timesheets", "daily_exports", ".mcp")) {
  $path = Join-Path $Workspace $d
  New-Item -ItemType Directory -Force -Path $path | Out-Null
  Write-Host "  created  $d\"
}

$contextDest = Join-Path $Workspace "Timesheets\.context.md"
if (Test-Path $contextDest) {
  Write-Host "  kept     Timesheets\.context.md (already exists - not overwritten)" -ForegroundColor Yellow
} elseif (Test-Path $template) {
  Copy-Item $template $contextDest
  Write-Host "  seeded   Timesheets\.context.md (from template - edit it next)" -ForegroundColor Green
} else {
  Write-Host "  WARNING  template not found at $template; create Timesheets\.context.md by hand" -ForegroundColor Red
}

Write-Host ""
Write-Host "Done. Now open Timesheets\.context.md and fill in your clients, colleagues," -ForegroundColor Yellow
Write-Host "ticket prefixes, timezone, and billing style. See the README for a walkthrough."
