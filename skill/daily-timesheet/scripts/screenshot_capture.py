"""
screenshot_capture.py
---------------------
Takes one screenshot PER MONITOR and saves them into a dated folder. Designed
to be fired by a Windows Task Scheduler trigger every ~2.5 minutes across the
workday. Run it with pythonw.exe (not python.exe) so no console window flashes.

`setup_screenshot_pipeline.ps1` (next to this file) registers the scheduled
task and installs the mss + Pillow dependencies; you normally don't run this
by hand.

Folder structure it produces (one file per monitor, left-to-right):
  SCREENSHOTS_DIR\
    2026-06-19\
      08-30-01_m1.png
      08-30-01_m2.png
      08-30-01_m3.png
    capture.log          (append-only; errors land here since there's no console)

Per-monitor files stay at native resolution, so window titles and code remain
readable when opened — a single stitched ultra-wide PNG gets downsampled to
mush. Laptop-only days produce just _m1.png.

Dependencies: mss (monitor enumeration + grab) and Pillow (PNG save). The setup
script installs both if missing.
"""

import os
import sys
import datetime

# Under pythonw.exe there is no console: sys.stdout / sys.stderr are None and
# any print() would crash. Redirect them to a log file so prints are safe.
if sys.stdout is None or sys.stderr is None:
    _log_dir = os.path.join(os.path.expanduser("~"), "Pictures", "WorkScreenshots")
    os.makedirs(_log_dir, exist_ok=True)
    _log_fh = open(os.path.join(_log_dir, "capture.log"), "a", encoding="utf-8", buffering=1)
    sys.stdout = _log_fh
    sys.stderr = _log_fh

# mss / Pillow are imported lazily inside take_screenshots() so this module
# stays importable (and order_monitors stays unit-testable) on machines where
# only pytest is installed.

# -- Configuration ----------------------------------------------------------
SCREENSHOTS_DIR = os.path.join(os.path.expanduser("~"), "Pictures", "WorkScreenshots")
# ---------------------------------------------------------------------------


def order_monitors(monitors):
    """Given mss's sct.monitors list, drop the virtual all-screens box (index 0)
    and return the real monitors ordered left-to-right by their 'left' edge."""
    real = monitors[1:] if len(monitors) > 1 else monitors
    return sorted(real, key=lambda m: m["left"])


def take_screenshots():
    today = datetime.date.today().strftime("%Y-%m-%d")
    folder = os.path.join(SCREENSHOTS_DIR, today)
    os.makedirs(folder, exist_ok=True)
    timestamp = datetime.datetime.now().strftime("%H-%M-%S")

    import mss
    from PIL import Image

    saved = []
    with mss.MSS() as sct:
        for n, mon in enumerate(order_monitors(sct.monitors), start=1):
            shot = sct.grab(mon)
            img = Image.frombytes("RGB", shot.size, shot.bgra, "raw", "BGRX")
            filepath = os.path.join(folder, f"{timestamp}_m{n}.png")
            img.save(filepath, optimize=True)
            saved.append(filepath)

    print(f"[{datetime.datetime.now().strftime('%H:%M:%S')}] Saved {len(saved)} monitor(s) -> {folder}")
    return saved


if __name__ == "__main__":
    try:
        take_screenshots()
        sys.exit(0)
    except Exception as e:
        print(f"ERROR: {e}", file=sys.stderr)
        sys.exit(1)
