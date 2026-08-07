"""Shared ActivityWatch REST helpers for the daily-timesheet skill.

`afk_blocks.py` reads the day skeleton and `activity_timeline.py` reads its
content, but both talk to the same local AW server the same way: discover a
hostname-suffixed bucket, pull a day of events, collapse the heartbeats. Each
used to carry its own copy of that code, so a fix to one left the other wrong.

No third-party deps - stdlib urllib, like the sibling harvest_*.py helpers.
"""
import datetime as dt
import json
import urllib.request

AW_BASE = "http://localhost:5600/api/0"


def get(path):
    with urllib.request.urlopen(AW_BASE + path, timeout=15) as r:
        return json.load(r)


def pick_bucket(buckets, prefix):
    """Bucket id starting with `prefix`, or None. Buckets are hostname-suffixed
    (`aw-watcher-afk_HOST`); an unsuffixed one is a leftover, so any suffixed
    candidate beats it regardless of recency. Among suffixed candidates, a machine
    rename/reimage leaves the old HOST bucket behind still matching the prefix but
    no longer updating — picking alphabetically-first silently reads that stale
    bucket once the new host's suffix happens to sort after the old one. Break
    the tie by `last_updated` instead, so the actively-reporting host wins.

    Takes an already-fetched `{bucket_id: {...}}` listing (as returned by
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


def utc_bounds(local_date, offset):
    """The local day as the Z-suffixed UTC strings the AW events API wants."""
    local_start = dt.datetime.combine(local_date, dt.time(0, 0))
    return ((local_start - offset).strftime("%Y-%m-%dT%H:%M:%SZ"),
            (local_start + dt.timedelta(days=1) - offset).strftime("%Y-%m-%dT%H:%M:%SZ"))
