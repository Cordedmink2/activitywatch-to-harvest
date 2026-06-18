"""
screenshot_capture.py
---------------------
Takes a single screenshot and saves it into a dated folder. Designed to be
fired by a Windows Task Scheduler trigger every ~2.5 minutes across the
workday (08:30-20:00 weekdays). Run it with pythonw.exe (not python.exe) so
no console window flashes on each fire.

`setup_screenshot_pipeline.ps1` (next to this file) registers the scheduled
task that calls this script; you normally don't run this by hand.

Folder structure it produces:
  SCREENSHOTS_DIR\
    2026-05-29\
      08-30-01.png
      08-32-31.png
      ...
    capture.log          (append-only; errors land here since there's no console)

Dependency: Pillow (PIL). The setup script installs it if missing.
"""

import os
import sys
import datetime

# Under pythonw.exe there is no console: sys.stdout / sys.stderr are None and
# any print() would crash. Redirect them to a log file under the screenshots
# dir so prints are safe and failures stay visible.
if sys.stdout is None or sys.stderr is None:
    _log_dir = os.path.join(os.path.expanduser("~"), "Pictures", "WorkScreenshots")
    os.makedirs(_log_dir, exist_ok=True)
    _log_fh = open(os.path.join(_log_dir, "capture.log"), "a", encoding="utf-8", buffering=1)
    sys.stdout = _log_fh
    sys.stderr = _log_fh

from PIL import ImageGrab

# -- Configuration ----------------------------------------------------------
# Change this path if you want screenshots stored somewhere else. Keep it in
# sync with the path the daily-timesheet skill reads from.
SCREENSHOTS_DIR = os.path.join(
    os.path.expanduser("~"), "Pictures", "WorkScreenshots"
)
# ---------------------------------------------------------------------------


def take_screenshot():
    today = datetime.date.today().strftime("%Y-%m-%d")
    folder = os.path.join(SCREENSHOTS_DIR, today)
    os.makedirs(folder, exist_ok=True)

    timestamp = datetime.datetime.now().strftime("%H-%M-%S")
    filepath = os.path.join(folder, f"{timestamp}.png")

    screenshot = ImageGrab.grab(all_screens=True)  # captures all monitors
    screenshot.save(filepath, optimize=True)

    print(f"[{datetime.datetime.now().strftime('%H:%M:%S')}] Saved -> {filepath}")
    return filepath


if __name__ == "__main__":
    try:
        take_screenshot()
        sys.exit(0)
    except Exception as e:
        print(f"ERROR: {e}", file=sys.stderr)
        sys.exit(1)
