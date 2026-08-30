"""Tests of the test harness itself.

The hermeticity fixture in `conftest.py` is the only thing standing between this suite
and the user's real ActivityWatch data / real Harvest timesheet. A safety net nobody
tests is a safety net nobody knows is there, so these assert it actually blocks — and
that the fakes it hands out really do drive the scripts end to end.
"""
from __future__ import annotations

import datetime as dt
import urllib.error

import pytest

import afk_blocks as ab
import aw_client
import harvest_client
import skill_config
from support import day, run_cli


# --------------------------------------------------------------------------------------
# The guard
# --------------------------------------------------------------------------------------

def test_an_unstubbed_activitywatch_call_fails_instead_of_reading_the_real_server():
    """AW really is running on this machine at :5600. Without the guard this call would
    succeed and the test would silently assert against whatever the user did today."""
    assert "localhost:5600" not in aw_client.AW_BASE
    with pytest.raises(urllib.error.URLError):
        aw_client.get("/buckets/")


def test_an_unstubbed_harvest_call_cannot_reach_the_real_api():
    """The dangerous one: unguarded, a POST here creates a real billable time entry."""
    assert "harvestapp.com" not in harvest_client.API_BASE
    harvest_client._CREDS_CACHE = ("x", "y")      # get past creds to the network layer
    with pytest.raises(RuntimeError, match="network error"):
        harvest_client.request("GET", "/users/me")


def test_the_real_credentials_file_is_never_read():
    """`.env` at the skill root holds a live Harvest PAT. Tests must not see it.

    One repointed path is enough because `skill_config` is the only module that reads it.
    """
    assert not skill_config.ENV_PATH.exists()
    with pytest.raises(SystemExit):
        harvest_client.load_creds()


# --------------------------------------------------------------------------------------
# The fakes
# --------------------------------------------------------------------------------------

def test_live_aw_drives_a_script_end_to_end(live_aw):
    d = day().afk("07:00", "08:30").active("08:30", "12:00").afk("12:00", "13:00").active("13:00", "17:00")
    live_aw(d)
    r = run_cli(ab, [d.date_str(), "--json"])
    assert r.code == 0
    result = r.json()
    assert (result["work_start"], result["work_end"]) == ("08:30:00", "17:00:00")
    assert result["afk_bucket"] == "aw-watcher-afk_TESTHOST"


def test_the_fake_server_answers_the_range_the_script_asked_for(live_aw):
    """`utc_bounds` has to ask for local midnight to local midnight; if it drifted, the
    fake would be handed a range that misses the day's events."""
    d = day().active("08:30", "17:00")
    srv = live_aw(d)
    run_cli(ab, [d.date_str()])
    events_calls = srv.sent("GET", "/events")
    assert events_calls, "the script never fetched any events"
    q = events_calls[0]["query"]
    assert (q["start"], q["end"]) == ("2026-05-27T12:00:00Z", "2026-05-28T12:00:00Z")


def test_a_day_renders_local_times_as_utc_events():
    d = day().active("08:30", "09:00")
    ev = d.afk_events()[0]
    assert ev["timestamp"] == "2026-05-27T20:30:00Z"      # 08:30 NZST
    assert ev["duration"] == 1800


def test_hours_past_twenty_four_reach_into_the_next_morning():
    d = day().active("22:00", "25:30")
    assert d.afk_events()[0]["duration"] == 3.5 * 3600


def test_a_marked_time_writes_the_second_pass_over_the_repeated_hour():
    """Without the marker `at()` localises with `fold=0`, so both ends of this event would
    be 13:30Z and the hour would render as an instantaneous one."""
    d = day(dt.date(2026, 4, 5), zone="Pacific/Auckland").afk("02:30", "02:30*")
    ev = d.afk_events()[0]
    assert ev["timestamp"] == "2026-04-04T13:30:00Z"
    assert ev["duration"] == 3600


@pytest.mark.parametrize("builder", ["thin", "locked"])
def test_the_slicing_builders_refuse_a_marked_time(builder):
    """They generate their pieces with `_fmt()`, which writes a bare `HH:MM:SS`. Accepting
    a marker would put every piece in the *first* pass — a fixture that reads as though it
    straddles the change and does not, which is worse than not being able to write it."""
    d = day(dt.date(2026, 4, 5), zone="Pacific/Auckland")
    with pytest.raises(ValueError, match="cannot write the second pass"):
        getattr(d, builder)("02:00*", "03:00")


# --------------------------------------------------------------------------------------
# run_cli
# --------------------------------------------------------------------------------------

def test_run_cli_captures_the_exit_code_from_a_returning_main(live_aw):
    d = day().active("09:00", "10:00")
    live_aw(d)
    assert run_cli(ab, ["not-a-date"]).code == 2


def test_run_cli_captures_stderr_separately_from_stdout(live_aw):
    d = day().active("09:00", "10:00")
    live_aw(d)
    r = run_cli(ab, [d.date_str(), "--window", "bogus"])
    assert r.code == 2
    assert "ERR bad --window" in r.err
    assert r.out == ""
