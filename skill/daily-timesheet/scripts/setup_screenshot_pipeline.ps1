<#
.SYNOPSIS
  Sets up the workday screenshot grabber: installs the Pillow + mss dependencies and
  registers ONE Windows scheduled task that fires screenshot_capture.py every
  ~2.5 minutes across the workday.

.DESCRIPTION
  This is the only screenshot task the daily-timesheet skill needs. It runs as
  the current (non-admin) user while you're logged in, capturing into
  ~/Pictures/WorkScreenshots/<date>/. The capture script creates the dated
  folders itself, so there's no separate folder-structure step.

  Re-running is safe: -Force replaces any existing task of the same name.

.EXAMPLE
  pwsh -File setup_screenshot_pipeline.ps1
  # default: WorkScreenshots, weekdays 08:30-20:00, every 150s

.EXAMPLE
  pwsh -File setup_screenshot_pipeline.ps1 -StartTime 09:00 -EndTime 18:00 -IntervalSeconds 300

.EXAMPLE
  pwsh -File setup_screenshot_pipeline.ps1 -DryRun
  # prints the task it would register and exits; installs nothing, registers nothing
#>
[CmdletBinding()]
param(
    [string]$TaskName       = "WorkScreenshots",
    [string]$StartTime      = "08:30",
    [string]$EndTime        = "20:00",
    [int]   $IntervalSeconds = 150,
    [string]$ScreenshotsDir = "",
    [string]$CaptureScript  = "",

    # Build and report the task definition without installing packages or registering
    # it. The capture directory is still created: whether it can be is part of what a
    # dry run is checking, and the real run has to fail there before it registers.
    [switch]$DryRun
)

$ErrorActionPreference = "Stop"

# Resolved here, not as param() defaults: Windows PowerShell 5.1 leaves $PSScriptRoot
# empty while binding parameters, so a default built from it fails before the script runs.
if (-not $CaptureScript)  { $CaptureScript  = Join-Path $PSScriptRoot "screenshot_capture.py" }
if (-not $ScreenshotsDir) { $ScreenshotsDir = Join-Path $env:USERPROFILE "Pictures\WorkScreenshots" }

# --- Resolve the Python interpreter (prefer pythonw so no console flashes) ---
# Spelled out with if/else rather than ?. and ?? so this parses under Windows
# PowerShell 5.1, which is all a stock Windows box has.
$pywCmd = Get-Command pythonw.exe -ErrorAction SilentlyContinue
$pyCmd  = Get-Command python.exe  -ErrorAction SilentlyContinue
$pyw = if ($pywCmd) { $pywCmd.Source } else { $null }
$py  = if ($pyCmd)  { $pyCmd.Source }  else { $null }
if (-not $pyw -and -not $py) { throw "Python not found on PATH. Install Python 3 first." }
$runExe = if ($pyw) { $pyw } else { $py }
$pipExe = if ($py)  { $py }  else { $pyw }   # use python.exe for pip if available

Write-Host "Capture script : $CaptureScript"
Write-Host "Python (run)   : $runExe"
if (-not (Test-Path $CaptureScript)) { throw "Capture script not found: $CaptureScript" }

# --- Ensure Pillow and mss are installed (mss does the per-monitor capture) ---
foreach ($pkg in @("PIL:Pillow", "mss:mss")) {
    $importName, $pipName = $pkg -split ":"
    Write-Host "Checking $pipName..."
    & $pipExe -c "import $importName" 2>$null
    if ($LASTEXITCODE -ne 0) {
        if ($DryRun) { Write-Host "  would install $pipName (user scope)"; continue }
        Write-Host "Installing $pipName (user scope)..."
        & $pipExe -m pip install --user --quiet $pipName
        if ($LASTEXITCODE -ne 0) { throw "Failed to install $pipName." }
    }
}

# --- Build the trigger: weekly Mon-Fri, repeating every IntervalSeconds ----
$start    = [DateTime]::Parse($StartTime)
$end      = [DateTime]::Parse($EndTime)
$duration = $end - $start
if ($duration.TotalMinutes -le 0) { throw "EndTime must be after StartTime." }

$trigger = New-ScheduledTaskTrigger -Weekly `
    -DaysOfWeek Monday,Tuesday,Wednesday,Thursday,Friday -At $start
# Attach repetition by borrowing it from a throwaway -Once trigger (the standard
# PowerShell idiom - the Weekly trigger has no direct repetition parameter).
$rep = (New-ScheduledTaskTrigger -Once -At $start `
    -RepetitionInterval (New-TimeSpan -Seconds $IntervalSeconds) `
    -RepetitionDuration $duration).Repetition
$trigger.Repetition = $rep

$action    = New-ScheduledTaskAction -Execute $runExe -Argument "`"$CaptureScript`" `"$ScreenshotsDir`""
$principal = New-ScheduledTaskPrincipal -UserId "$env:USERDOMAIN\$env:USERNAME" `
    -LogonType Interactive -RunLevel Limited
$settings  = New-ScheduledTaskSettingsSet -AllowStartIfOnBatteries `
    -DontStopIfGoingOnBatteries -MultipleInstances IgnoreNew -StartWhenAvailable

# Before registering, so an unusable -ScreenshotsDir fails without leaving a task
# behind that captures into a directory nothing created.
New-Item -ItemType Directory -Force -Path $ScreenshotsDir | Out-Null

if ($DryRun) {
    # Reported off the built objects, not the variables that fed them, so the report
    # reflects what would actually be registered - argument quoting included.
    Write-Host ""
    Write-Host "DRYRUN Task name           : $TaskName"
    Write-Host "DRYRUN Execute             : $($action.Execute)"
    Write-Host "DRYRUN Arguments           : $($action.Arguments)"
    Write-Host "DRYRUN Days bitmask        : $($trigger.DaysOfWeek)   (Sunday = 1, doubling to Saturday = 64)"
    Write-Host "DRYRUN Start boundary      : $($trigger.StartBoundary)"
    Write-Host "DRYRUN Repetition interval : $($trigger.Repetition.Interval)"
    Write-Host "DRYRUN Repetition duration : $($trigger.Repetition.Duration)"
    Write-Host "DRYRUN Screenshots dir     : $ScreenshotsDir"
    Write-Host ""
    Write-Host "Dry run: nothing installed, no task registered."
    exit 0
}

Register-ScheduledTask -TaskName $TaskName -Trigger $trigger -Action $action `
    -Principal $principal -Settings $settings `
    -Description "Workday screenshot grabber for the daily-timesheet skill." -Force | Out-Null

Write-Host ""
Write-Host "Registered '$TaskName': weekdays $StartTime-$EndTime, every ${IntervalSeconds}s -> $ScreenshotsDir"
Write-Host "Check status any time with:  Get-ScheduledTaskInfo -TaskName $TaskName"
