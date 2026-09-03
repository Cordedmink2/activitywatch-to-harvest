"""Shared ActivityWatch REST helpers for the billables `daily` skill.

`afk_blocks.py` reads the day skeleton and `activity_timeline.py` reads its
content, but both talk to the same local AW server the same way: discover a
hostname-suffixed bucket, pull a day of events, collapse the heartbeats. Each
used to carry its own copy of that code, so a fix to one left the other wrong.

It also owns the one fact about *where* a day is read — the server's address — because
both scripts need it and neither should answer it its own way. It resolves through
`skill_config`, so it arrives from wherever the user configured it and nothing here knows
about the harness.

*When* a day is read is `timezone.py`'s, and was this module's until #36: the provider
scripts need the same arithmetic and were importing this client to get at it. Everything
about a zone or a clock reading is there — `resolve_zone()`, `utc_bounds()`,
`local_clock()`, `parse_range()` — and the two day-reading scripts import it directly.

No third-party deps - stdlib urllib, like the sibling harvest_*.py helpers.
"""
import datetime as dt
import json
import urllib.error
import urllib.request

import skill_config

DEFAULT_ACTIVITY_URL = "http://localhost:5600"


class UsageError(ValueError):
    """A flag value a day-reading script cannot act on — a `--window` or `--cover` that
    does not parse. Carries the message `main()` prints after `ERR `; the exit code stays
    `main()`'s to decide, and the function that raised it has printed nothing."""


def resolve_base() -> str:
    """The `/api/0` prefix every request is built on, from `TIMESHEET_ACTIVITY_URL`.

    Optional, and its default is the answer for almost everyone: ActivityWatch runs on the
    machine you are typing on. It is declared configuration rather than a constant for the
    case it isn't — a second machine, a non-standard port — which used to mean editing an
    installed script that the next update overwrites.

    Called per request rather than once into a module global. The global saved one settings
    read per call and cost more than it saved: the address was fixed before any caller
    existed, so redirecting it meant reassigning `aw_client.AW_BASE` from the outside —
    which is what this suite had to do to keep itself off a developer's real ActivityWatch,
    and what made a plain `import aw_client` a thing with consequences. A settings read is
    a dict lookup and a file stat, and a request over the wire follows it immediately.
    """
    base = skill_config.setting("TIMESHEET_ACTIVITY_URL", default=DEFAULT_ACTIVITY_URL)
    return base.rstrip("/") + "/api/0"


def get(path):
    try:
        with urllib.request.urlopen(resolve_base() + path, timeout=15) as r:
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
