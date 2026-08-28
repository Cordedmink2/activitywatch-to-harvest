import os, re, sys
SCRIPTS = os.path.join(os.path.dirname(__file__), "..", "scripts")
sys.path.insert(0, SCRIPTS)
import activity_timeline as at

CLASSES = [
    ("ACME", re.compile("ACME", re.IGNORECASE)),
    ("BETA", re.compile("BETA", re.IGNORECASE)),
]


def _ev(ts, dur, app, title):
    return {"timestamp": ts, "duration": dur, "data": {"app": app, "title": title}}


def test_categorize_matches_and_misses():
    assert at.categorize("Code.exe", "Welcome - ACME - Visual Studio Code", CLASSES) == ["ACME"]
    assert at.categorize("msedge.exe", "Find Cheap Flights - Google Flights", CLASSES) == []


def test_build_spans_merges_same_category_and_breaks_on_change():
    evs = [
        _ev("2026-06-19T00:00:00+00:00", 120, "Code.exe", "Welcome - ACME"),
        _ev("2026-06-19T00:02:00+00:00", 120, "msedge.exe", "CMS Board - ACME"),  # same cat, gap 0
        _ev("2026-06-19T00:10:00+00:00", 120, "msedge.exe", "Overleaf CV"),       # uncategorized, gap 8min
    ]
    spans = at.build_window_spans(evs, CLASSES)
    assert len(spans) == 2
    assert spans[0]["category"] == "ACME"
    assert spans[1]["category"] == "uncategorized"


def test_multi_match_flagged():
    evs = [_ev("2026-06-19T00:00:00+00:00", 60, "x", "ACME and BETA both")]
    spans = at.build_window_spans(evs, CLASSES)
    assert spans[0]["multi"] is True


def test_sub5s_dropped():
    evs = [_ev("2026-06-19T00:00:00+00:00", 3, "x", "ACME blip")]
    assert at.build_window_spans(evs, CLASSES) == []
