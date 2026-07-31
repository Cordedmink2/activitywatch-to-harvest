"""
refresh_catalogs.py — refresh the Harvest project-assignment and Dataverse active-incident
caches used by the daily-timesheet skill.

Usage: python refresh_catalogs.py [--harvest-only | --dataverse-only]

Credentials come from the shared `harvest_client.load_creds()` helper: `.env` at
the skill root, or OS env vars.

Writes:
  - Work/.mcp/harvest_assignments.json          (page 1)
  - Work/.mcp/harvest_assignments_p2.json … _p7.json (subsequent pages)
  - Work/.mcp/dv_active_incidents.txt           (tabular output from pac env fetch)
"""

import argparse
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

os.environ["PYTHONIOENCODING"] = "utf-8"
sys.stdout.reconfigure(encoding="utf-8")

from harvest_client import request as harvest_request, _parse_env_file, ENV_PATH


def _config(key):
    """Read an optional setting from the skill `.env` file, falling back to OS env vars."""
    file_vals = _parse_env_file(ENV_PATH) if ENV_PATH.exists() else {}
    return file_vals.get(key) or os.environ.get(key)


def _resolve_workspace():
    """Locate the workspace root where `.mcp/` catalogs are written and read.

    This must land in the SAME directory the reader scripts read from, or refreshes
    silently write catalogs nowhere anyone looks. Resolution order:

    1. TIMESHEET_WORKSPACE (`.env` or OS env) — explicit wins.
    2. The current directory, if it already looks like a workspace (`.mcp/` or
       `Timesheets/`). Matches how the reader scripts (harvest_lookup) resolve it.
    3. Four levels up from this script, but only if THAT looks like a workspace —
       correct only when the skill is installed inside the workspace tree.

    If none look right, fail loudly. The alternative — deriving a path from the script's
    install location and writing there regardless — is exactly the bug this replaces: when
    the skill lives outside the workspace (e.g. ~/.claude/skills/), that path is not the
    workspace, and every refresh reports success while the reader keeps seeing stale data.
    """
    ws = _config("TIMESHEET_WORKSPACE")
    if ws:
        return Path(ws).expanduser()
    cwd = Path.cwd()
    if (cwd / ".mcp").is_dir() or (cwd / "Timesheets").is_dir():
        return cwd
    guess = Path(__file__).resolve().parents[3]
    if (guess / ".mcp").is_dir() or (guess / "Timesheets").is_dir():
        return guess
    sys.exit(
        "ERROR: can't locate your timesheet workspace (the directory holding .mcp/ and "
        "Timesheets/). Run this from that directory, or set TIMESHEET_WORKSPACE in the "
        "skill .env (or as an OS env var) to its absolute path."
    )


WORKSPACE = _resolve_workspace()
MCP_DIR = WORKSPACE / ".mcp"

# Dataverse incident catalog is OPTIONAL. Leave DATAVERSE_URL / PAC_AUTH_PROFILE unset in `.env`
# to skip it entirely — the Harvest refresh still runs. Set both to enable ticket-number
# resolution from your Dataverse org via the `pac` CLI.
DV_URL = _config("DATAVERSE_URL")
PAC_PROFILE = _config("PAC_AUTH_PROFILE")

INCIDENT_FETCHXML = """<fetch>
  <entity name="incident">
    <attribute name="ticketnumber" />
    <attribute name="title" />
    <attribute name="modifiedon" />
    <filter type="or">
      <condition attribute="statecode" operator="eq" value="0" />
      <condition attribute="modifiedon" operator="last-x-days" value="120" />
    </filter>
    <order attribute="ticketnumber" />
  </entity>
</fetch>
"""


def refresh_harvest():
    """Refresh the cached Harvest project-assignment catalog (best-effort).

    The endpoint is eventually consistent (see references/catalog-refresh.md → "Read-replica
    lag"): a just-created project may be missing and `total_entries` is not a reliable
    freshness signal. To bill a brand-new project, use wait_for_project() rather than trusting
    a single refresh.
    """
    MCP_DIR.mkdir(parents=True, exist_ok=True)

    # Fetch every page into memory BEFORE touching the existing files, so an API
    # failure mid-refresh leaves the old catalog intact rather than half-deleted.
    pages = []
    page = 1
    while True:
        try:
            payload = harvest_request(
                "GET",
                "/users/me/project_assignments",
                query={"per_page": 100, "page": page},
            )
        except RuntimeError as e:
            sys.exit(f"ERROR: Harvest API on page {page}: {e} (existing catalog left untouched)")
        pages.append(payload)
        if not payload.get("next_page"):
            break
        page += 1

    # Clear stale page files — if a prior run produced more pages than this one,
    # leftover _p{n}.json files would be read as stale data by consumers that
    # glob harvest_assignments*.json.
    for old in MCP_DIR.glob("harvest_assignments*.json"):
        old.unlink()

    for i, payload in enumerate(pages, start=1):
        out_name = "harvest_assignments.json" if i == 1 else f"harvest_assignments_p{i}.json"
        with open(MCP_DIR / out_name, "w", encoding="utf-8") as f:
            json.dump(payload, f, indent=2)
        n = len(payload.get("project_assignments", []))
        print(f"  ✓ Page {i}: {n} project assignments → {out_name}")

    total = payload.get("total_entries", "?")
    print(f"  Done. Total entries reported by Harvest: {total} (best-effort; see docstring on replica lag)")


def wait_for_project(code, attempts=20, delay=15):
    """Poll /users/me/project_assignments until `code` appears; return its assignment dict.

    Use this before billing to a freshly-created project/case — the bulk catalog refresh is
    eventually-consistent and may not show a brand-new code for a few minutes. Each attempt is
    an independent read (replica selection varies over time), so retrying across a span of
    minutes is what actually surfaces the new row. Returns the project_assignment dict, or None
    if it never showed up within attempts*delay seconds.
    """
    import time

    for i in range(attempts):
        page = 1
        while True:
            payload = harvest_request(
                "GET",
                "/users/me/project_assignments",
                query={"per_page": 100, "page": page},
            )
            for pa in payload.get("project_assignments", []):
                if (pa.get("project", {}).get("code") or "") == code:
                    return pa
            if not payload.get("next_page"):
                break
            page += 1
        if i < attempts - 1:
            time.sleep(delay)
    return None


def _active_pac_index(pac_cmd):
    """Return the index (str) of the currently-active pac auth profile, or None.

    Parsed from `pac auth list` — the active row is marked with `*`, e.g. `[6]   *  …`.
    Used so we can restore the user's profile after temporarily switching to PAC_PROFILE;
    otherwise every refresh silently leaves the active profile changed (a cause of
    cross-tenant 'profile drift').
    """
    res = subprocess.run([pac_cmd, "auth", "list"], capture_output=True, text=True)
    if res.returncode != 0:
        return None
    for line in res.stdout.splitlines():
        m = re.match(r"\s*\[(\d+)\]\s+\*", line)
        if m:
            return m.group(1)
    return None


def refresh_dataverse():
    if not DV_URL or not PAC_PROFILE:
        print(
            "  Skipping Dataverse refresh — DATAVERSE_URL and/or PAC_AUTH_PROFILE not set in .env.\n"
            "  (This is an optional feature; the Harvest catalog above is all most users need.)"
        )
        return

    pac_cmd = shutil.which("pac")
    if not pac_cmd:
        sys.exit("ERROR: pac CLI not on PATH. Install Power Platform CLI and retry.")

    MCP_DIR.mkdir(parents=True, exist_ok=True)
    out_path = MCP_DIR / "dv_active_incidents.txt"

    # Remember the user's active profile so we can restore it afterward.
    prior_index = _active_pac_index(pac_cmd)

    # Ensure the right profile is active
    sel = subprocess.run(
        [pac_cmd, "auth", "select", "--name", PAC_PROFILE],
        capture_output=True,
        text=True,
    )
    if sel.returncode != 0:
        sys.exit(f"ERROR: pac auth select failed:\n{sel.stdout}\n{sel.stderr}")

    with tempfile.NamedTemporaryFile("w", suffix=".xml", delete=False, encoding="utf-8") as tf:
        tf.write(INCIDENT_FETCHXML)
        xml_path = tf.name

    try:
        result = subprocess.run(
            [pac_cmd, "env", "fetch", "--xmlFile", xml_path, "--environment", DV_URL],
            capture_output=True,
            text=True,
        )
        if result.returncode != 0:
            sys.exit(f"ERROR: pac env fetch failed:\n{result.stdout}\n{result.stderr}")
        with open(out_path, "w", encoding="utf-8") as f:
            f.write(result.stdout)
        # Quick sanity check
        n_lines = sum(1 for _ in open(out_path, encoding="utf-8"))
        print(f"  ✓ {n_lines} lines written to {out_path.name}")
    finally:
        try:
            os.unlink(xml_path)
        except OSError:
            pass
        # Restore the user's original active profile (don't leave it on PAC_PROFILE).
        if prior_index:
            subprocess.run(
                [pac_cmd, "auth", "select", "--index", prior_index],
                capture_output=True,
                text=True,
            )


def main():
    parser = argparse.ArgumentParser(description="Refresh Harvest + Dataverse catalogs for daily-timesheet skill.")
    parser.add_argument("--harvest-only", action="store_true")
    parser.add_argument("--dataverse-only", action="store_true")
    args = parser.parse_args()

    if args.harvest_only and args.dataverse_only:
        sys.exit("Pick one of --harvest-only or --dataverse-only, not both.")

    if not args.dataverse_only:
        print("Refreshing Harvest project assignments…")
        refresh_harvest()

    if not args.harvest_only:
        print("Refreshing Dataverse active incidents…")
        refresh_dataverse()


if __name__ == "__main__":
    main()
