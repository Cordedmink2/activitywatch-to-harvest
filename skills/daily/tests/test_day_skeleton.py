"""The day skeleton and the timeline, reached as values rather than as printed output.

Both day-reading scripts pull their span arithmetic into functions and then used to do
the rest inside `main()`: the coverage union, the band verdict, the window-watcher tail,
the zoom mode's web-watcher merge, and the assembly of the result itself. Those were the
parts that had gone wrong, and the only thing that could reach them was a run of the
script. `test_scenarios.py` still pins every rendering against its golden; these hold the
pieces the goldens cannot name, at the function.
"""
from __future__ import annotations

import re

import pytest

import activity_timeline as tl
import afk_blocks as ab
from support import DEFAULT_DATE, day, fixed

ZONE = fixed(12)


def skeleton(d, **kw):
    return ab.day_skeleton(d.afk_events(), d.window_events(), d.date, d.tz,
                           afk_bucket="aw-watcher-afk_TESTHOST", **kw)


# --------------------------------------------------------------------------------------
# One call, one shape, nothing printed
# --------------------------------------------------------------------------------------

def test_the_skeleton_is_a_value_and_prints_nothing(capsys):
    """`main()` renders; the skeleton does not. A print inside it would reach the JSON
    output and break the parse for the reader that asked for JSON."""
    d = day().active("09:00", "12:00").afk("12:00", "12:40").active("12:40", "17:00")
    result = skeleton(d, window="09:00-10:00", cover="09:00-12:00")
    assert capsys.readouterr() == ("", "")
    assert result["work_start"] == "09:00:00" and result["work_end"] == "17:00:00"
    assert [b["min"] for b in result["breaks"]] == [40.0]


def test_the_empty_and_populated_days_have_one_shape():
    """`--json` output has to parse the same way whether or not the day held any activity;
    the empty result used to restate the key set in a second literal, with a comment
    hoping the two stayed in agreement."""
    empty = skeleton(day().afk("00:00", "24:00"))
    full = skeleton(day().active("09:00", "17:00"), window="09:00-10:00", cover="09:00-17:00")
    assert empty.keys() == full.keys()
    assert empty["work_start"] is None and empty["total_active_min"] == 0.0
    assert set(empty) == set(ab.empty_skeleton(DEFAULT_DATE, None))


def test_an_unreadable_window_on_an_empty_day_is_still_the_empty_skeleton():
    """As it always was: a day with no activity answers before the flags are read, so the
    reader hears "nothing happened" rather than a usage error about a probe it no longer
    needs. On a populated day the same flag is refused by name."""
    assert skeleton(day().afk("00:00", "24:00"), window="bogus")["work_start"] is None
    with pytest.raises(ab.UsageError, match=r"bad --window 'bogus'"):
        skeleton(day().active("09:00", "17:00"), window="bogus")
    with pytest.raises(ab.UsageError, match=r"bad --cover '09:00-x'.*HH:MM-HH:MM,\.\.\."):
        skeleton(day().active("09:00", "17:00"), cover="09:00-x")


@pytest.mark.parametrize("window", ["09:00-10:00,11:00-12:00", ",", "09:00-10:00,"],
                         ids=["two-ranges", "bare-comma", "trailing-comma"])
def test_a_window_is_one_range_and_a_comma_in_it_is_refused_by_name(window):
    """`--cover` is a list and `--window` is not; the first draft of the skeleton read both
    through one splitter, and a window with a comma in it either tracebacked on the unpack
    or was accepted with the comma echoed into the report. The review caught it."""
    with pytest.raises(ab.UsageError, match=r"bad --window '.*', expected HH:MM-HH:MM "):
        skeleton(day().active("09:00", "17:00"), window=window)


# --------------------------------------------------------------------------------------
# The three pieces that had gone wrong
# --------------------------------------------------------------------------------------
#
# `test_review_findings.py` and `test_scenarios.py` pin these through the script, where
# they were found. These are their function-level twins: the same facts, reachable without
# a run, so a change to the arithmetic is measured where it lives.

def test_union_ranges_merges_overlaps_and_touching_blocks_and_keeps_gaps():
    """Summing proposed blocks independently let two overlapping blocks report more covered
    activity than the day held. Touching blocks merge too — `<=`, not `<` — because a
    boundary shared to the second is one block written as two, not a gap of nothing."""
    d = day()
    t = d.at
    merged = ab.union_ranges([(t("13:00"), t("14:00")), (t("09:00"), t("11:00")),
                              (t("10:00"), t("12:00")), (t("12:00"), t("13:00"))])
    assert merged == [(t("09:00"), t("14:00"))]
    assert ab.union_ranges([(t("09:00"), t("10:00")), (t("11:00"), t("12:00"))]) == [
        (t("09:00"), t("10:00")), (t("11:00"), t("12:00"))]


@pytest.mark.parametrize("ratio,verdict", [
    (0.7, "active (>=0.7)"), (0.69, "thin (0.4-0.7)"), (0.4, "thin (0.4-0.7)"),
    (0.39, "mostly idle (<0.4)"),
], ids=["at-active", "under-active", "at-thin", "under-thin"])
def test_the_band_verdict_is_inclusive_at_both_thresholds(ratio, verdict):
    """The model bills on the word. Both bands are `>=`, so a ratio exactly on a threshold
    reads as the better band — the side SKILL.md's numbers were written for."""
    assert ab.band_verdict(ratio) == verdict


def test_the_window_watcher_tail_is_measured_against_work_end():
    """A foreground window that outlives the last not-afk moment is the left-in-focus
    trap; the tail says by how much, so the renderer can flag more than a minute."""
    d = (day().active("09:00", "17:00")
         .window("16:00", "17:25", "Code.exe", "left open"))
    tail = skeleton(d)["window_watcher_tail"]
    assert tail == {"end": "17:25:00", "gap_past_work_end_min": 25.0}
    assert skeleton(day().active("09:00", "17:00"))["window_watcher_tail"] is None


def test_the_text_rendering_reads_only_the_skeleton():
    """Both renderings consume the returned value, so what the model reads as text and
    what a test reads as JSON are one description of the day."""
    d = day().active("09:00", "17:00").window("16:00", "17:25", "Code.exe", "left open")
    result = skeleton(d, window="09:00-10:00")
    lines = ab.render_text(result, d.tz, focused=True)
    assert lines[0].startswith("AFK analysis for 2026-05-28")
    assert any("left-in-focus trap" in ln for ln in lines)
    assert not any(ln.startswith("  breaks") for ln in lines), "a focused probe drops the lists"
    assert any(re.search(r"active_ratio for 09:00-10:00: 1\.0 ", ln) for ln in lines)


# --------------------------------------------------------------------------------------
# The timeline's zoom mode
# --------------------------------------------------------------------------------------

def test_zoom_keeps_overlapping_spans_and_tabs_and_merges_browsers_by_instant():
    """Overlap, not containment: a tab opened before the zoom and still open inside it is
    usually the row that names the client. Two browsers are merged and sorted on the
    instant, so a Chrome tab from 09:10 comes before a Firefox tab from 09:20. The
    script-level twins are in `test_edge_timeline.py`; this is the function."""
    d = (day()
         .window("08:30", "09:30", "Code.exe", "CMS - ACME")      # straddles the zoom start
         .window("11:00", "12:00", "Code.exe", "after the zoom")
         .web("08:50", "09:05", "Portal", "https://portal.example", browser="firefox")
         .web("09:20", "09:25", "Docs", "https://docs.example", browser="firefox")
         .web("09:10", "09:12", "Board", "https://board.example", browser="chrome")
         .web("10:30", "10:40", "Later", "https://later.example", browser="chrome"))
    spans = tl.build_window_spans(d.window_events(), [])
    web = d.web_events("firefox") + d.web_events("chrome")
    inside, rows = tl.zoom(spans, web, d.at("09:00"), d.at("10:00"), d.tz)
    assert [(tl.local_clock(s["start"], d.tz)) for s in inside] == ["08:30:00"]
    assert [(r["time"], r["title"]) for r in rows] == [
        ("08:50:00", "Portal"), ("09:10:00", "Board"), ("09:20:00", "Docs")]


def test_the_timeline_is_a_value_with_web_rows_only_in_zoom_mode(capsys):
    """`web` is `None` outside zoom mode so a reader can tell "no tabs" from "not asked";
    the unreadable window is refused by name, and nothing is printed either way."""
    d = day().window("09:00", "09:30", "Code.exe", "CMS - ACME")
    plain = tl.timeline(d.window_events(), [], [], d.date, d.tz, "aw-watcher-window_TESTHOST")
    zoomed = tl.timeline(d.window_events(), [], [], d.date, d.tz, window="09:00-10:00")
    assert capsys.readouterr() == ("", "")
    assert plain["web"] is None and zoomed["web"] == []
    assert plain["spans"][0]["min"] == 30.0
    with pytest.raises(tl.UsageError, match=r"bad --window 'bogus'"):
        tl.timeline([], [], [], d.date, ZONE, window="bogus")
