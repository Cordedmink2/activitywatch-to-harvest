"""Shared ActivityWatch REST helpers for the daily-timesheet skill.

`afk_blocks.py` reads the day skeleton and `activity_timeline.py` reads its
content, but both talk to the same local AW server the same way: discover a
hostname-suffixed bucket, pull a day of events, collapse the heartbeats. Each
used to carry its own copy of that code, so a fix to one left the other wrong.

No third-party deps - stdlib urllib, like the sibling harvest_*.py helpers.
"""
import datetime as dt
import json
import urllib.error
import urllib.request

AW_BASE = "http://localhost:5600/api/0"


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
