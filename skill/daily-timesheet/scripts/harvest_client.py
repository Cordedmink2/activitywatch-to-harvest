"""Shared Harvest API and configuration helper for the daily-timesheet skill.

  load_creds() -> (account_id, api_key)
  request(method, path, body=None, query=None) -> dict (parsed JSON) or raises RuntimeError
  config(key) -> str | None            — optional setting from `.env`, else OS env
  find_workspace() -> Path | None      — the directory holding `.mcp/`

Credentials resolution order:
  1. `.env` file at the skill root (next to SKILL.md). Simple `KEY=VALUE` lines,
     blank lines and `#` comments allowed.
  2. Process environment variables.

If neither yields both HARVEST_ACCOUNT_ID and HARVEST_API_KEY, exits with a
message pointing at `.env.example`.

No third-party deps — uses stdlib `urllib` like the sibling `aw_*.py` helpers.
"""
import json
import os
import sys
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

SKILL_ROOT = Path(__file__).resolve().parents[1]
ENV_PATH = SKILL_ROOT / ".env"
API_BASE = "https://api.harvestapp.com/v2"
USER_AGENT = "daily-timesheet-skill"

_CREDS_CACHE: tuple[str, str] | None = None


def parse_time_to_minutes(t: str) -> int:
    """Parse a Harvest-style time string ('8:15am', '08:15', '12:30pm') to minutes-since-midnight.

    Raises ValueError on unparseable or out-of-range input. Used by harvest_post.py and
    harvest_patch.py to block reversed-time / zero-duration entries before they reach
    Harvest — the API otherwise silently stores `10:00-09:00` as a 23-hour block.
    """
    raw = t.strip().lower()
    suffix = ""
    if raw.endswith("am") or raw.endswith("pm"):
        suffix = raw[-2:]
        raw = raw[:-2].strip()
    try:
        h_str, m_str = raw.split(":")
        h, m = int(h_str), int(m_str)
    except (ValueError, IndexError):
        raise ValueError(f"cannot parse time: {t!r}")
    if suffix == "pm" and h != 12:
        h += 12
    if suffix == "am" and h == 12:
        h = 0
    if not (0 <= h < 24 and 0 <= m < 60):
        raise ValueError(f"time out of range: {t!r}")
    return h * 60 + m


def _parse_env_file(path: Path) -> dict:
    out = {}
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        if "=" not in line:
            continue
        k, _, v = line.partition("=")
        v = v.strip()
        if (v.startswith('"') and v.endswith('"')) or (v.startswith("'") and v.endswith("'")):
            v = v[1:-1]
        out[k.strip()] = v
    return out


def config(key: str) -> str | None:
    """Read an optional setting from the skill `.env`, falling back to OS env vars.

    Returns None when the key is unset anywhere; callers decide whether that is fatal.
    """
    file_vals = _parse_env_file(ENV_PATH) if ENV_PATH.exists() else {}
    return file_vals.get(key) or os.environ.get(key)


def find_workspace() -> Path | None:
    """Locate the workspace root holding the `.mcp/` catalogs, or None if it can't be found.

    The writer (refresh_catalogs.py) and the readers (harvest_lookup.py) both resolve
    the workspace through here, so a refresh cannot write catalogs into one directory
    while a lookup reads another. Resolution order:

    1. TIMESHEET_WORKSPACE, from the skill `.env` or an OS env var — explicit wins.
    2. The current directory, if it already looks like a workspace (`.mcp/` or `Timesheets/`).
    3. The directories the skill is installed under, if one looks like a workspace. Two
       install shapes are checked: `<workspace>/skills/<name>` and Claude Code's own
       `<workspace>/.claude/skills/<name>`, which sits one level deeper. Checking only the
       first meant auto-detection could never succeed on a stock install, while
       `.env.example` promised that it would.

    Returning None instead of guessing is deliberate: deriving a path from the install
    location and using it regardless is how refreshes used to report success while
    writing catalogs nowhere the reader would look.
    """
    ws = config("TIMESHEET_WORKSPACE")
    if ws:
        return Path(ws).expanduser()
    for cand in (Path.cwd(), *SKILL_ROOT.parents[1:3]):
        if (cand / ".mcp").is_dir() or (cand / "Timesheets").is_dir():
            return cand
    return None


def load_creds() -> tuple[str, str]:
    global _CREDS_CACHE
    if _CREDS_CACHE is not None:
        return _CREDS_CACHE
    file_creds = _parse_env_file(ENV_PATH) if ENV_PATH.exists() else {}
    acct = file_creds.get("HARVEST_ACCOUNT_ID") or os.environ.get("HARVEST_ACCOUNT_ID")
    key = file_creds.get("HARVEST_API_KEY") or os.environ.get("HARVEST_API_KEY")
    if not acct or not key:
        sys.exit(
            "ERROR: Harvest credentials not found.\n"
            f"  Copy {SKILL_ROOT / '.env.example'} -> {ENV_PATH}\n"
            "  and fill in HARVEST_ACCOUNT_ID and HARVEST_API_KEY.\n"
            "  (Or set them as OS environment variables.)"
        )
    _CREDS_CACHE = (acct, key)
    return _CREDS_CACHE


def request(method: str, path: str, body=None, query=None):
    acct, key = load_creds()
    url = f"{API_BASE}/{path.lstrip('/')}"
    if query:
        cleaned = {k: v for k, v in query.items() if v is not None}
        if cleaned:
            url = f"{url}?{urllib.parse.urlencode(cleaned)}"

    data = json.dumps(body).encode("utf-8") if body is not None else None
    req = urllib.request.Request(url, data=data, method=method.upper())
    req.add_header("Harvest-Account-Id", acct)
    req.add_header("Authorization", f"Bearer {key}")
    req.add_header("User-Agent", USER_AGENT)
    if body is not None:
        req.add_header("Content-Type", "application/json")

    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            text = resp.read().decode("utf-8")
            return json.loads(text) if text else {}
    except urllib.error.HTTPError as e:
        # HTTPError *is* the response: it owns a spooled temp file that stays open until
        # its destructor runs. Closing it here keeps a run of failed calls from leaking a
        # handle apiece — and keeps the collector from raising a ResourceWarning later,
        # from a stack with no relationship to the request that caused it.
        with e:
            body_text = e.read().decode("utf-8", "replace")[:300]
        raise RuntimeError(f"{e.code} {body_text}") from None
    except urllib.error.URLError as e:
        raise RuntimeError(f"network error: {e}") from None
