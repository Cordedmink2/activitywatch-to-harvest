"""What a user can change without editing a script, and what happens when they haven't.

Two layers meet here, and the division between them is the point.

**Machine and account facts** are declared plugin configuration — the Harvest credentials,
the timezone, the ActivityWatch address. The install asks once, the harness stores them,
and they arrive as ordinary environment variables that `skill_config.setting()` resolves.
The tests below cover the two the scripts newly read, and the failure a user meets when a
required one is absent: the timezone, which used to be a silent `default=12.0` — every
other user's day dated in New Zealand, with nothing on screen saying so.

**Preferences** stay in the user's own workspace, as prose in `context.md` that the model
reads and passes on the command line. The tunables that decide whether a block counts as
active, and how much noise is folded away, were settable nowhere: they were module
constants, so changing one meant editing a shipped script — which an update then
overwrites. Each now has a flag, with the constant as its default, so nothing about a run
that passes none of them changes.
"""
from __future__ import annotations

import ast
import datetime as dt
from pathlib import Path
from zoneinfo import ZoneInfo

import pytest

import activity_timeline as tl
import afk_blocks as ab
import aw_client as aw
from support import aw_server, day, run_cli

MAY = dt.date(2026, 5, 28)


@pytest.fixture
def unconfigured(monkeypatch):
    """No timezone anywhere — the state a user is in before they have configured one."""
    monkeypatch.delenv("TIMESHEET_TIMEZONE", raising=False)


# --------------------------------------------------------------------------------------
# The ActivityWatch address
# --------------------------------------------------------------------------------------

def test_the_activity_watch_address_defaults_to_the_local_server(monkeypatch):
    """The overwhelmingly common case, and the reason the option is optional: AW runs on
    the machine you are typing on.

    The setting is deleted first because the hermetic fixture sets it — that is how the
    suite now keeps itself off a real ActivityWatch, so a test about the *unconfigured*
    default has to opt out of the guard, exactly as the timezone tests do.
    """
    monkeypatch.delenv("TIMESHEET_ACTIVITY_URL", raising=False)
    assert aw.resolve_base() == "http://localhost:5600/api/0"


def test_the_address_can_point_somewhere_else(monkeypatch):
    monkeypatch.setenv("TIMESHEET_ACTIVITY_URL", "http://desk.lan:5600")
    assert aw.resolve_base() == "http://desk.lan:5600/api/0"


def test_a_trailing_slash_does_not_produce_a_doubled_path(monkeypatch):
    """A URL pasted out of a browser's address bar has one. `//api/0` is a 404 whose
    message blames ActivityWatch for being unreachable."""
    monkeypatch.setenv("TIMESHEET_ACTIVITY_URL", "http://desk.lan:5600/")
    assert aw.resolve_base() == "http://desk.lan:5600/api/0"


def test_the_address_every_request_is_built_on_is_the_resolved_one(monkeypatch):
    """The wiring, not just the resolver.

    The tests above exercise `resolve_base()` in isolation. Nothing there says `get()` —
    the function that actually opens the socket — is built on it, and for a while nothing
    did: the address was resolved once into `AW_BASE` at import, the hermetic fixture
    reassigned that global directly, and reverting the resolver to a literal
    `"http://localhost:5600/api/0"` would have left every other test in this file green
    while breaking every remote-ActivityWatch install.

    So this drives a real request at a real socket and asks where it landed.
    """
    d = day().active("09:00", "17:00")
    with aw_server(d.buckets(), d.settings()) as srv:
        monkeypatch.setenv("TIMESHEET_ACTIVITY_URL", srv.base)
        aw.get("/buckets/")
        assert srv.requests, (
            "get() did not reach the configured address, so TIMESHEET_ACTIVITY_URL "
            "reaches nothing that makes a request")


def test_the_address_is_resolved_per_request_rather_than_once(monkeypatch):
    """Two requests, two addresses, no reimport and no module global reassigned.

    This is the property the prefactor bought, and it is the one that cannot be inferred
    from the test above: a resolver called once at import would satisfy that one and fail
    this one. It is also what the hermeticity fixture now stands on — `conftest` redirects
    the activity source by setting `TIMESHEET_ACTIVITY_URL`, and if the address were ever
    frozen again the whole suite would quietly start reading the developer's real
    ActivityWatch.
    """
    d = day().active("09:00", "17:00")
    with aw_server(d.buckets(), d.settings()) as first,          aw_server(d.buckets(), d.settings()) as second:
        monkeypatch.setenv("TIMESHEET_ACTIVITY_URL", first.base)
        aw.get("/buckets/")
        monkeypatch.setenv("TIMESHEET_ACTIVITY_URL", second.base)
        aw.get("/buckets/")
        assert first.requests and second.requests, (
            "the second request went back to the first address — the activity source is "
            "resolved once and frozen, so no caller can redirect it")


# --------------------------------------------------------------------------------------
# The timezone
# --------------------------------------------------------------------------------------

def test_a_flag_is_taken_exactly_as_given():
    """`--utc-offset` still overrides a single run — a user reconstructing a day they
    spent in another zone should not have to reconfigure the plugin to do it. What it
    resolves to is a zone that is that offset all year, which is what passing a number
    has always meant."""
    assert aw.resolve_zone(13.0).utcoffset(None) == dt.timedelta(hours=13)


def test_the_zone_comes_from_the_configuration(monkeypatch):
    monkeypatch.setenv("TIMESHEET_TIMEZONE", "Europe/London")
    zone = aw.resolve_zone(None)
    # A real zone, not the fixed-offset one `--utc-offset` produces: the whole point of
    # reading the setting is that the day's two ends can be resolved at different offsets.
    assert isinstance(zone, ZoneInfo)
    assert zone.key == "Europe/London"


def test_the_configured_zone_dates_a_day_by_the_offset_in_force_on_it(monkeypatch):
    """The same zone bounds a January day differently from a May one. Resolving a zone
    rather than a number is what lets a user reconstruct a day from the other side of a
    daylight-saving change without touching their configuration."""
    monkeypatch.setenv("TIMESHEET_TIMEZONE", "Europe/London")
    zone = aw.resolve_zone(None)
    assert aw.utc_bounds(MAY, zone)[0] == "2026-05-27T23:00:00Z"              # BST, UTC+1
    assert aw.utc_bounds(dt.date(2026, 1, 15), zone)[0] == "2026-01-15T00:00:00Z"   # GMT


def test_a_day_containing_the_change_is_bounded_by_both_of_its_offsets(monkeypatch):
    """The bug a single offset per day leaves behind.

    `Pacific/Auckland` goes back an hour at 03:00 on 2026-04-05, so that local day is
    twenty-five hours long: it opens at UTC+13 and closes at UTC+12. Reading one offset
    for it — at local noon, the only unambiguous hour to ask about — bounds it at
    12:00Z-12:00Z and never asks ActivityWatch for the first hour of the day.
    """
    monkeypatch.setenv("TIMESHEET_TIMEZONE", "Pacific/Auckland")
    start, end = aw.utc_bounds(dt.date(2026, 4, 5), aw.resolve_zone(None))
    assert (start, end) == ("2026-04-04T11:00:00Z", "2026-04-05T12:00:00Z")


def test_a_day_the_clocks_jump_forward_over_is_bounded_the_other_way(monkeypatch):
    """The mirror case, twenty-three hours long: 2026-09-27 opens at UTC+12 and closes at
    UTC+13. A single noon offset here overshoots instead, pulling in an hour of the
    previous local day — the same class of error, biased the opposite way."""
    monkeypatch.setenv("TIMESHEET_TIMEZONE", "Pacific/Auckland")
    start, end = aw.utc_bounds(dt.date(2026, 9, 27), aw.resolve_zone(None))
    assert (start, end) == ("2026-09-26T12:00:00Z", "2026-09-27T11:00:00Z")


def test_no_new_zealand_offset_is_applied_to_a_user_who_configured_nothing(unconfigured):
    """The whole reason this resolution exists.

    `--utc-offset` defaulted to 12.0, so a user in London who ran the skill got a day
    boundary twelve hours out — and nothing failed. Events landed on the wrong date, the
    timesheet was filed against the wrong day, and the only symptom was a day that looked
    oddly short. Refusing is the only safe answer: there is no offset that is right to
    guess.
    """
    with pytest.raises(SystemExit) as exc:
        aw.resolve_zone(None)
    message = str(exc.value)
    assert "TIMESHEET_TIMEZONE" in message
    assert "12" not in message, "the old New Zealand default is still being suggested"


def test_the_missing_zone_message_names_both_ways_to_supply_one(unconfigured):
    """A user reading this has two routes and should not have to find out about the
    second one from the source: configure it once, or pass it for this run."""
    with pytest.raises(SystemExit) as exc:
        aw.resolve_zone(None)
    message = str(exc.value)
    assert "/plugin configure" in message
    assert "--utc-offset" in message


def test_a_zone_that_cannot_be_loaded_says_so_and_names_the_escape_hatch(monkeypatch):
    """Two causes, one message: a mistyped IANA name, and a Windows Python with no zone
    database installed (`zoneinfo` is stdlib; the data it reads is not). Both are
    "this name did not resolve", and both are fixed by one of the two lines below —
    so the message names the check and the escape hatch rather than guessing which."""
    monkeypatch.setenv("TIMESHEET_TIMEZONE", "Nowhere/Notreal")
    with pytest.raises(SystemExit) as exc:
        aw.resolve_zone(None)
    message = str(exc.value)
    assert "Nowhere/Notreal" in message
    assert "tzdata" in message
    assert "--utc-offset" in message


@pytest.mark.parametrize("bad", ["99", "-40", "nan", "inf"],
                         ids=["too-big", "too-small", "nan", "infinity"])
def test_an_offset_no_zone_could_have_is_refused_rather_than_raised(bad, unconfigured):
    """`--utc-offset 99` is a typo, and the scripts' contract is that bad input produces
    a line and a non-zero exit rather than a traceback. Building a fixed zone out of it
    is the first thing that would raise, so the check belongs here.

    All four are parametrised because they do not raise the same exception: `argparse
    type=float` accepts `inf` and `nan` as readily as `99`, and the timedelta constructor
    answers the first with `OverflowError` and the others with `ValueError`. Catching only
    the second leaves exactly one input producing the traceback this test forbids — which
    is what it did.
    """
    d = day().active("09:00", "17:00")
    r = run_cli(ab, [d.date_str(), "--json", "--utc-offset", bad])
    assert r.code != 0
    assert "Traceback" not in r.err
    assert "--utc-offset" in r.err


def test_a_configured_zone_carries_a_run_that_passes_no_offset(live_aw, monkeypatch):
    """End to end: the value the install asked for is enough to analyse a day."""
    monkeypatch.setenv("TIMESHEET_TIMEZONE", "Etc/GMT-12")
    d = day().active("09:00", "12:00")
    live_aw(d)
    result = run_cli(ab, [d.date_str(), "--json"]).json()
    assert result["work_start"] == "09:00:00" and result["work_end"] == "12:00:00"


@pytest.mark.parametrize("module", [ab, tl], ids=["afk_blocks", "activity_timeline"])
def test_neither_script_runs_a_day_against_a_zone_nobody_chose(module, live_aw, unconfigured):
    """Both scripts date a day, so both have to refuse the same way. `afk_blocks` refusing
    while `activity_timeline` quietly assumed +12 would be the worst of both."""
    d = day().active("09:00", "12:00").window("09:00", "12:00", "Code", "x")
    live_aw(d)
    r = run_cli(module, [d.date_str(), "--json"])
    assert r.code != 0
    assert "TIMESHEET_TIMEZONE" in r.err


# --------------------------------------------------------------------------------------
# The tunables — module constants until now, so settable only by editing a shipped script
# --------------------------------------------------------------------------------------

def blip_day():
    """A solid day, then an hour away, then a one-second nudge. `work_end` is the nudge,
    which is exactly the flicker the blip guard exists to discount."""
    return (day().active("09:00", "17:00").afk("17:00", "18:00")
            .active("18:00", "18:00:01"))


def test_by_default_a_one_second_nudge_does_not_extend_the_day(live_aw):
    d = blip_day()
    live_aw(d)
    result = run_cli(ab, [d.date_str(), "--json", "--utc-offset", str(d.offset)]).json()
    assert result["work_end_blip"] == {"last_solid_end": "17:00:00"}


def test_what_counts_as_substantive_activity_is_settable(live_aw):
    """`--solid` is the duration below which a not-afk run is a flicker. A user whose
    real work arrives in very short bursts — reviewing an agent's output, say — needs it
    lower, and used to have to edit `SOLID_S` in an installed script to get it."""
    d = blip_day()
    live_aw(d)
    result = run_cli(ab, [d.date_str(), "--json", "--utc-offset", str(d.offset),
                          "--solid", "1"]).json()
    assert result["work_end_blip"] is None
    assert result["work_end"] == "18:00:01"


def test_how_long_a_gap_makes_the_day_end_a_flicker_is_settable(live_aw):
    """`--blip-gap`: the same day, judged by the other half of the rule."""
    d = blip_day()
    live_aw(d)
    result = run_cli(ab, [d.date_str(), "--json", "--utc-offset", str(d.offset),
                          "--blip-gap", "7200"]).json()
    assert result["work_end_blip"] is None


def test_the_smallest_uncovered_stretch_worth_reporting_is_settable(live_aw):
    """`--min-uncovered` separates "you forgot to bill this" from block rounding. Ten
    minutes is rounding to one user and a missed entry to another."""
    d = day().active("09:00", "11:00")
    live_aw(d)
    args = [d.date_str(), "--json", "--utc-offset", str(d.offset), "--cover", "09:00-10:50"]
    assert run_cli(ab, args).json()["coverage_report"]["uncovered"] == []
    loosened = run_cli(ab, args + ["--min-uncovered", "300"]).json()
    assert [u["start"] for u in loosened["coverage_report"]["uncovered"]] == ["10:50:00"]


def test_the_bands_deciding_whether_a_block_is_active_are_settable(live_aw):
    """`--active-band` / `--thin-band`: the ratio at which a stretch stops being billable.

    Half-active reads as "thin" on the shipped bands. Someone supervising long-running
    work is genuinely working through those idle stretches, and the verdict — which the
    model reads as a recommendation — should be able to say so.
    """
    d = day().active("09:00", "09:30").afk("09:30", "10:00")
    live_aw(d)
    args = [d.date_str(), "--json", "--utc-offset", str(d.offset), "--window", "09:00-10:00"]
    default = run_cli(ab, args).json()["window_report"]
    assert default["active_ratio"] == 0.5 and default["verdict"] == "thin (0.4-0.7)"
    loosened = run_cli(ab, args + ["--active-band", "0.5"]).json()["window_report"]
    assert loosened["verdict"] == "active (>=0.5)"


def test_bands_that_read_backwards_are_refused(live_aw):
    """`--thin-band 0.9 --active-band 0.5` produces the verdict "thin (0.9-0.5)" — which
    nothing fails on, and which the model then bills against."""
    d = day().active("09:00", "10:00")
    live_aw(d)
    r = run_cli(ab, [d.date_str(), "--json", "--utc-offset", str(d.offset),
                     "--window", "09:00-10:00", "--thin-band", "0.9", "--active-band", "0.5"])
    assert r.code == 2 and "--thin-band" in r.err


def test_the_noise_floor_below_which_an_event_is_a_tab_switch_is_settable(live_aw):
    """`--noise-floor`. The shipped 5s drops tab-switch noise; it also drops a genuine
    four-second glance at the ticket that names the client."""
    d = day().window("09:00", "09:00:04", "Firefox", "ACME ticket")
    live_aw(d)
    args = [d.date_str(), "--json", "--utc-offset", str(d.offset)]
    assert run_cli(tl, args).json()["spans"] == []
    assert len(run_cli(tl, args + ["--noise-floor", "1"]).json()["spans"]) == 1


def test_the_gap_that_breaks_a_span_in_two_is_settable(live_aw):
    """`--gap-fold`. Folding a 30s gap keeps one span; a user reading their timeline for
    genuine interruptions wants the two."""
    d = (day().window("09:00", "09:10", "Code", "main.py")
         .window("09:10:30", "09:20", "Code", "main.py"))
    live_aw(d)
    args = [d.date_str(), "--json", "--utc-offset", str(d.offset)]
    assert len(run_cli(tl, args).json()["spans"]) == 1
    assert len(run_cli(tl, args + ["--gap-fold", "10"]).json()["spans"]) == 2


@pytest.mark.parametrize("flag,value", [
    ("--solid", "1"), ("--blip-gap", "7200"), ("--min-uncovered", "300"),
    ("--active-band", "0.5"), ("--thin-band", "0.2"),
])
def test_an_afk_tunable_left_alone_changes_nothing(flag, value, live_aw):
    """Each constant is still its own flag's default, so an existing run is unaffected.

    Written as a pair rather than trusted: moving a constant into `argparse` is exactly
    where a units mistake (seconds read as minutes) or a lost default hides, and neither
    would fail anything else in the suite.
    """
    d = day().active("09:00", "17:00")
    live_aw(d)
    base = [d.date_str(), "--json", "--utc-offset", str(d.offset)]
    defaults = {"--solid": "120", "--blip-gap": "600", "--min-uncovered": "900",
                "--active-band": "0.7", "--thin-band": "0.4"}
    assert run_cli(ab, base).json() == run_cli(ab, base + [flag, defaults[flag]]).json()
    assert run_cli(ab, base + [flag, value]).code == 0


@pytest.mark.parametrize("flag,default", [("--noise-floor", "5"), ("--gap-fold", "60")])
def test_a_timeline_tunable_left_alone_changes_nothing(flag, default, live_aw):
    d = (day().window("09:00", "09:10", "Code", "main.py")
         .window("09:10:30", "09:20", "Code", "main.py"))
    live_aw(d)
    base = [d.date_str(), "--json", "--utc-offset", str(d.offset)]
    assert run_cli(tl, base).json() == run_cli(tl, base + [flag, default]).json()
