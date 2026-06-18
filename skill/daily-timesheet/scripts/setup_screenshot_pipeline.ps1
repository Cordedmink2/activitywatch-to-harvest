<#
.SYNOPSIS
  Sets up the workday screenshot grabber: installs the Pillow dependency and
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
#>
[CmdletBinding()]
param(
    [string]$TaskName       = "WorkScreenshots",
    [string]$StartTime      = "08:30",
    [string]$EndTime        = "20:00",
    [int]   $IntervalSeconds = 150,
    [string]$ScreenshotsDir = (Join-Path $HOME "Pictures\WorkScreenshots"),
    [string]$CaptureScript  = (Join-Path $PSScriptRoot "screenshot_capture.py")
)

$ErrorActionPreference = "Stop"

# --- Resolve the Python interpreter (prefer pythonw so no console flashes) ---
$pyw = (Get-Command pythonw.exe -ErrorAction SilentlyContinue)?.Source
$py  = (Get-Command python.exe  -ErrorAction SilentlyContinue)?.Source
if (-not $pyw -and -not $py) { throw "Python not found on PATH. Install Python 3 first." }
$runExe = $pyw ?? $py
$pipExe = $py  ?? $pyw   # use python.exe for pip if available

Write-Host "Capture script : $CaptureScript"
Write-Host "Python (run)   : $runExe"
if (-not (Test-Path $CaptureScript)) { throw "Capture script not found: $CaptureScript" }

# --- Ensure Pillow is installed -------------------------------------------
Write-Host "Checking Pillow..."
& $pipExe -c "import PIL" 2>$null
if ($LASTEXITCODE -ne 0) {
    Write-Host "Installing Pillow (user scope)..."
    & $pipExe -m pip install --user --quiet Pillow
    if ($LASTEXITCODE -ne 0) { throw "Failed to install Pillow." }
}

# --- Build the trigger: weekly Mon-Fri, repeating every IntervalSeconds ----
$start    = [DateTime]::Parse($StartTime)
$end      = [DateTime]::Parse($EndTime)
$duration = $end - $start
if ($duration.TotalMinutes -le 0) { throw "EndTime must be after StartTime." }

$trigger = New-ScheduledTaskTrigger -Weekly `
    -DaysOfWeek Monday,Tuesday,Wednesday,Thursday,Friday -At $start
# Attach repetition by borrowing it from a throwaway -Once trigger (the standard
# PowerShell idiom — the Weekly trigger has no direct repetition parameter).
$rep = (New-ScheduledTaskTrigger -Once -At $start `
    -RepetitionInterval (New-TimeSpan -Seconds $IntervalSeconds) `
    -RepetitionDuration $duration).Repetition
$trigger.Repetition = $rep

$action    = New-ScheduledTaskAction -Execute $runExe -Argument "`"$CaptureScript`""
$principal = New-ScheduledTaskPrincipal -UserId "$env:USERDOMAIN\$env:USERNAME" `
    -LogonType Interactive -RunLevel Limited
$settings  = New-ScheduledTaskSettingsSet -AllowStartIfOnBatteries `
    -DontStopIfGoingOnBatteries -MultipleInstances IgnoreNew -StartWhenAvailable

Register-ScheduledTask -TaskName $TaskName -Trigger $trigger -Action $action `
    -Principal $principal -Settings $settings `
    -Description "Workday screenshot grabber for the daily-timesheet skill." -Force | Out-Null

New-Item -ItemType Directory -Force -Path $ScreenshotsDir | Out-Null

Write-Host ""
Write-Host "Registered '$TaskName': weekdays $StartTime-$EndTime, every ${IntervalSeconds}s -> $ScreenshotsDir"
Write-Host "Check status any time with:  Get-ScheduledTaskInfo -TaskName $TaskName"
