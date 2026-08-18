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

.EXAMPLE
  pwsh -File setup_screenshot_pipeline.ps1 -PythonExe C:\Python313\python.exe
  # pin the interpreter when PATH resolution picks the wrong one (Store stub, broken install)
#>
[CmdletBinding()]
param(
    [string]$TaskName       = "WorkScreenshots",
    [string]$StartTime      = "08:30",
    [string]$EndTime        = "20:00",
    [int]   $IntervalSeconds = 150,
    [string]$ScreenshotsDir = "",
    [string]$CaptureScript  = "",

    # Pin the interpreter instead of probing PATH. Point it at a python.exe (or
    # pythonw.exe); it is probed like every other candidate, so a broken install
    # here is an error, not a silent fallback to whatever else is on PATH.
    [string]$PythonExe      = "",

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

# --- Resolve the Python interpreter -----------------------------------------
# Every candidate is PROBED with a real import, never taken on existence: both
# failure modes seen on a coworker's first install were interpreters that existed —
# the Windows Store app-execution alias (a 0-byte python.exe that runs nothing) and
# a split install whose executables had been separated from Lib\ (the stdlib still
# imports through a registry PythonPath, but sys.prefix — and with it pip and
# site-packages — resolves to garbage). Either one, taken on existence, registers a
# task that never captures anything.
function Test-UsablePython([string]$Exe) {
    if (-not $Exe -or -not (Test-Path $Exe)) { return $false }
    if ((Get-Item $Exe).Length -eq 0) { return $false }   # Store app-execution stub
    # Start-Process rather than &: pythonw is a GUI-subsystem exe, which & doesn't
    # wait on, leaving $LASTEXITCODE stale and the probe answering for the wrong run.
    $errFile = [System.IO.Path]::GetTempFileName()
    try {
        # The embedded quotes matter: Start-Process joins the list with spaces and no
        # quoting, and a bare `import sys,os` then reaches -c as just `import`.
        $p = Start-Process -FilePath $Exe -ArgumentList '-c', '"import sys,os"' `
            -Wait -PassThru -WindowStyle Hidden -RedirectStandardError $errFile
        if ($p.ExitCode -ne 0) { return $false }
        $err = Get-Content $errFile -Raw -ErrorAction SilentlyContinue
        # The split-install tell: exit 0 with this warning still means no usable prefix.
        return (-not ($err -match 'platform independent libraries'))
    } catch { return $false }
    finally { Remove-Item $errFile -ErrorAction SilentlyContinue }
}

if ($PythonExe) {
    if (-not (Test-UsablePython $PythonExe)) {
        throw "-PythonExe is not a usable Python (missing, a 0-byte Store stub, or it failed an import probe): $PythonExe"
    }
    $found = $PythonExe
} else {
    # The version-independent launcher first: the task action stores an absolute path,
    # so a versioned install directory moves on upgrade and every trigger then fails
    # 0x80070002, silently. The launcher survives reinstalls. PATH lookups come after,
    # because that's where the Store stub lives.
    $candidates = @(Join-Path $env:SystemRoot "py.exe")
    foreach ($name in "py.exe", "python.exe", "python3.exe") {
        $cmd = Get-Command $name -ErrorAction SilentlyContinue
        if ($cmd) { $candidates += $cmd.Source }
    }
    $candidates = $candidates | Select-Object -Unique
    $found = $null
    foreach ($c in $candidates) {
        if (Test-UsablePython $c) { $found = $c; break }
        if (Test-Path $c) { Write-Host "  skipping unusable interpreter: $c" }
    }
    if (-not $found) {
        throw ("No usable Python found. Probed: " + ($candidates -join ", ") +
               ". Install Python 3, or pass -PythonExe <path\to\python.exe>.")
    }
}

# Prefer the windowed sibling of whatever survived the probe, so no console flashes;
# pip and the import checks need the console exe. Siblings share an install, so the
# probe's verdict covers both.
$dir  = Split-Path $found
$base = [System.IO.Path]::GetFileNameWithoutExtension($found) -replace 'w$', ''
$conExe = Join-Path $dir "$base.exe"
$winExe = Join-Path $dir ($base + "w.exe")
$runExe = if ((Test-Path $winExe) -and (Get-Item $winExe).Length -gt 0) { $winExe } else { $conExe }
$pipExe = if (Test-Path $conExe) { $conExe } else { $found }

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
