"""Timing tripwires, not correctness tests. Skipped unless you pass `--bench`.

    python -m pytest --bench -s tests/test_bench.py

These exist for one reason: the skill runs these scripts interactively, several times per
timesheet, and a run that used to take a second and now takes forty is a silent
regression nothing else in this suite would notice. The ceilings are deliberately loose —
roughly 20x the observed time on an unremarkable laptop — so they catch a change in
*complexity class*, not a slow afternoon. A benchmark that goes red when a machine is
busy teaches people to ignore benchmarks.

The workload is a 10,000-event day, which is the `limit=10000` the scripts ask AW for:
the largest input the real system can hand them.
"""
from __future__ import annotations

import datetime as dt
import re
import time
from contextlib import contextmanager

import pytest

import activity_timeline as tl
import afk_blocks as ab
import aw_client as aw
from support import day, run_cli

pytestmark = pytest.mark.bench

AW_EVENT_LIMIT = 10_000


@contextmanager
def timed(label: str, ceiling_s: float):
    start = time.perf_counter()
    yield
    elapsed = time.perf_counter() - start
    print(f"\n[bench] {label:<38} {elapsed * 1000:8.1f} ms   (ceiling {ceiling_s * 1000:.0f} ms)")
    assert elapsed < ceiling_s, (
        f"{label} took {elapsed:.2f}s, over the {ceiling_s}s tripwire. This is a "
        f"complexity regression, not a slow machine — the ceiling is ~20x normal."
    )


def synthetic_afk_events(n: int = AW_EVENT_LIMIT) -> list[dict]:
    """A day chopped into `n` alternating active/idle events. Pathological on purpose:
    real days hold hundreds of AFK events, so this is the shape of an AW instance whose
    watcher is flapping."""
    base = dt.datetime(2026, 5, 27, 20, 0, tzinfo=dt.timezone.utc)
    return [{"timestamp": (base + dt.timedelta(seconds=i * 4)).strftime("%Y-%m-%dT%H:%M:%SZ"),
             "duration": 4.0,
             "data": {"status": "not-afk" if i % 3 else "afk"}}
            for i in range(n)]


def synthetic_window_events(n: int = AW_EVENT_LIMIT) -> list[dict]:
    """Durations must clear `NOISE_FLOOR`, or the timeline drops every event and the
    benchmark measures an empty loop. (It did, on the first draft of this file.)"""
    base = dt.datetime(2026, 5, 27, 20, 0, tzinfo=dt.timezone.utc)
    apps = ["Code.exe", "msedge.exe", "WindowsTerminal.exe", "ms-teams.exe"]
    assert 6.0 >= tl.NOISE_FLOOR
    return [{"timestamp": (base + dt.timedelta(seconds=i * 6)).strftime("%Y-%m-%dT%H:%M:%SZ"),
             "duration": 6.0,
             "data": {"app": apps[i % len(apps)], "title": f"ticket NLS{2000 + i % 40}S - work"}}
            for i in range(n)]


def test_bench_afk_day_arithmetic():
    """The whole `afk_blocks` pipeline over a maxed-out event stream."""
    events = aw.dedupe_heartbeats(synthetic_afk_events())
    with timed("afk: spans + bounds + breaks + active", 2.0):
        spans = ab.to_spans(events)
        bounds = ab.work_bounds(spans)
        ab.total_active_seconds(spans)
        ab.find_breaks(spans, bounds["work_start"], bounds["work_end"], ab.DEFAULT_THRESHOLD)
        ab.active_spans(spans, ab.DEFAULT_THRESHOLD)


def test_bench_uncovered_segments_against_many_proposed_blocks():
    """`uncovered_segments` walks every proposed block against every surviving fragment of
    every active span. That nesting is where a quadratic blow-up would hide, and a
    backfill run passes a whole week of blocks at once."""
    spans = ab.to_spans(aw.dedupe_heartbeats(synthetic_afk_events()))
    active = ab.active_spans(spans, ab.DEFAULT_THRESHOLD)
    start = spans[0][0]
    proposed = [(start + dt.timedelta(minutes=15 * i), start + dt.timedelta(minutes=15 * i + 10))
                for i in range(200)]
    with timed("afk: uncovered_segments x200 blocks", 5.0):
        ab.uncovered_segments(spans, active, proposed)


def test_bench_dedupe_heartbeats_on_a_storm():
    """AW re-emits a running event on every heartbeat. A long focused stretch can arrive
    as tens of thousands of near-duplicates, and dedupe sees all of them."""
    events = synthetic_afk_events()
    storm = [{**e, "duration": e["duration"] * f} for f in (0.25, 0.5, 1.0) for e in events]
    with timed(f"aw: dedupe_heartbeats ({len(storm)} events)", 3.0):
        aw.dedupe_heartbeats(storm)


def test_bench_timeline_span_building_with_a_full_ruleset():
    """Every event is matched against every class regex, so cost scales with the product.
    A user with a rule per client accumulates these faster than they expect."""
    classes = [(f"Client{i}", re.compile(f"NLS{2000 + i}|client-{i}", re.IGNORECASE))
               for i in range(40)]
    events = synthetic_window_events()
    spans = None
    with timed("timeline: build_window_spans (40 rules)", 5.0):
        spans = tl.build_window_spans(events, classes)
    assert spans, "the workload must survive the noise floor, or this measures nothing"
    with timed("timeline: category_rollup (40 rules)", 5.0):
        rollup = tl.category_rollup(events, classes)
    assert rollup


def test_bench_end_to_end_through_the_fake_server(live_aw):
    """The number that matters to a human: one `afk_blocks` invocation, HTTP and all."""
    d = day()
    for hour in range(8, 18):
        d.thin(f"{hour:02d}:00", f"{hour + 1:02d}:00", active_min=1, idle_min=1)
        d.window(f"{hour:02d}:00", f"{hour + 1:02d}:00", "Code.exe", f"work hour {hour}")
    live_aw(d)
    with timed("end-to-end: afk_blocks --json --cover", 10.0):
        r = run_cli(ab, [d.date_str(), "--json", "--cover", "08:00-12:00,13:00-18:00"])
    assert r.code == 0
