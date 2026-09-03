"""Tests for the shared ActivityWatch client.

`afk_blocks.py` and `activity_timeline.py` both read the same local AW server and
carried byte-identical copies of the request, dedupe and timestamp helpers. Two
copies means a fix to one silently leaves the other wrong, so these cover the
shared module and then assert both scripts really use it rather than their own.

The zone a day is read in was this module's too until #36 and is now `timezone.py`'s,
because the provider half needs the same arithmetic; `test_timezone.py` covers it.
"""

import datetime as dt
import os
import sys

import pytest

SCRIPTS = os.path.join(os.path.dirname(__file__), "..", "scripts")
sys.path.insert(0, SCRIPTS)
import aw_client as aw
import activity_timeline as tl
import afk_blocks as ab
from support import day

# Written in UTC: these are tests of the wire format, and an offset would only put a
# second conversion between the fixture and the string asserted on.
D = day(offset=0)


def test_dedupe_keeps_the_longest_duration_per_timestamp():
    """AW extends an ongoing event by re-emitting it at the same timestamp."""
    events = [D.event("09:00", seconds=60), D.event("09:00", seconds=900),
              D.event("09:00", seconds=300)]
    kept = aw.dedupe_heartbeats(events)
    assert [e["duration"] for e in kept] == [900]


def test_dedupe_returns_events_in_timestamp_order():
    events = [D.event("11:00", seconds=60), D.event("09:00", seconds=60),
              D.event("10:00", seconds=60)]
    assert [e["timestamp"] for e in aw.dedupe_heartbeats(events)] == [
        "2026-05-28T09:00:00Z", "2026-05-28T10:00:00Z", "2026-05-28T11:00:00Z"]


UTC_0930 = dt.datetime(2026, 5, 28, 9, 30, tzinfo=dt.timezone.utc)


@pytest.mark.parametrize("stamp", ["2026-05-28T09:30:00Z", "2026-05-28T09:30:00+00:00"])
def test_parse_ts_reads_both_utc_spellings(stamp):
    """AW emits both forms depending on the endpoint."""
    assert aw.parse_ts(stamp) == UTC_0930


def test_parse_ts_reads_the_z_suffix_on_python_310(monkeypatch):
    """fromisoformat only learned `Z` in 3.11, and the README supports 3.10, where the
    raw string raises. Simulated: on a newer interpreter parse_ts would pass either way,
    so dropping the normalization would break 3.10 users with nothing to catch it."""
    real = dt.datetime

    class Py310Datetime(real):
        @classmethod
        def fromisoformat(cls, s):
            if s.endswith("Z"):
                raise ValueError(f"Invalid isoformat string: {s!r}")
            return real.fromisoformat(s)

    monkeypatch.setattr(aw.dt, "datetime", Py310Datetime)
    assert aw.parse_ts("2026-05-28T09:30:00Z") == UTC_0930


def test_pick_bucket_prefers_the_hostname_suffixed_bucket():
    """`aw-watcher-web-chrome` (no host) is a stale leftover; the `_HOST` one is live —
    even when the leftover happens to have the more recent `last_updated`, since a
    real leftover bucket can still receive occasional writes."""
    buckets = {
        "aw-watcher-web-chrome": {"last_updated": "2026-08-07T00:00:00+00:00"},
        "aw-watcher-web-chrome_WS-113359": {"last_updated": "2026-08-01T00:00:00+00:00"},
    }
    assert aw.pick_bucket(buckets, "aw-watcher-web-chrome") == "aw-watcher-web-chrome_WS-113359"


def test_pick_bucket_prefers_the_more_recently_updated_host_on_a_rename():
    """A machine rename/reimage leaves the old host's bucket behind, still matching
    the prefix. Alphabetical order would pick `_WS-113359` here (it sorts first);
    `_WS-114622` is the one actually reporting and must win instead."""
    buckets = {
        "aw-watcher-afk_WS-113359": {"last_updated": "2026-08-04T03:49:59+00:00"},
        "aw-watcher-afk_WS-114622": {"last_updated": "2026-08-07T01:56:22+00:00"},
    }
    assert aw.pick_bucket(buckets, "aw-watcher-afk_") == "aw-watcher-afk_WS-114622"


def test_pick_bucket_returns_none_when_no_bucket_matches():
    buckets = {"aw-watcher-afk_HOST": {"last_updated": "2026-08-07T00:00:00+00:00"}}
    assert aw.pick_bucket(buckets, "aw-watcher-window_") is None


def test_fetch_events_makes_no_request_for_a_missing_bucket(monkeypatch):
    """The web watchers are optional, so pick_bucket legitimately returns None."""
    monkeypatch.setattr(aw, "get", lambda path: pytest.fail(f"requested {path} for no bucket"))
    assert aw.fetch_events(None, "2026-05-28T00:00:00Z", "2026-05-29T00:00:00Z") == []


def test_fetch_events_asks_the_bucket_for_the_requested_range(monkeypatch):
    seen = []
    monkeypatch.setattr(aw, "get", lambda path: seen.append(path) or ["event"])
    got = aw.fetch_events("aw-watcher-afk_HOST", "2026-05-28T00:00:00Z", "2026-05-29T00:00:00Z")
    assert got == ["event"]
    assert seen == ["/buckets/aw-watcher-afk_HOST/events"
                    "?start=2026-05-28T00:00:00Z&end=2026-05-29T00:00:00Z&limit=10000"]


# The request, dedupe and timestamp helpers the two day-reading scripts each used to carry
# a copy of, which is the drift this module exists to prevent. `parse_range` was on this
# list until #36 and is now on `test_timezone.py`'s, with the rest of the zone arithmetic.
SHARED = ["get", "pick_bucket", "fetch_events", "dedupe_heartbeats", "parse_ts",
          "resolve_base"]


@pytest.mark.parametrize("module", [ab, tl], ids=["afk_blocks", "activity_timeline"])
@pytest.mark.parametrize("name", SHARED)
def test_scripts_use_the_shared_helper_rather_than_their_own(module, name):
    """A private copy would be a different function object; the same object proves reuse."""
    assert getattr(module, name, None) is getattr(aw, name), (
        f"{module.__name__}.{name} is not the shared aw_client one"
    )


@pytest.mark.parametrize("module", [ab, tl], ids=lambda m: m.__name__)
def test_scripts_do_not_redefine_the_server_address(module):
    """A second default address can drift from the shared one, and an identity check
    cannot catch that for a string the way it does for a function.

    `AW_BASE` is what this used to name — a module global holding the resolved address.
    There is no such global now; `resolve_base()` runs per request. The thing that could
    still be copied is the default it falls back to, so that is what is named here — on
    the imported module, since a module global is exactly what an import exposes.
    """
    for own in ("AW_BASE", "DEFAULT_ACTIVITY_URL"):
        assert not hasattr(module, own), f"{module.__name__} keeps its own copy of {own}"
