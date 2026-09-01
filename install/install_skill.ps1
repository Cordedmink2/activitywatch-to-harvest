<#
.SYNOPSIS
  Generate the shared Agent Skills export from this plugin.

.DESCRIPTION
  Finds an interpreter and hands over to export_agent_skills.py, which is where the
  export and its rules are documented. It does nothing else: the plugin is installed
  with /plugin install, and a second install path that could drift from it is exactly
  what the export replaces.

.EXAMPLE
  pwsh -File install\install_skill.ps1
#>
[CmdletBinding()]
param(
  # The shared Agent Skills directory. Blank uses the exporter's own default, ~/.agents/skills.
  [string]$SkillsDir
)

$ErrorActionPreference = "Stop"

$export = Join-Path $PSScriptRoot "export_agent_skills.py"
$exportArgs = @($export)
if ($SkillsDir) { $exportArgs += $SkillsDir }

foreach ($candidate in @("py", "python", "python3")) {
  $found = Get-Command $candidate -ErrorAction SilentlyContinue
  if (-not $found) { continue }
  # Probed, not just found. A bare `python` on Windows is often the Store app-execution
  # alias: a 0-byte stub that prints an install nag and exits 49 without running anything.
  # Wrapped, because the 0-byte case cannot be launched at all — it raises rather than
  # exiting non-zero, and under `Stop` that ends the script instead of the candidate.
  try {
    & $found.Source -c "import sys" 2>$null | Out-Null
    if ($LASTEXITCODE -ne 0) { continue }
  } catch { continue }
  & $found.Source @exportArgs
  exit $LASTEXITCODE
}

throw "No usable Python on PATH. The export needs Python 3.10 or newer."
