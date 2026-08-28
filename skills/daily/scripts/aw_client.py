"""Shared ActivityWatch REST helpers for the billables `daily` skill.

`afk_blocks.py` reads the day skeleton and `activity_timeline.py` reads its
content, but both talk to the same local AW server the same way: discover a
hostname-suffixed bucket, pull a day of events, collapse the heartbeats. Each
used to carry its own copy of that code, so a fix to one left the other wrong.

It also owns the two facts about *where and when* a day is read — the server's address and
the user's zone — because both scripts need them and neither should answer them its own
way. Both resolve through `skill_config`, so they arrive from wherever the user configured
them and nothing here knows about the harness.

No third-party deps - stdlib urllib, like the sibling harvest_*.py helpers.
"""
import datetime as dt
import json
import urllib.error
import urllib.request
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

import skill_config

DEFAULT_ACTIVITY_URL = "http://localhost:5600"


def resolve_base() -> str:
    """The `/api/0` prefix every request is built on, from `TIMESHEET_ACTIVITY_URL`.

    Optional, and its default is the answer for almost everyone: ActivityWatch runs on the
    machine you are typing on. It is declared configuration rather than a constant for the
    case it isn't — a second machine, a non-standard port — which used to mean editing an
    installed script that the next update overwrites.
    """
    base = skill_config.setting("TIMESHEET_ACTIVITY_URL", default=DEFAULT_ACTIVITY_URL)
    return base.rstrip("/") + "/api/0"


AW_BASE = resolve_base()


def resolve_utc_offset(flag, local_date):
    """The local zone's offset from UTC, in hours, for `local_date`.

    `flag` is whatever `--utc-offset` supplied, or None; it wins, so a day spent in
    another zone can still be reconstructed without reconfiguring anything. Otherwise the
    configured `TIMESHEET_TIMEZONE` is read at that date, which is what makes a day from
    the other side of a daylight-saving change come out right.

    There is deliberately no fallback. This used to be `default=12.0` in both scripts'
    argument parsers, so every user who was not in New Zealand got a day boundary up to
    twelve hours out — and nothing failed: the events landed on the wrong date and the
    only symptom was a day that looked oddly short. No offset is safe to guess, so an
    unconfigured run stops and says which value it needs.

    The offset is read at local noon, not local midnight: midnight is where a transition
    lands, and asking there is asking the ambiguous question. One offset for the whole day
    is still an approximation across a transition — issue #8 owns that.
    """
    if flag is not None:
        return flag
    name = skill_config.setting("TIMESHEET_TIMEZONE")
    if not name:
        skill_config.fail_missing(
            "No timezone configured, and no --utc-offset given.\n"
            "  A day's boundaries depend on your zone, so there is nothing safe to assume.\n"
            "  Set it once:  /plugin configure billables  -> TIMESHEET_TIMEZONE\n"
            "                (an IANA name, e.g. Europe/London or Pacific/Auckland)\n"
            "  Already set it? Start a new session — the value is published at session\n"
            "  start. If a new session still shows this, see references/setup.md\n"
            "  § 'When the configuration does not arrive'.\n"
            "  Or for this run only:  --utc-offset <hours>")
    try:
        zone = ZoneInfo(name)
    except (ZoneInfoNotFoundError, ValueError) as exc:
        skill_config.fail_missing(
            f"Could not load the timezone '{name}' ({exc}).\n"
            "  Check it against the IANA list (e.g. Europe/London, Pacific/Auckland).\n"
            "  On Windows the zone database is a separate install:  pip install tzdata\n"
            "  Or bypass it for this run:  --utc-offset <hours>")
    noon = dt.datetime.combine(local_date, dt.time(12, 0), tzinfo=zone)
    return noon.utcoffset().total_seconds() / 3600


def get(path):
    try:
        with urllib.request.urlopen(AW_BASE + path, timeout=15) as r:
            return json.load(r)
    except urllib.error.HTTPError as e:
        # An HTTPError never reaches the `with`, so its response body is left open. That
        # matters most for the settings endpoint, whose absence load_classes() swallows
        # by design — nothing downstream ever sees the object to close it.
        e.close()
        raise


def pick_bucket(buckets, prefix):
    """Bucket id starting with `prefix`, or None. Prefers a hostname-suffixed match
    over an unsuffixed leftover; among suffixed candidates, breaks ties by
    `last_updated` so a stale post-reimage bucket loses to the actively-reporting
    host. Takes an already-fetched `{bucket_id: {...}}` listing (as returned by
    `GET /buckets/`) so a caller wanting several buckets pays for one such call
    rather than one per prefix."""
    cands = [b for b in buckets if b.startswith(prefix)]
    if not cands:
        return None
    return max(cands, key=lambda b: ("_" in b, buckets[b].get("last_updated") or ""))


def fetch_events(bucket, start_utc, end_utc):
    """Events in the range. `bucket` may be None: the web watchers are optional, so
    discovery legitimately finds nothing for them."""
    if not bucket:
        return []
    return get(f"/buckets/{bucket}/events?start={start_utc}&end={end_utc}&limit=10000")


def dedupe_heartbeats(events):
    """AW extends an ongoing event by re-emitting it with the same timestamp and a
    longer duration. Keep the longest duration per timestamp so we don't double-count."""
    best = {}
    for e in events:
        ts = e["timestamp"]
        if ts not in best or e["duration"] > best[ts]["duration"]:
            best[ts] = e
    return sorted(best.values(), key=lambda e: e["timestamp"])


def parse_ts(ts):
    return dt.datetime.fromisoformat(ts.replace("Z", "+00:00"))


def parse_local_time(s):
    """Parse 'HH:MM' or 'HH:MM:SS' to a datetime.time."""
    s = s.strip()
    fmt = "%H:%M:%S" if s.count(":") == 2 else "%H:%M"
    return dt.datetime.strptime(s, fmt).time()


def parse_range(rng, local_date, offset):
    """Parse a local 'HH:MM-HH:MM' (seconds optional) to an aware UTC (start, end) pair.

    Raises ValueError on a bad format or a reversed/empty range. Shared because both
    scripts take a `--window` in this shape and each used to parse it its own way: the
    afk one rejected `17:00-09:00`, the timeline one accepted it and printed an empty
    result, so the same typo produced an error in one script and a plausible-looking
    "nothing happened then" in the other.
    """
    a, b = rng.split("-", 1)
    local_start = dt.datetime.combine(local_date, parse_local_time(a))
    local_end = dt.datetime.combine(local_date, parse_local_time(b))
    ws = (local_start - offset).replace(tzinfo=dt.timezone.utc)
    we = (local_end - offset).replace(tzinfo=dt.timezone.utc)
    if we <= ws:
        raise ValueError(f"end must be after start in range '{rng}'")
    return ws, we


def utc_bounds(local_date, offset):
    """The local day as the Z-suffixed UTC strings the AW events API wants."""
    local_start = dt.datetime.combine(local_date, dt.time(0, 0))
    return ((local_start - offset).strftime("%Y-%m-%dT%H:%M:%SZ"),
            (local_start + dt.timedelta(days=1) - offset).strftime("%Y-%m-%dT%H:%M:%SZ"))
