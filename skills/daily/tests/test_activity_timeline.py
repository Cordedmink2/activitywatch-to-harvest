import datetime as dt
import os, re, sys
SCRIPTS = os.path.join(os.path.dirname(__file__), "..", "scripts")
sys.path.insert(0, SCRIPTS)
import activity_timeline as at
from support import day

CLASSES = [
    ("ACME", re.compile("ACME", re.IGNORECASE)),
    ("BETA", re.compile("BETA", re.IGNORECASE)),
]

D = day(dt.date(2026, 6, 19), offset=0)


def test_categorize_matches_and_misses():
    assert at.categorize("Code.exe", "Welcome - ACME - Visual Studio Code", CLASSES) == ["ACME"]
    assert at.categorize("msedge.exe", "Find Cheap Flights - Google Flights", CLASSES) == []


def test_build_spans_merges_same_category_and_breaks_on_change():
    evs = [
        D.event("00:00", seconds=120, app="Code.exe", title="Welcome - ACME"),
        D.event("00:02", seconds=120, app="msedge.exe", title="CMS Board - ACME"),  # same cat, gap 0
        D.event("00:10", seconds=120, app="msedge.exe", title="Overleaf CV"),       # uncategorized, gap 8min
    ]
    spans = at.build_window_spans(evs, CLASSES)
    assert len(spans) == 2
    assert spans[0]["category"] == "ACME"
    assert spans[1]["category"] == "uncategorized"


def test_multi_match_flagged():
    evs = [D.event("00:00", seconds=60, app="x", title="ACME and BETA both")]
    spans = at.build_window_spans(evs, CLASSES)
    assert spans[0]["multi"] is True


def test_sub5s_dropped():
    evs = [D.event("00:00", seconds=3, app="x", title="ACME blip")]
    assert at.build_window_spans(evs, CLASSES) == []
