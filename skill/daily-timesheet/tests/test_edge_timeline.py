"""Edge cases in the *content* view — the one the skill reads a client's name off.

`activity_timeline.py` does not produce a number anybody bills directly; it produces
the merged, category-tagged picture the skill reasons from when it decides which client
a stretch of the day belonged to. So its failure mode is not "the total is 6 minutes
out", it is "a span that touched two clients was silently handed to one of them", or
"a locked screen was folded into the block either side of it and billed".

`tests/test_activity_timeline.py` covers the four happy paths and `tests/test_scenarios.py`
covers whole days end to end. This file covers the seams between them: the exact
boundaries of the two constants, the shapes real watchers emit that no scenario contains,
the ways a settings file can be half-broken, and the rendering rules that decide what the
model ever gets to see.
"""
from __future__ import annotations

import datetime as dt
import gc
import re
import warnings

import pytest

import activity_timeline as at
from support import day, run_cli

# --------------------------------------------------------------------------------------
# Fixtures-in-miniature for the pure functions
# --------------------------------------------------------------------------------------

NZLS_FIRST = [("NZLS", re.compile("NZLS", re.IGNORECASE)),
              ("Connexis", re.compile("Connexis", re.IGNORECASE))]
CONNEXIS_FIRST = list(reversed(NZLS_FIRST))

_EPOCH = dt.datetime(2026, 6, 19, tzinfo=dt.timezone.utc)


def _ev(offset_s: float, duration: float, app: str = "Code.exe", title: str = "",
        data: dict | None = None) -> dict:
    """One AW window event, `offset_s` after an arbitrary UTC epoch.

    One fixed timestamp format throughout: `dedupe_heartbeats` sorts on the raw string,
    so mixing `Z` and `+00:00` suffixes would silently reorder the stream.
    """
    ts = (_EPOCH + dt.timedelta(seconds=offset_s)).strftime("%Y-%m-%dT%H:%M:%S+00:00")
    return {"timestamp": ts, "duration": duration,
            "data": {"app": app, "title": title} if data is None else data}


def _loaded(live_aw, classes: list[dict], **kw):
    """Serve `classes` as the AW settings payload and return `load_classes()`'s view of it.

    Raw dicts rather than `Day.classify`, because the interesting settings are the ones
    the builder cannot express: a parent category with no regex, or a regex that is not
    one. They must be attached before `live_aw` starts, which snapshots the settings.
    """
    d = day()
    d.classes.extend(classes)
    live_aw(d, **kw)
    return at.load_classes()


def _regex_class(label: str, pattern: str, ignore_case: bool = True) -> dict:
    return {"name": label.split(">"),
            "rule": {"type": "regex", "regex": pattern, "ignore_case": ignore_case}}


# --------------------------------------------------------------------------------------
# Boundaries: the two constants that decide what is one span and what is noise
# --------------------------------------------------------------------------------------

def test_an_event_of_exactly_five_seconds_is_kept_as_activity():
    """`NOISE_FLOOR` is a `<` test, so five seconds is the shortest thing that counts.
    Were it a `<=`, every glance at a client's window that lasted exactly the floor would
    vanish, and the day would read as if that client had never been opened at all."""
    spans = at.build_window_spans([_ev(0, 5, "Code.exe", "CMS - NZLS")], NZLS_FIRST)
    assert len(spans) == 1
    assert spans[0]["category"] == "NZLS"


def test_an_event_just_under_five_seconds_is_dropped_as_tab_switch_noise():
    """A tab flicked through on the way somewhere else must not open a span. If it did,
    passing through a client's tab would plant that client's name in the middle of another
    client's block, which is the misattribution the noise floor exists to prevent."""
    assert at.build_window_spans([_ev(0, 4.9, "Code.exe", "CMS - NZLS")], NZLS_FIRST) == []


def test_a_gap_of_exactly_sixty_seconds_breaks_a_span_in_two():
    """`GAP_FOLD` is a `<` test: a full minute away from the keyboard ends the span. The
    two halves stay separately timestamped, so a reader can see the minute of nothing
    rather than being shown one continuous stretch that was never continuous."""
    evs = [_ev(0, 60, "Code.exe", "CMS - NZLS"),
           _ev(120, 60, "Code.exe", "CMS - NZLS")]      # ends 60s, next starts 120s
    spans = at.build_window_spans(evs, NZLS_FIRST)
    assert len(spans) == 2
    assert [s["category"] for s in spans] == ["NZLS", "NZLS"]


def test_a_gap_of_fifty_nine_seconds_folds_into_one_span():
    """Below the fold the same-category halves become one span. Without this the timeline
    would shatter every real hour of work into dozens of rows, and the substantive blocks
    the skill is looking for would be buried under its own noise."""
    evs = [_ev(0, 60, "Code.exe", "CMS - NZLS"),
           _ev(119, 60, "Code.exe", "CMS - NZLS")]      # ends 60s, next starts 119s
    spans = at.build_window_spans(evs, NZLS_FIRST)
    assert len(spans) == 1
    assert (spans[0]["end"] - spans[0]["start"]).total_seconds() == 179


def test_two_touching_events_with_different_categories_stay_two_spans():
    """Zero gap is not a reason to merge. Switching straight from one client's window to
    another's is the commonest boundary in a real day, and folding it would hand the
    second client's minutes to the first under the first client's name."""
    evs = [_ev(0, 60, "Code.exe", "CMS - NZLS"),
           _ev(60, 60, "Code.exe", "Portal - Connexis")]
    spans = at.build_window_spans(evs, NZLS_FIRST)
    assert [s["category"] for s in spans] == ["NZLS", "Connexis"]
    assert spans[0]["end"] == spans[1]["start"], "the two spans must abut, not overlap"


# --------------------------------------------------------------------------------------
# Malformed and missing data, as the watchers actually emit it
# --------------------------------------------------------------------------------------

def test_an_event_with_no_app_key_is_categorised_from_its_title():
    """Some watcher builds omit `app` entirely. The script must fall back rather than
    raise: a `KeyError` here kills the whole timeline, so one malformed event costs the
    skill its view of the entire day and it falls back to guessing from memory."""
    evs = [_ev(0, 60, data={"title": "CMS Board - NZLS"})]
    spans = at.build_window_spans(evs, NZLS_FIRST)
    assert len(spans) == 1
    assert spans[0]["category"] == "NZLS"


@pytest.mark.parametrize("data", [{"app": "Code.exe"}, {"app": "Code.exe", "title": None}],
                         ids=["title-absent", "title-null"])
def test_an_event_with_a_missing_or_null_title_still_produces_a_span(data):
    """A titleless window is not a broken one — it is a splash screen, or an app that has
    not painted yet. It has to land as an uncategorized span the reader can see and ask
    about, not disappear and not take the timeline down with it."""
    spans = at.build_window_spans([_ev(0, 60, data=data)], NZLS_FIRST)
    assert len(spans) == 1
    assert spans[0]["category"] == "uncategorized"


def test_a_locked_windows_screen_logs_as_unknown_and_lands_uncategorized():
    """Windows records a locked screen as app `unknown` with an empty title. That stretch
    is the user being *away*; it must read as uncategorized so the skill treats it as time
    to question, never inherit the client of the window that happened to precede it."""
    evs = [_ev(0, 600, "Code.exe", "CMS - NZLS"),
           _ev(600, 1800, "unknown", "")]
    spans = at.build_window_spans(evs, NZLS_FIRST)
    assert [s["category"] for s in spans] == ["NZLS", "uncategorized"]
    assert spans[1]["categories"] == set()
    assert spans[1]["multi"] is False


# --------------------------------------------------------------------------------------
# load_classes(): half-broken settings must degrade, not detonate
# --------------------------------------------------------------------------------------

def test_load_classes_returns_empty_when_the_settings_endpoint_is_missing(live_aw):
    """Older AW builds have no `/settings`. An uncategorised timeline is still worth
    having — every span is there, just unlabelled — whereas a raised exception loses the
    times as well as the labels, and the skill has nothing left to reason from."""
    assert _loaded(live_aw, [], settings_status=404) == []


def test_an_unavailable_settings_endpoint_does_not_leak_the_error_response(live_aw):
    """`load_classes` swallows the error by design — and an `HTTPError` *is* the response,
    a file object over a spooled temp file. Swallowing it without closing it leaves the
    body for the garbage collector, which emits a `ResourceWarning` from a destructor.

    Harmless in the one-shot CLI, which exits moments later. It is pinned because this
    suite runs under `filterwarnings = error`: the warning surfaces at whatever unrelated
    test the collector happens to interrupt, so the leak reads as a failure somewhere with
    no connection to the settings endpoint at all. `aw_client.get()` closes it; this is
    the test that says it must keep doing so.
    """
    d = day()
    live_aw(d, settings_status=404)
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        assert at.load_classes() == []
        gc.collect()
    assert [w for w in caught if issubclass(w.category, ResourceWarning)] == []


def test_a_timeline_with_no_classes_still_reports_every_span(live_aw):
    """The consequence of the rule above, end to end: no settings endpoint means no
    labels, but the day's shape and its totals must survive so the user can still be
    asked "what were you doing at 09:00?"."""
    d = day().window("09:00", "09:30", "Code.exe", "CMS - NZLS")
    live_aw(d, settings_status=404)
    r = run_cli(at, [d.date_str(), "--json"])
    assert r.code == 0
    payload = r.json()
    assert [s["start"] for s in payload["spans"]] == ["09:00:00"]
    assert payload["rollup_min_by_category"] == {"uncategorized": 30.0}


def test_load_classes_skips_a_parent_category_whose_rule_is_not_a_regex(live_aw):
    """AW's tree has parent nodes carrying `type: "none"` and no pattern. Treating one as
    a rule would either crash on the absent regex or, worse, invent a label that matches
    everything — attaching the parent's client name to the whole day."""
    classes = [{"name": ["Work"], "rule": {"type": "none"}},
               _regex_class("Work>NZLS", "NZLS")]
    assert [label for label, _ in _loaded(live_aw, classes)] == ["Work>NZLS"]


def test_load_classes_skips_an_uncompilable_regex_without_losing_its_neighbours(live_aw):
    """One typo in the AW UI must cost exactly that one rule. If a bad pattern aborted the
    load, a stray bracket in an unrelated client's rule would strip the labels off every
    other client too, and the day would silently read as entirely uncategorized."""
    classes = [_regex_class("Alpha", "Alpha"),
               _regex_class("Broken", "(unclosed"),
               _regex_class("Beta", "Beta")]
    assert [label for label, _ in _loaded(live_aw, classes)] == ["Alpha", "Beta"]


def test_load_classes_honours_ignore_case_when_it_is_set(live_aw):
    """Window titles do not agree on capitalisation — `nzls.co.nz` in a browser tab, `NZLS`
    in a repo path. With the flag set they are the same client, and a span that misses only
    because of case lands uncategorized and gets billed to nobody."""
    classes = _loaded(live_aw, [_regex_class("NZLS", "NZLS", ignore_case=True)])
    assert at.categorize("firefox.exe", "concerns - nzls intranet", classes) == ["NZLS"]


def test_load_classes_does_not_fold_case_when_ignore_case_is_off(live_aw):
    """The flag has to mean something in both directions. A user who deliberately made a
    rule case-sensitive — to keep an acronym apart from an ordinary word — must get the
    narrow match, or the rule quietly claims spans belonging to another client."""
    classes = _loaded(live_aw, [_regex_class("NZLS", "NZLS", ignore_case=False)])
    assert at.categorize("firefox.exe", "concerns - nzls intranet", classes) == []
    assert at.categorize("firefox.exe", "concerns - NZLS intranet", classes) == ["NZLS"]


def test_load_classes_joins_a_nested_category_name_with_a_chevron(live_aw):
    """AW stores a nested category as a list of path segments. The joined label is what the
    skill reads the client off, so flattening it wrongly — or showing only the leaf —
    strands the reader with `CMS` and no idea which client's CMS it was."""
    classes = _loaded(live_aw, [_regex_class("Work>NZLS>CMS", "NZLS")])
    assert [label for label, _ in classes] == ["Work>NZLS>CMS"]


# --------------------------------------------------------------------------------------
# Categorisation: which client wins, and what the span remembers
# --------------------------------------------------------------------------------------

def test_the_primary_category_is_the_first_matching_class_in_settings_order():
    """When two clients' rules both match, the winner is decided by AW's own ordering and
    nothing else. Pinned in both directions, because a stable tie-break is the only reason
    the same day categorises the same way twice — and `!MULTI` is what says "check me"."""
    evs = [_ev(0, 60, "msedge.exe", "NZLS board vs Connexis migration")]
    assert at.build_window_spans(evs, NZLS_FIRST)[0]["category"] == "NZLS"
    assert at.build_window_spans(evs, CONNEXIS_FIRST)[0]["category"] == "Connexis"


def test_the_rollup_gives_an_ambiguous_event_wholly_to_its_primary_category():
    """Pinned, not endorsed. `category_rollup` credits `cats[0]` and nothing else, so an
    event whose title matches two clients puts 100% of its minutes on whichever rule AW
    ordered first — the other client contributes nothing to the totals at all, as the two
    orderings below show.

    Nothing splits the minutes and nothing in the rollup marks them as contested, which
    matters because the rollup is the number a day's split between clients is argued from.
    The compensating control is the *span*: the same event sets `multi`, the span renders
    `!MULTI`, and Step 4 sends the reader to investigate every one before billing. That is
    the only thing between this attribution and a wrong invoice, so a change that reorders
    the classes, or drops `!MULTI` from the rendering, has to confront this test.

    Deliberately not "fixed" by splitting the time: a title matching two rules says nothing
    about how the minutes actually divided, so any split would be invented precision — a
    plausible wrong number in place of a flagged one.
    """
    evs = [_ev(0, 600, "msedge.exe", "NZLS board vs Connexis migration")]

    assert at.category_rollup(evs, NZLS_FIRST) == {"NZLS": 10.0}
    assert at.category_rollup(evs, CONNEXIS_FIRST) == {"Connexis": 10.0}

    span = at.build_window_spans(evs, NZLS_FIRST)[0]
    assert sorted(span["categories"]) == ["Connexis", "NZLS"]
    assert span["multi"] is True, "the flag is the only signal that the rollup is contested"


def test_a_span_accumulates_every_category_matched_by_the_events_merged_into_it():
    """`category` names one client; `categories` is the honest list. Merging is what makes
    them diverge, and if the second client's name were dropped at the merge the span would
    look like a clean single-client block that nobody ever thinks to check."""
    evs = [_ev(0, 60, "Code.exe", "CMS - NZLS"),
           _ev(60, 60, "msedge.exe", "NZLS board vs Connexis migration")]
    spans = at.build_window_spans(evs, NZLS_FIRST)
    assert len(spans) == 1
    assert sorted(spans[0]["categories"]) == ["Connexis", "NZLS"]


def test_multi_stays_set_for_the_whole_span_once_any_event_matched_two_clients():
    """The flag is sticky by design: a single ambiguous window contaminates everything
    folded around it. If a later single-client event cleared it, the span would print
    without `!MULTI` and the one thing the skill must never bill unreviewed sails through."""
    ambiguous = _ev(0, 60, "msedge.exe", "NZLS board vs Connexis migration")
    single = _ev(60, 60, "Code.exe", "CMS - NZLS")
    for order in ([ambiguous, single], [single, ambiguous]):
        spans = at.build_window_spans(order, NZLS_FIRST)
        assert len(spans) == 1, "same primary, no gap — these must merge"
        assert spans[0]["multi"] is True


def test_the_rollup_totals_the_event_durations_that_fed_the_spans():
    """The rollup counts *events*, while a span's width counts wall-clock including the
    sub-minute gaps folded inside it. The rollup is the number a day's split between
    clients is argued from, so it has to reconcile against the events, not the spans."""
    evs = [_ev(0, 600, "Code.exe", "CMS - NZLS"),          # 10 min NZLS
           _ev(630, 600, "Code.exe", "CMS - NZLS"),        # 10 min NZLS, gap folds
           _ev(1800, 300, "msedge.exe", "Portal - Connexis"),   # 5 min Connexis
           _ev(2400, 60, "explorer.exe", "Downloads"),     # 1 min uncategorized
           _ev(2500, 4, "explorer.exe", "Downloads")]      # noise, counted nowhere
    assert at.category_rollup(evs, NZLS_FIRST) == {
        "NZLS": 20.0, "Connexis": 5.0, "uncategorized": 1.0}
    # ...and the merged span is wider than the events inside it, which is why the two
    # numbers are not interchangeable.
    spans = at.build_window_spans(evs, NZLS_FIRST)
    assert (spans[0]["end"] - spans[0]["start"]).total_seconds() == 1230


# --------------------------------------------------------------------------------------
# Rendering: what the model actually gets shown
# --------------------------------------------------------------------------------------

def _two_client_day():
    """A day holding one substantial block, one short ambiguous blip, one short dull blip."""
    return (day()
            .classify("NZLS", "NZLS")
            .classify("Connexis", "Connexis")
            .window("09:00", "09:30", "Code.exe", "CMS Board - NZLS")
            .window("11:00", "11:00:30", "msedge.exe", "NZLS board vs Connexis migration")
            .window("13:00", "13:00:30", "explorer.exe", "Downloads"))


def test_default_text_mode_hides_short_spans_and_names_the_flag_that_reveals_them(live_aw):
    """The compaction is a context-saving measure, so it owes the reader a receipt. A
    silent drop would leave the model believing 13:00 was idle when it was half a minute
    of somebody's work; the hidden line is what turns an omission into a question."""
    d = _two_client_day()
    live_aw(d)
    r = run_cli(at, [d.date_str()])
    assert r.code == 0
    assert "13:00:00" not in r.out, "a 0.5-minute uncategorized span is below --min-span"
    hidden = [ln for ln in r.lines if "hidden" in ln]
    assert len(hidden) == 1
    assert "1 sub-3min spans hidden" in hidden[0]
    assert "--full" in hidden[0], "the reader must be told how to see what was hidden"


def test_a_short_multi_span_is_shown_even_though_it_is_under_min_span(live_aw):
    """The one exemption from compaction. Thirty seconds naming two clients is precisely
    the span the skill must confirm before billing, so length must never be allowed to
    hide it — while an equally short unambiguous span in the same day still goes."""
    d = _two_client_day()
    live_aw(d)
    r = run_cli(at, [d.date_str()])
    multi = [ln for ln in r.lines if "!MULTI" in ln]
    assert len(multi) == 1
    assert "11:00:00" in multi[0]
    assert "13:00:00" not in r.out, "keeping it must turn on multi, not on being short"


def test_full_shows_every_span_and_prints_no_hidden_line(live_aw):
    """`--full` is the escape hatch the hidden line advertises. If it still suppressed
    anything the advertisement would be a lie, and a user chasing a missing half-hour
    would conclude the time was never recorded."""
    d = _two_client_day()
    live_aw(d)
    r = run_cli(at, [d.date_str(), "--full"])
    assert r.code == 0
    for start in ("09:00:00", "11:00:00", "13:00:00"):
        assert start in r.out, start
    assert "hidden" not in r.out


def test_a_span_hidden_from_the_text_output_is_still_counted_in_the_rollup(live_aw):
    """Compaction may cost visibility, never minutes. The rollup is the day's arithmetic;
    if hiding a span also deducted it, every short stretch would be billed to nobody and
    the totals would quietly fall short of the day the user actually worked."""
    d = _two_client_day()
    live_aw(d)
    text = run_cli(at, [d.date_str()])
    assert "13:00:00" not in text.out
    rollup = run_cli(at, [d.date_str(), "--json"]).json()["rollup_min_by_category"]
    assert rollup == {"NZLS": 30.5, "uncategorized": 0.5}
    # the printed day totals say the same thing the JSON does, hidden span included
    totals = [ln.split() for ln in text.lines if ln.startswith("     ")]
    assert ["uncategorized", "0.5"] in totals


def test_json_carries_the_spans_the_text_mode_hid(live_aw):
    """Text and JSON are two views of one `result` dict — the text one filtered, the JSON
    one whole. A consumer parsing the JSON must get every span, or the skill's structured
    path would silently disagree with what it printed a moment earlier."""
    d = _two_client_day()
    live_aw(d)
    text = run_cli(at, [d.date_str()])
    payload = run_cli(at, [d.date_str(), "--json"]).json()
    starts = [s["start"] for s in payload["spans"]]
    assert starts == ["09:00:00", "11:00:00", "13:00:00"]
    assert "13:00:00" not in text.out, "the hidden span exists in JSON and not in text"
    # and --full renders exactly the spans JSON reports
    full = run_cli(at, [d.date_str(), "--full"])
    for s in payload["spans"]:
        assert any(s["start"] in ln and s["end"] in ln for ln in full.lines), s["start"]


def test_window_restricts_the_spans_and_folds_in_both_browsers(live_aw):
    """Zoom mode is what the skill reaches for when a block is ambiguous, and the URLs are
    the evidence. Reading only firefox would make a Chrome-based afternoon look like an
    hour of nothing, and the client behind it would have to be guessed.

    The 13:20-13:40 span straddles the zoom's start: the filter is an *overlap* test, not
    containment, because the work at the edge of an ambiguous block is usually the work
    that explains it, and dropping it would leave the zoom explaining the wrong half.
    """
    d = (day()
         .classify("NZLS", "NZLS")
         .window("09:00", "09:30", "Code.exe", "CMS Board - NZLS")
         .window("13:20", "13:40", "Code.exe", "Straddles the zoom edge - NZLS")
         .window("14:00", "14:30", "Code.exe", "Concerns - NZLS")
         .web("14:05", "14:10", "Board - NZLS", "https://dev.azure.com/nzls", browser="firefox")
         .web("14:12", "14:15", "Confidential teams", "https://learn.example.com/teams",
              browser="chrome"))
    live_aw(d)
    payload = run_cli(at, [d.date_str(), "--window", "13:30-15:00", "--json"]).json()
    assert [s["start"] for s in payload["spans"]] == ["13:20:00", "14:00:00"], (
        "09:00 is outside the zoom; 13:20-13:40 overlaps its start and must be kept")
    assert [r["url"] for r in payload["web"]] == ["https://dev.azure.com/nzls",
                                                  "https://learn.example.com/teams"]
    assert [r["time"] for r in payload["web"]] == ["14:05:00", "14:12:00"]


def test_a_browser_tab_open_across_the_start_of_the_zoom_is_not_dropped(live_aw):
    """Spans used an overlap test while web rows keyed on the event's start alone, so a
    tab opened before the zoom and still open inside it vanished from the evidence list.

    That is backwards for what zoom is for. The skill zooms a block precisely because it
    cannot tell whose work it is, and a tab left open across the boundary — a Dataverse
    org, a client's SharePoint — is exactly the row that names the client. Dropping it
    leaves the zoom reporting "no web activity" for a block spent in one browser tab.
    """
    d = (day()
         .classify("NZLS", "NZLS")
         .window("13:00", "14:30", "msedge.exe", "Power Apps")
         .web("13:20", "13:50", "Confidential Matter - example-uat", "https://example-uat.crm6.dynamics.com/main.aspx")
         .web("13:45", "13:50", "Started inside the zoom", "https://example.invalid/inside"))
    live_aw(d)
    payload = run_cli(at, [d.date_str(), "--window", "13:30-14:00", "--json"]).json()
    urls = [r["url"] for r in payload["web"]]
    assert "https://example-uat.crm6.dynamics.com/main.aspx" in urls, (
        "the tab open across 13:30 is the one that names the client")
    assert "https://example.invalid/inside" in urls


def test_a_browser_tab_that_closed_before_the_zoom_stays_out(live_aw):
    """The other half of the overlap rule: widening it must not drag in the whole day."""
    d = (day()
         .classify("NZLS", "NZLS")
         .window("13:00", "14:30", "msedge.exe", "Power Apps")
         .web("09:00", "09:30", "Breakfast reading", "https://example.invalid/morning"))
    live_aw(d)
    payload = run_cli(at, [d.date_str(), "--window", "13:30-14:00", "--json"]).json()
    assert payload["web"] == []


def test_a_long_web_title_and_url_are_truncated_for_the_reader(live_aw):
    """A single Dataverse or ADO URL runs to hundreds of characters. Left whole, one row
    swamps the zoom the skill asked for and the surrounding evidence scrolls out of
    view — so title stops at 60 characters and url at 80, both from the front."""
    title = "T" * 100
    url = "https://example.com/" + "u" * 200
    d = (day()
         .window("14:00", "14:30", "firefox.exe", "long tab")
         .web("14:05", "14:10", title, url, browser="firefox"))
    live_aw(d)
    payload = run_cli(at, [d.date_str(), "--window", "13:30-15:00", "--json"]).json()
    row = payload["web"][0]
    assert len(row["title"]) == 60 and row["title"] == title[:60]
    assert len(row["url"]) == 80 and row["url"] == url[:80]
