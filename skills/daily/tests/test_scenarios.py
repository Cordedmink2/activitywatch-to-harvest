"""End-to-end scenario regression: every script, every scenario, against a golden file.

Two layers, deliberately:

* **The golden files** catch *change*. They hold the complete output of both scripts for
  each day in `scenarios.py`, so any edit to the arithmetic produces a reviewable diff
  instead of a quietly different timesheet. Regenerate with `pytest --regen-golden`.
* **The named assertions below them** state *intent*. A golden can only say "this is what
  it did"; these say "this is what it must do, and here is why", so a regeneration that
  bakes in a bug still fails.

A golden alone is not a test. Both layers, or neither.
"""
from __future__ import annotations

import datetime as dt
import json
from pathlib import Path

import pytest

import activity_timeline as tl
import afk_blocks as ab
import harvest_post as hpost
from scenarios import SCENARIOS, BY_NAME
from support import day, run_cli, with_heartbeats

GOLDEN = Path(__file__).resolve().parent / "golden"

pytestmark = pytest.mark.scenario


def dating_args(d) -> list:
    """How this day tells the scripts what its clock reads.

    A fixed-offset day hands over `--utc-offset`; a `zone=` day hands over nothing, having
    had its zone configured by `live_aw`. Passing the flag anyway would take the same
    shortcut the scripts are being tested for not needing, and on a day whose offset
    changes at 03:00 there is no number to pass.
    """
    return [] if d.zone_name else ["--utc-offset", str(d.offset)]


def probe(scenario, live_aw) -> dict:
    """Run both scripts over the scenario the way the skill's Step 2 does."""
    d = scenario.build()
    live_aw(d)
    date, offset = d.date_str(), dating_args(d)

    afk_args = [date, "--json", *offset]
    if scenario.cover:
        afk_args += ["--cover", scenario.cover]
    afk = run_cli(ab, afk_args)

    out = {
        "afk_json": afk.json(),
        "afk_text": run_cli(ab, [date, *offset,
                                *(["--cover", scenario.cover] if scenario.cover else [])]).out,
        "window_reports": {},
        "timeline_json": run_cli(tl, [date, "--json", *offset]).json(),
        "timeline_text": run_cli(tl, [date, *offset]).out,
    }
    for w in scenario.windows:
        r = run_cli(ab, [date, "--json", "--window", w, *offset])
        out["window_reports"][w] = r.json().get("window_report")
    if scenario.zoom:
        out["zoom_json"] = run_cli(tl, [date, "--json", "--window", scenario.zoom, *offset]).json()
    return out


@pytest.mark.parametrize("scenario", SCENARIOS, ids=lambda s: s.name)
def test_scenario_matches_its_golden(scenario, live_aw, request):
    actual = probe(scenario, live_aw)
    path = GOLDEN / f"{scenario.name}.json"
    rendered = json.dumps(actual, indent=2, ensure_ascii=False) + "\n"

    if request.config.getoption("--regen-golden"):
        GOLDEN.mkdir(exist_ok=True)
        path.write_text(rendered, encoding="utf-8")
        pytest.skip(f"regenerated {path.name} — read the diff before committing it")

    assert path.exists(), (
        f"no golden for '{scenario.name}'. Run `pytest --regen-golden`, then READ "
        f"tests/golden/{scenario.name}.json and confirm it says what you meant."
    )
    expected = json.loads(path.read_text(encoding="utf-8"))
    assert actual == expected, (
        f"'{scenario.name}' output changed. If the change is intended, rerun with "
        f"--regen-golden and commit the diff as the record of what moved."
    )


# --------------------------------------------------------------------------------------
# What each scenario is actually for. A regenerated golden can bake in a bug; these can't.
# --------------------------------------------------------------------------------------

def test_a_screen_lock_produces_no_break_but_a_dead_ratio(live_aw):
    """The documented AW quirk, end to end: a 48-minute absence the break detector cannot
    see, because the lock fragments AFK into sub-threshold chunks. The only signal left is
    the window ratio — which is why the skill validates every block with one."""
    s = BY_NAME["locked-screen-day"]
    got = probe(s, live_aw)
    assert got["afk_json"]["breaks"] == [], "a fragmented lock must not register as a break"
    assert got["window_reports"]["10:57-11:45"]["active_ratio"] == 0.0
    assert got["window_reports"]["10:57-11:45"]["verdict"] == "mostly idle (<0.4)"
    # ...and the lock does not split the active span, so the span alone looks like work.
    assert len(got["afk_json"]["active_spans"]) == 1


def test_agent_supervision_reads_thin_not_idle(live_aw):
    """Both supervision stretches must land in the 0.4-0.7 band. Below 0.4 the skill would
    refuse to bill them; above 0.7 it would stop flagging them for review."""
    got = probe(BY_NAME["locked-screen-day"], live_aw)
    for w in ("11:45-13:26", "13:48-18:02"):
        assert got["window_reports"][w]["verdict"] == "thin (0.4-0.7)", w


def test_active_but_unbilled_time_is_reported_as_uncovered(live_aw):
    """The under-billing guard. 13:26-13:48 is 22 active minutes deliberately left out of
    --cover (personal browsing); the script must name it rather than let it vanish."""
    got = probe(BY_NAME["locked-screen-day"], live_aw)
    uncovered = got["afk_json"]["coverage_report"]["uncovered"]
    assert [(u["start"], u["end"]) for u in uncovered] == [("13:26:00", "13:48:00")]


def test_the_sub_floor_tail_is_below_the_reporting_bar(live_aw):
    """18:53-19:01 is real work, but 8 minutes — under MIN_UNCOVERED_S. Reporting it would
    make the coverage check noisy on every rounded block, so it stays silent by design."""
    got = probe(BY_NAME["locked-screen-day"], live_aw)
    starts = [u["start"] for u in got["afk_json"]["coverage_report"]["uncovered"]]
    assert "18:53:00" not in starts


def test_a_late_flicker_does_not_become_the_end_of_the_day(live_aw):
    got = probe(BY_NAME["blip-and-tail-day"], live_aw)
    afk = got["afk_json"]
    assert afk["work_end"] == "19:31:00"
    assert afk["work_end_blip"]["last_solid_end"] == "17:20:00", "billing to 19:31 invents 2 hours"


def test_a_window_left_in_focus_is_flagged_as_a_tail_not_as_work(live_aw):
    got = probe(BY_NAME["blip-and-tail-day"], live_aw)
    tail = got["afk_json"]["window_watcher_tail"]
    assert tail["end"] == "22:00:00"
    assert tail["gap_past_work_end_min"] == 149.0


def test_a_late_flicker_also_manufactures_a_break_out_of_the_evening(live_aw):
    """Not just an end-of-day problem. `find_breaks` bounds itself by `work_end`, so the
    flicker pulls the 17:20-19:30 evening idle *inside* the workday and reports it as a
    second break. Real lunch first, invented "break" second — a reader who takes the
    breaks list at face value gets a plausible-looking day that ends two hours late.

    Pinned as current behaviour, not endorsed: the `blip` flag next to it is what tells
    the skill to end the day at 17:20 and ignore the second entry."""
    got = probe(BY_NAME["blip-and-tail-day"], live_aw)
    breaks = [(b["start"], b["end"]) for b in got["afk_json"]["breaks"]]
    assert breaks == [("12:15:00", "13:10:00"), ("17:20:00", "19:30:00")]
    assert got["afk_json"]["work_end_blip"], "the blip flag is what makes the 2nd break readable"


def test_a_title_matching_two_clients_is_flagged_multi(live_aw):
    """The span the skill is told never to accept without a screenshot."""
    got = probe(BY_NAME["interleaved-clients-day"], live_aw)
    multi = [s for s in got["timeline_json"]["spans"] if s["multi"]]
    assert multi, "an ACME/BETA title must be flagged, not silently assigned to one"
    assert sorted(multi[0]["categories"]) == ["ACME", "BETA"]


def test_a_generic_tool_lands_uncategorized_rather_than_guessed(live_aw):
    got = probe(BY_NAME["interleaved-clients-day"], live_aw)
    uncat = [s for s in got["timeline_json"]["spans"]
             if s["category"] == "uncategorized" and "XrmToolBox" in str(s["top_titles"])]
    assert uncat, "XrmToolBox names no client; guessing one is the misattribution failure"


def test_a_day_with_no_break_is_one_span_hiding_dead_stretches(live_aw):
    """The Step 6 guard-1 trap: the span passes the 0.7 band while three stretches inside
    it are nearly dead. If the span ratio ever dropped below 0.7 this scenario would stop
    testing what it was built for."""
    got = probe(BY_NAME["no-break-day"], live_aw)
    assert got["afk_json"]["breaks"] == []
    assert len(got["afk_json"]["active_spans"]) == 1
    assert got["window_reports"]["08:15-17:30"]["active_ratio"] >= 0.7
    for dead in ("10:30-11:00", "13:00-13:35", "15:40-16:10"):
        assert got["window_reports"][dead]["active_ratio"] < 0.4, dead


def test_work_past_midnight_ends_on_a_clock_time_earlier_than_it_started(live_aw):
    """Times render as HH:MM:SS with no date, so a post-midnight end reads as `01:12:00`.
    Anything comparing the two strings to sanity-check the day gets the wrong answer."""
    got = probe(BY_NAME["overnight-day"], live_aw)
    afk = got["afk_json"]
    assert (afk["work_start"], afk["work_end"]) == ("19:30:00", "01:12:00")
    assert afk["work_end"] < afk["work_start"]      # the trap, pinned


def test_a_day_with_no_activity_reports_that_rather_than_failing(live_aw):
    d = BY_NAME["idle-day"].build()
    live_aw(d)
    r = run_cli(ab, [d.date_str()])
    assert r.code == 0
    assert "No not-afk activity found" in r.out


def test_the_configured_zone_alone_reproduces_a_summer_time_clock(live_aw):
    """Nothing is passed on the command line: the zone `live_aw` configured is the whole
    input, and on 2026-01-20 it is an hour off `Pacific/Auckland`'s winter offset. Passing
    that winter offset by hand is what the user used to have to remember not to do, and
    the second half shows what it would have cost them — every time an hour early."""
    d = BY_NAME["daylight-saving-day"].build()
    live_aw(d)
    correct = run_cli(ab, [d.date_str(), "--json"]).json()
    assert (correct["work_start"], correct["work_end"]) == ("08:30:00", "17:15:00")
    wrong = run_cli(ab, [d.date_str(), "--json", "--utc-offset", "12"]).json()
    assert wrong["work_start"] == "07:30:00", "the wrong offset must visibly shift the day"


def test_a_day_whose_offset_changes_renders_both_halves_in_local_time(live_aw):
    """The case no single offset can cover. `Pacific/Auckland` goes back an hour at 03:00
    on 2026-04-05, so the 00:40 start is UTC+13 and the 09:15 one is UTC+12.

    Reading one offset for the whole day fails twice over, and this is what each failure
    looks like: at the winter offset the early session renders as 23:40 the night before
    *and* falls outside the fetch window, so a day that started at twenty to one in the
    morning reports starting at quarter past nine.
    """
    got = probe(BY_NAME["daylight-saving-transition-day"], live_aw)
    afk = got["afk_json"]
    assert (afk["work_start"], afk["work_end"]) == ("00:40:00", "17:00:00")
    starts = [s["start"] for s in afk["active_spans"]]
    assert starts == ["00:40:00", "09:15:00", "13:20:00"]


def test_the_hour_the_clocks_give_back_is_counted_as_elapsed_time(live_aw):
    """01:45 to 09:15 is seven and a half hours on the wall and eight and a half in real
    time, because 02:00-03:00 happens twice that morning. The break is reported at the
    elapsed length — the honest one, and the one the AFK watcher actually recorded. Pinned
    because 510 minutes against those two clock times reads like an arithmetic bug."""
    got = probe(BY_NAME["daylight-saving-transition-day"], live_aw)
    overnight = [b for b in got["afk_json"]["breaks"] if b["start"] == "01:45:00"]
    assert overnight and overnight[0]["end"] == "09:15:00"
    assert overnight[0]["min"] == 510.0


def test_an_hour_long_break_across_the_change_is_not_a_zero_length_one(live_aw):
    """The sharpest instance of one clock string for two instants. Both ends of this break
    read 02:30; unmarked it printed `02:30:00-02:30:00`, sixty minutes as a zero-length
    range — and a range `parse_range` would then refuse to read back as reversed."""
    got = probe(BY_NAME["fall-back-repeated-hour-day"], live_aw)
    breaks = [(b["start"], b["end"], b["min"]) for b in got["afk_json"]["breaks"]]
    assert breaks == [("02:30:00", "02:30:00*", 60.0)]


def test_two_spans_an_hour_apart_do_not_wear_the_same_clock_string(live_aw):
    """They abut on the clock and do not abut in time. The marker is the only thing
    separating `02:30:00` from the 02:30 an hour later, and the minutes are what say the
    hour between them was really counted: 60 + 105 is the day's whole 165."""
    got = probe(BY_NAME["fall-back-repeated-hour-day"], live_aw)
    afk = got["afk_json"]
    spans = [(s["start"], s["end"], s["min"]) for s in afk["active_spans"]]
    assert spans == [("01:30:00", "02:30:00", 60.0), ("02:30:00*", "04:15:00", 105.0)]
    assert afk["total_active_min"] == 165.0


def test_a_block_read_out_of_the_output_covers_the_hour_it_names(live_aw):
    """The round trip, which is the reason the marker is exact rather than decorative.
    `--cover 01:30-02:30,02:30*-04:15` is written in the notation the spans came back in;
    drop the marker and the second block claims 13:30Z onward — an hour of work nobody did,
    and an hour of real work left uncovered."""
    got = probe(BY_NAME["fall-back-repeated-hour-day"], live_aw)
    cov = got["afk_json"]["coverage_report"]
    assert cov["uncovered"] == []
    assert (cov["covered_active_min"], cov["total_active_min"]) == (165.0, 165.0)


def test_the_repeated_hour_is_measurable_as_a_window_of_its_own(live_aw):
    """`02:30-02:30*` names the hour between the two identical readings. It was previously
    unwritable — both ends resolved to one instant, so `parse_range` rejected it as
    reversed — and it has to come back as a real sixty minutes at a ratio of zero, not as
    an empty window that would read as 'nothing to see here'."""
    got = probe(BY_NAME["fall-back-repeated-hour-day"], live_aw)
    report = got["window_reports"]["02:30-02:30*"]
    assert report["window_min"] == 60.0
    assert (report["active_ratio"], report["verdict"]) == (0.0, "mostly idle (<0.4)")


def test_web_rows_in_the_repeated_hour_keep_the_order_they_happened_in(live_aw):
    """The runbook at 02:35 on the first pass really does precede the deploy log at 02:05
    on the second. Sorting the rendered strings reverses them and tells the model the day
    ran the other way round."""
    got = probe(BY_NAME["fall-back-repeated-hour-day"], live_aw)
    assert [(w["time"], w["title"]) for w in got["zoom_json"]["web"]] == [
        ("02:35:00", "ACME release runbook"),
        ("02:05:00*", "ACME deploy log"),
    ]


# --------------------------------------------------------------------------------------
# The write side of the same morning. `harvest_post` reads no ActivityWatch, so these take
# the fall-back scenario for its date and zone only — the point is that the script that
# *bills* the repeated hour answers for the same day the scripts that *read* it do.
# --------------------------------------------------------------------------------------

# The scenario's own two active spans, as one stretch worked straight through. `01:30` is
# before the change and `04:15` after it, so the clock says 2.75 hrs and 3.75 hrs really
# passed — the entry the ticket is about.
STRADDLE = ("01:30", "04:15")
# What the refusal has to name instead, in the plain HH:MM the script accepts. They read as
# though they overlap and do not: the transition instant is `03:00` as you reach it and
# `02:00` once it has passed, so the first ends where the second starts.
PIECES = (("01:30", "03:00"), ("02:00", "04:15"))

# The refusal in full, pinned the way a golden is. Substrings were tried first and cannot
# do this job: every assertion about the message survives text *appended* to it, so a
# rewrite ending "…they abut exactly and must be merged into one entry" passed a test whose
# name says it checks the opposite. This is the one message the ticket says an implementer
# must not second-guess, and its prose has been wrong once already — an earlier version of
# the same advice in `references/output-format.md` split at the break rather than at the
# transition and lost the exact hour it was written to save, which a review caught and no
# test could have. So any edit to it fails here and is made deliberately, with the numbers
# re-checked against the zone.
REFUSAL = (
    "ERR 01:30-04:15 on 2026-04-05 runs straight through the daylight-saving change in "
    "zone Pacific/Auckland.\n"
    "  Harvest bills the difference between the two clock times, so this entry would "
    "record 2.75 hrs against the 3.75 hrs that really passed. Post two entries instead:\n"
    "      01:30 03:00   (1.5 hrs)\n"
    "      02:00 04:15   (2.25 hrs)\n"
    "  Those two look like they overlap by 1.0 hrs and do not — they abut. The clocks go "
    "back at one instant, and that instant reads 03:00 as you reach it and 02:00 once it "
    "has passed, so the first entry ends and the second begins at the same moment. "
    "Closing the apparent overlap is what loses the 1.0 hrs that happened twice, which is "
    "why this is refused rather than split for you. Say in the day's notes that the clocks "
    "changed — the overlap is the first thing a reviewer will query.\n")


def create(monkeypatch, zone, date, start, end, *extra):
    """A create against a configured zone, run in-process. The ids are the fixtures' own."""
    monkeypatch.setenv("TIMESHEET_TIMEZONE", zone)
    return run_cli(hpost, ["48084036", "20753151", date, start, end, "Cutover", *extra])


def fall_back_day():
    """The date and zone of the scenario, without starting an ActivityWatch for them."""
    d = BY_NAME["fall-back-repeated-hour-day"].build()
    assert d.zone_name, "the fall-back scenario is written in a named zone, not an offset"
    return d.zone_name, d.date_str()


def test_a_create_straddling_the_change_is_refused_rather_than_billed_short(
        live_harvest, monkeypatch):
    """The defect, at the seam it reaches Harvest through. Harvest derives the duration
    from the two clock times, so this entry bills 2.75 hrs for 3.75 hrs of work and then
    reads correctly in every listing afterwards — there is no later moment at which anyone
    finds out. Asserted against the recorded requests as well as the exit code, because a
    script that posted and *then* complained would pass on the latter alone."""
    srv = live_harvest({("POST", "/time_entries"): (201, {"id": 4101})})
    zone, date = fall_back_day()
    r = create(monkeypatch, zone, date, *STRADDLE, "--confirm")

    assert srv.sent("POST", "/time_entries") == [], "nothing may reach the wire"
    assert r.code != 0
    assert "Traceback" not in r.err
    for start, end in PIECES:
        assert f"{start} {end}" in r.err, "the message has to name both entries to post"
    assert "3.75" in r.err, "and the hours the single entry would have lost"


def test_the_refusal_says_why_the_two_entries_it_names_are_not_an_overlap(
        live_harvest, monkeypatch):
    """The trap this whole guard is built around. `01:30`-`03:00` and `02:00`-`04:15` look
    like they overlap by an hour, and an implementer or a reviewer who "corrects" that
    reintroduces exactly the hour the refusal exists to save — which is how the hand-split
    guidance in `references/output-format.md` was wrong the first time it was written."""
    live_harvest({("POST", "/time_entries"): (201, {"id": 4102})})
    zone, date = fall_back_day()
    r = create(monkeypatch, zone, date, *STRADDLE, "--confirm")

    assert r.err == REFUSAL


def test_the_straddling_entry_is_never_previewed_either(live_harvest, monkeypatch):
    """Without `--confirm` this script prints the body it would have sent and exits 0, and
    that preview is what Step 8 shows the user to get their yes. An entry that will be
    refused must not be offered: shown one, a run collects the approval, appends the flag
    exactly as the preview's own last line says to, and only then meets the refusal — with
    a yes already recorded against an entry that cannot exist.

    Its own test because every other refusal test passes `--confirm`, so the guard could
    move below the preview and none of them would notice."""
    live_harvest({("POST", "/time_entries"): (201, {"id": 4104})})
    zone, date = fall_back_day()
    r = create(monkeypatch, zone, date, *STRADDLE)

    assert r.code != 0, "a preview of a refused entry is not the normal case"
    assert r.out == "", "nothing may be offered that cannot then be posted"
    assert "WOULD POST" not in r.out + r.err
    assert f"{PIECES[0][0]} {PIECES[0][1]}" in r.err


def test_the_two_entries_the_refusal_names_are_themselves_accepted(
        live_harvest, monkeypatch):
    """A guard that refused its own advice would be unusable, and this is the assertion
    that catches the obvious wrong rule. "The clock interval and the elapsed time
    disagree" is true of *both* replacement entries — `01:30`-`03:00` spans 1.5 hrs on the
    clock and 2.5 in real time if `03:00` is read as the unambiguous reading an hour after
    the change. Only the entry that contains the whole repeated hour is unambiguously
    wrong, and only that one may be refused."""
    srv = live_harvest({("POST", "/time_entries"): (201, {"id": 4103})})
    zone, date = fall_back_day()

    for start, end in PIECES:
        r = create(monkeypatch, zone, date, start, end, "--confirm")
        assert r.code == 0, f"{start}-{end} is one of the two entries to post: {r.err}"

    sent = [(r["body"]["started_time"], r["body"]["ended_time"])
            for r in srv.sent("POST", "/time_entries")]
    assert sent == list(PIECES), "and each goes on the wire as the user typed it"


def test_a_date_with_no_transition_posts_exactly_what_it_always_did(monkeypatch):
    """The same two clock times, on an ordinary day in a zone that has no transitions at
    all. The guard has to be invisible on the other 364 days: the preview line is the body
    itself, so pinning it whole is what says no field moved."""
    zone, _ = "Etc/GMT-12", None
    r = create(monkeypatch, zone, "2026-08-12", *STRADDLE)

    assert r.code == 0 and r.err == ""
    assert r.lines[0] == (
        'WOULD POST {"project_id": 48084036, "task_id": 20753151, '
        '"spent_date": "2026-08-12", "started_time": "01:30", "ended_time": "04:15", '
        '"notes": "Cutover"}')


def test_a_user_outside_new_zealand_gets_their_own_zones_day_boundaries(live_aw):
    """The criterion the whole timezone change exists for. Nothing about this run is New
    Zealand's: the day is written in `Europe/London`, the zone is the configured one, and
    the local clock comes back unshifted.

    Honest about its strength: this passed before the transition fix too, because a day
    with one offset all the way through is one a single offset describes. What it guards
    is the built-in `default=12.0` two releases back, which read this day as starting at
    20:00. The guards for the fix itself are the two transition tests above."""
    d = day(dt.date(2026, 5, 28), zone="Europe/London").active("09:00", "17:00")
    live_aw(d)
    result = run_cli(ab, [d.date_str(), "--json"]).json()
    assert (result["work_start"], result["work_end"]) == ("09:00:00", "17:00:00")


# --------------------------------------------------------------------------------------
# Heartbeats: the same day, re-emitted the way AW really sends it.
# --------------------------------------------------------------------------------------

@pytest.mark.parametrize("name", ["locked-screen-day", "blip-and-tail-day", "no-break-day"])
def test_heartbeat_duplicates_change_nothing(name, live_aw, monkeypatch):
    """AW extends a running event by re-emitting it at the same timestamp with a growing
    duration. Every number the skill bills against has to survive that, or a long focused
    stretch inflates by however many heartbeats AW happened to send."""
    scenario = BY_NAME[name]
    clean = probe(scenario, live_aw)

    d = scenario.build()
    original = d.buckets

    def noisy():
        return {bid: with_heartbeats(evs) for bid, evs in original().items()}

    monkeypatch.setattr(d, "buckets", noisy)
    live_aw(d)
    date, offset = d.date_str(), dating_args(d)
    args = [date, "--json", *offset] + (["--cover", scenario.cover] if scenario.cover else [])
    assert run_cli(ab, args).json() == clean["afk_json"]
