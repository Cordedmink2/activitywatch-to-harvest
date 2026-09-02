"""
screenshot_capture.py
---------------------
Takes one screenshot PER MONITOR and saves them into a dated folder. Designed
to be fired by a Windows Task Scheduler trigger every ~2.5 minutes across the
workday. Run it with pythonw.exe (not python.exe) so no console window flashes.

`setup_screenshot_pipeline.ps1` (next to this file) registers the scheduled
task and installs the mss + Pillow dependencies; you normally don't run this
by hand.

Output directory: first positional argument, else TIMESHEET_SCREENSHOTS_DIR,
else ~/Pictures/WorkScreenshots — resolved by `skill_config`, which owns the
precedence between a flag, the skill `.env` and the process environment.

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

from skill_config import setting

DEFAULT_SCREENSHOTS_DIR = os.path.join(os.path.expanduser("~"), "Pictures", "WorkScreenshots")


def resolve_screenshots_dir(argv):
    """Where to write: the first positional argument, else TIMESHEET_SCREENSHOTS_DIR,
    else ~/Pictures/WorkScreenshots.

    The scheduled task registered by setup_screenshot_pipeline.ps1 passes its
    -ScreenshotsDir as that argument. Merging the argument with the setting is the
    standard flag-beats-configuration order, so it is `skill_config`'s to apply rather
    than this script's — including the rule that a blank argument, which Task Scheduler
    hands through for an omitted one, does not count as a value.

    `expanduser` because a configured value is typed by a person. `~/Pictures/Shots` from
    a `.env` used to be taken literally, so the capture wrote to a directory *named* `~`
    under whatever the task's working directory happened to be, and every reader looked
    somewhere else — the same reader/writer divergence `--where` below exists to close,
    arrived at from the other end. The default is already absolute.
    """
    resolved = setting("TIMESHEET_SCREENSHOTS_DIR",
                       flag=argv[0] if argv else None,
                       default=DEFAULT_SCREENSHOTS_DIR)
    return os.path.expanduser(resolved)


# mss / Pillow are imported lazily inside take_screenshots() so this module
# stays importable (and order_monitors stays unit-testable) on machines where
# only pytest is installed.


def order_monitors(monitors):
    """Given mss's sct.monitors list, drop the virtual all-screens box (index 0)
    and return the real monitors ordered left-to-right by their 'left' edge."""
    real = monitors[1:] if len(monitors) > 1 else monitors
    return sorted(real, key=lambda m: m["left"])


def take_screenshots(dest):
    today = datetime.date.today().strftime("%Y-%m-%d")
    folder = os.path.join(dest, today)
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


WHERE_FLAG = "--where"


if __name__ == "__main__":
    if WHERE_FLAG in sys.argv[1:]:
        # Print where captures go and take none. The three skills need this value to
        # build a PowerShell listing command, and PowerShell is the one shell the
        # configuration is not published to — so they resolve it here, in a Bash tool
        # call, and paste the answer. `echo "$TIMESHEET_SCREENSHOTS_DIR"` is the obvious
        # thing to reach for and is wrong: it reads the process environment alone, which
        # is one of four layers and not the one an exported install keeps this value in.
        # Nothing sensitive can come out of here — this key is a path, and no other key
        # is reachable through this flag.
        print(resolve_screenshots_dir([a for a in sys.argv[1:] if a != WHERE_FLAG]))
        sys.exit(0)

    dest = resolve_screenshots_dir(sys.argv[1:])

    # Under pythonw.exe there is no console: sys.stdout / sys.stderr are None and
    # any print() would crash. Redirect them to a log file so prints are safe.
    if sys.stdout is None or sys.stderr is None:
        os.makedirs(dest, exist_ok=True)
        _log_fh = open(os.path.join(dest, "capture.log"), "a", encoding="utf-8", buffering=1)
        sys.stdout = _log_fh
        sys.stderr = _log_fh

    try:
        take_screenshots(dest)
        sys.exit(0)
    except Exception as e:
        print(f"ERROR: {e}", file=sys.stderr)
        sys.exit(1)
