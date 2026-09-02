"""Shared Harvest API helper for the billables `daily` skill.

  load_creds() -> (account_id, api_key)
  request(method, path, body=None, query=None) -> dict (parsed JSON) or raises RuntimeError

Credentials are the one setting this module owns, because the pair of keys and the
message a first-run user gets are Harvest's business. *Where* a value comes from is not:
that is `skill_config`, which holds the precedence rule for every setting in the skill.
This module used to hold both, which meant the `.env`/OS-env walk existed twice — once in
`config()` and once, subtly its own way, in `load_creds()`.

If either HARVEST_ACCOUNT_ID or HARVEST_API_KEY fails to resolve, exits with a message
pointing at `.env.example`, through the shared error contract in `skill_config.fail_missing()`.

No third-party deps — uses stdlib `urllib` like the sibling `aw_*.py` helpers.
"""
import io
import json
import os
import sys
import urllib.error
import urllib.parse
import urllib.request

import skill_config

API_BASE = "https://api.harvestapp.com/v2"
USER_AGENT = "billables-daily-skill"

_CREDS_CACHE: tuple[str, str] | None = None


def use_utf8() -> None:
    """Make this process and its children speak UTF-8. Call it first thing in `main()`.

    Every script that prints Harvest data needs this: client and project names carry
    macrons and dashes that a console opened under a Windows codepage turns into a
    `UnicodeEncodeError` mid-report. `PYTHONIOENCODING` is set as well as the streams
    reconfigured because `refresh_catalogs` spawns `pac`, which inherits it.

    Lives here rather than in four copies at the top of four scripts — which is where it
    was, and the copies were module-scope statements, so merely importing any of those
    scripts rewrote the environment for every other module in the interpreter. A stream
    that is captured or redirected is not a `TextIOWrapper` and is left alone; a bare
    `reconfigure()` died with an `AttributeError` naming neither the script nor the cause.
    """
    os.environ["PYTHONIOENCODING"] = "utf-8"
    for stream in (sys.stdout, sys.stderr):
        if isinstance(stream, io.TextIOWrapper):
            stream.reconfigure(encoding="utf-8")


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


def load_creds() -> tuple[str, str]:
    """The Harvest account id and token, resolved through `skill_config.setting()`.

    Cached for the process: `harvest_list` makes one call per page, and re-resolving per
    request would both cost a file open apiece and make the credentials mutable mid-run,
    so a half-paged listing could start authenticating as a different account.
    """
    global _CREDS_CACHE
    if _CREDS_CACHE is not None:
        return _CREDS_CACHE
    acct = skill_config.setting("HARVEST_ACCOUNT_ID")
    key = skill_config.setting("HARVEST_API_KEY")
    if not acct or not key:
        # Two routes, plugin first: it is the one that does not leave a token in this
        # folder. Both fields are declared sensitive, so the harness keeps them in its own
        # credential store and hands them back as environment variables. The `.env` line
        # stays because the skill is also installable as the shared Agent Skills export,
        # which has no manifest and so no harness to ask.
        #
        # The "already configured?" line is the one that saves a support round trip: the
        # values arrive through a SessionStart hook, so a user who fills the dialog and
        # keeps typing in the same session sees exactly this message and reasonably
        # concludes the dialog did not work.
        skill_config.fail_missing(
            "Harvest credentials not found.\n"
            "  Run:  /plugin configure billables\n"
            "  and fill in HARVEST_ACCOUNT_ID and HARVEST_API_KEY — get both from\n"
            "  https://id.getharvest.com/developers.\n"
            "  Already configured them? Start a new session: the values are published at\n"
            "  session start. If a new session still shows this, see references/setup.md\n"
            "  § 'When the configuration does not arrive'.\n"
            f"  (Exported install instead? Copy {skill_config.SKILL_ROOT / '.env.example'}\n"
            f"   -> {skill_config.ENV_PATH} and put them there.)"
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
