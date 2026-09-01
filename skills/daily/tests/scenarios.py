"""Whole-day scenarios: the complex cases the unit tests don't reach.

Each one is a shape the skill has actually had to reason about, written as a synthetic
day the fake ActivityWatch serves. `test_scenarios.py` runs every script against every
scenario and compares the complete output to a checked-in golden file, so a change in
the day arithmetic shows up as a reviewable diff rather than as a wrong timesheet.

Adding a scenario: define it here, run `pytest --regen-golden`, read the new golden file
to confirm it says what you meant, commit both. A golden nobody read is worthless.
"""
from __future__ import annotations

import datetime as dt
from dataclasses import dataclass, field
from typing import Callable

from support import Day, day

# Client names and environment hostnames here are deliberately fictional — these fixtures ship
# in a public repo, so a real client name or tenant URL in a window title would publish the
# maintainer's client list or their infrastructure detail. Keep new fixtures to the same
# placeholder family (ACME / BETA / Ledger / Nimbus) and to `example.*` / `*.invalid` hosts.
ACME = ("ACME", r"ACME|example-uat|example-dev|sharepoint-access-sync")
BETA = ("BETA", r"BETA|Field Services")

# The one zone in these fixtures, named rather than repeated: the daylight-saving days are
# about a zone's transitions, and a scenario that quietly used a different one would prove
# nothing about the dates the others were chosen for.
NZ = "Pacific/Auckland"


@dataclass
class Scenario:
    """One day plus the probes the skill would run against it."""
    name: str
    build: Callable[[], Day]
    cover: str | None = None            # --cover argument for afk_blocks
    windows: tuple[str, ...] = ()       # --window probes for afk_blocks
    zoom: str | None = None             # --window zoom for activity_timeline
    extra_args: tuple[str, ...] = field(default_factory=tuple)
    doc: str = field(init=False)        # the builder's docstring — see __post_init__

    def __post_init__(self):
        """A scenario's prose is its builder's docstring, read here rather than passed in.

        It used to be both: every entry below named the same function twice, once to build
        the day and once for `.__doc__`. Reading it from the builder makes the two
        impossible to mismatch, and makes a builder with no docstring an error at import
        rather than a scenario that silently describes nothing.
        """
        if self.build.__doc__ is None:
            raise ValueError(f"{self.build.__name__} needs a docstring — it is what "
                             f"describes the '{self.name}' scenario")
        self.doc = self.build.__doc__


# --------------------------------------------------------------------------------------


def _locked_screen_day() -> Day:
    """The 2026-08-12 shape, and the reason this harness exists.

    Two screen locks fragment the AFK record below the break threshold, so the script
    reports no breaks at all on a day with 99 minutes of absence. Between them sit two
    long agent-supervision stretches whose ratio reads ~0.6 despite being billable work,
    a 22-minute personal-browsing run that is active-but-not-billable, and an 8-minute
    tail that falls under the 0.25 hr floor.
    """
    d = day(dt.date(2026, 8, 12))
    d.classify(*ACME)
    d.afk("00:00", "08:12")
    d.active("08:12", "10:57")
    d.locked("10:57", "11:45")
    d.thin("11:45", "13:26", active_min=6, idle_min=4)
    d.active("13:26", "13:48")                      # personal: home media server admin
    d.thin("13:48", "18:02", active_min=7, idle_min=5)
    d.locked("18:02", "18:53")
    d.active("18:53", "19:01")                      # real work, under the billing floor
    d.afk("19:01", "24:00")

    d.window("08:12", "08:30", "ms-teams.exe", "Meeting | Daily Standup")
    d.window("08:30", "10:57", "Code.exe", "sharepoint-access-sync - Visual Studio Code")
    d.window("10:57", "11:45", "unknown", "")       # LockApp reads as unknown
    d.window("11:45", "13:26", "WindowsTerminal.exe", "claude - CLAUDE.md")
    d.window("13:26", "13:48", "firefox.exe", "Jellyfin - Home Media")
    d.window("13:48", "18:02", "WindowsTerminal.exe", "claude - AGENTS.md")
    d.window("18:02", "18:53", "unknown", "")
    d.window("18:53", "19:01", "msedge.exe", "Power Apps - example-uat.crm6.dynamics.com")
    d.web("13:26", "13:48", "Jellyfin", "https://jellyfin.example.invalid/web/index.html")
    return d


def _blip_and_tail_day() -> Day:
    """A textbook day carrying the two end-of-day traps at once.

    A one-minute mouse nudge at 19:30 sets `work_end` two hours after the last real work
    (`blip`), and a terminal left in the foreground until 22:00 makes the *window* watcher
    claim activity for another 2.5 hours after that (`window_watcher_tail`). Billing to
    either number invents most of an evening.
    """
    d = day(dt.date(2026, 8, 11))
    d.classify(*ACME)
    d.afk("00:00", "08:00")
    d.active("08:00", "12:15")
    d.afk("12:15", "13:10")                          # a real, reported lunch break
    d.active("13:10", "17:20")
    d.afk("17:20", "19:30")
    d.active("19:30", "19:31")                       # the flicker
    d.afk("19:31", "24:00")

    d.window("08:00", "12:15", "Code.exe", "CasePlugins - ACME - Visual Studio Code")
    d.window("13:10", "17:20", "msedge.exe", "Complaints - example-dev.crm6.dynamics.com")
    d.window("17:20", "22:00", "WindowsTerminal.exe", "pwsh")   # left in focus
    return d


def _interleaved_clients_day() -> Day:
    """Two clients in one day, with the switch buried inside a single active span.

    Also carries a genuinely ambiguous span (a title matching both client rules, which
    the timeline must flag `!MULTI`) and a long uncategorized stretch — the two shapes
    the skill is told to investigate rather than accept.
    """
    d = day(dt.date(2026, 8, 6))
    d.classify(*ACME)
    d.classify(*BETA)
    d.afk("00:00", "08:20")
    d.active("08:20", "11:50")
    d.afk("11:50", "12:35")
    d.active("12:35", "16:45")
    d.afk("16:45", "24:00")

    d.window("08:20", "08:35", "ms-teams.exe", "Meeting | Standup")
    d.window("08:35", "10:10", "Code.exe", "CasePlugins - ACME")
    d.window("10:10", "10:25", "ms-teams.exe", "Call with BETA - Field Services handover")
    d.window("10:25", "11:50", "msedge.exe", "BETA Field Services - admin")
    d.window("12:35", "13:40", "XrmToolBox.exe", "XrmToolBox")            # names no client
    d.window("13:40", "14:05", "msedge.exe", "ACME / BETA shared migration notes")  # !MULTI
    d.window("14:05", "16:45", "Code.exe", "field-services-api - BETA")
    d.web("10:25", "11:50", "BETA admin", "https://beta.example/admin")
    return d


def _no_break_day() -> Day:
    """No AFK run reaches the threshold, so the whole day is one active span.

    The span-level ratio passes 0.7 while hiding three nearly-dead stretches inside it —
    the exact configuration that made two of four test agents over-bill by 1.7 hours
    before Step 6 guard 1 was scoped (see TESTING.md).
    """
    d = day(dt.date(2026, 8, 5))
    d.classify(*ACME)
    d.afk("00:00", "08:15")
    d.active("08:15", "10:30")
    d.locked("10:30", "11:00", chunk_min=10)
    d.active("11:00", "13:00")
    d.locked("13:00", "13:35", chunk_min=11)
    d.active("13:35", "15:40")
    d.locked("15:40", "16:10", chunk_min=15)
    d.active("16:10", "17:30")
    d.afk("17:30", "24:00")
    d.window("08:15", "17:30", "Code.exe", "CasePlugins - ACME")
    return d


def _overnight_day() -> Day:
    """Work running past local midnight.

    The local day is bounded at midnight, so the final span's end renders as `01:12:00` —
    a `work_end` that reads *earlier* than `work_start`. Pinned because it is the one
    output where a naive string comparison of the two times gives the wrong answer.
    """
    d = day(dt.date(2026, 8, 4))
    d.classify(*ACME)
    d.afk("00:00", "19:30")
    d.active("19:30", "22:40")
    d.afk("22:40", "23:05")
    d.active("23:05", "25:12")            # 01:12 the following morning
    d.window("19:30", "25:12", "Code.exe", "release-cutover - ACME")
    return d


def _idle_day() -> Day:
    """A machine left on with nobody at it: AFK all day, not one `not-afk` event."""
    d = day(dt.date(2026, 8, 3))
    d.classify(*ACME)
    d.afk("00:00", "24:00")
    d.window("09:00", "17:00", "unknown", "")
    return d


def _daylight_saving_day() -> Day:
    """The same clock times during summer time, when the zone is an hour off its winter
    offset (`Pacific/Auckland` is UTC+13 on 2026-01-20, UTC+12 in July).

    Written against the zone, not a number: the run passes no `--utc-offset` at all, so
    what this pins is that the *configured* zone alone dates the day correctly. Every span
    is written in local time, so a correct resolution reproduces the local rendering
    exactly; resolving to the winter offset would shift the whole day by an hour.
    """
    d = day(dt.date(2026, 1, 20), zone=NZ)
    d.classify(*ACME)
    d.afk("00:00", "08:30")
    d.active("08:30", "12:00")
    d.afk("12:00", "12:45")
    d.active("12:45", "17:15")
    d.afk("17:15", "24:00")
    d.window("08:30", "17:15", "Code.exe", "CasePlugins - ACME")
    return d


def _daylight_saving_transition_day() -> Day:
    """The day the clocks actually change, which no single offset can describe.

    `Pacific/Auckland` goes back an hour at 03:00 on 2026-04-05, so that local day is
    twenty-five hours long: 00:40 that morning is UTC+13 and 09:15 is UTC+12. The day
    therefore runs from 11:00Z on the 4th to 12:00Z on the 5th, and an early session
    before the change has to render at the offset in force *then*.

    Reading one offset for the whole day — at local noon, which is the winter one — gets
    both ends wrong at once: the fetch window starts an hour late, so the first hour of
    work is never asked for, and what does come back renders an hour early, putting a
    00:40 start at 23:40 the previous evening. Neither failure raises anything; the day
    just reads short and starts in the wrong place.

    The spans deliberately avoid 02:00-03:00, the hour that happens twice, so that this
    day pins the conversion and nothing else. `_fall_back_repeated_hour_day` is its
    complement and works inside that hour.
    """
    d = day(dt.date(2026, 4, 5), zone=NZ)
    d.classify(*ACME)
    d.afk("00:00", "00:40")
    d.active("00:40", "01:45")            # before the change: UTC+13
    d.afk("01:45", "09:15")               # spans it
    d.active("09:15", "12:30")            # after the change: UTC+12
    d.afk("12:30", "13:20")
    d.active("13:20", "17:00")
    d.afk("17:00", "24:00")
    d.window("00:40", "01:45", "Code.exe", "release-cutover - ACME")
    d.window("09:15", "17:00", "Code.exe", "CasePlugins - ACME")
    # A web row in the pre-change session, so the zoom's web-watcher path renders a time
    # on the far side of the transition rather than only the span list.
    d.web("00:40", "01:45", "ACME release runbook", "https://acme.example/runbook")
    return d


def _fall_back_repeated_hour_day() -> Day:
    """Work either side of the hour that happens twice, which one clock string cannot tell
    apart.

    `Pacific/Auckland` goes back at 03:00 on 2026-04-05, so local 02:00-03:00 runs once at
    UTC+13 and again at UTC+12. A cutover team working through it stops at 02:30, waits an
    hour for a restore, and resumes at 02:30 — the same reading, sixty minutes later.

    Every ambiguity the skill can emit is in here at once. The break is the sharpest:
    unmarked it renders `02:30:00-02:30:00`, an hour off shown as a zero-length string,
    which is also a range `parse_range` would refuse to read back. The two active spans
    abut on the clock and do not abut in time. And the two web rows are ordered against
    the clock — the runbook at 02:35 on the first pass really does precede the deploy log
    at 02:05 on the second — so a sort on the rendered string reverses them.

    The `*` suffix is what separates them, and it is exact rather than decorative: the
    `cover` and `windows` probes below are written in the notation the goldens come back
    in, so the golden is also the round-trip test.
    """
    d = day(dt.date(2026, 4, 5), zone=NZ)
    d.classify(*ACME)
    d.afk("00:00", "01:30")
    d.active("01:30", "02:30")            # first pass over 02:00-03:00: UTC+13
    d.afk("02:30", "02:30*")              # an hour, both ends reading 02:30
    d.active("02:30*", "04:15")           # second pass, then out the far side: UTC+12
    d.afk("04:15", "24:00")

    d.window("01:30", "02:30", "Code.exe", "release-cutover - ACME")
    d.window("02:30*", "04:15", "Code.exe", "release-cutover - ACME")
    d.web("02:35", "02:45", "ACME release runbook", "https://acme.example/runbook")
    d.web("02:05*", "02:15*", "ACME deploy log", "https://acme.example/deploys/8812")
    return d


SCENARIOS: tuple[Scenario, ...] = (
    Scenario(
        name="locked-screen-day",
        build=_locked_screen_day,
        cover="08:12-08:30,08:30-10:57,11:45-13:26,13:48-18:02",
        windows=("10:57-11:45", "11:45-13:26", "13:48-18:02", "18:02-18:53"),
        zoom="13:26-13:48",
    ),
    Scenario(
        name="blip-and-tail-day",
        build=_blip_and_tail_day,
        cover="08:00-12:15,13:10-17:20",
        windows=("08:00-12:15", "17:20-19:31"),
    ),
    Scenario(
        name="interleaved-clients-day",
        build=_interleaved_clients_day,
        cover="08:20-11:50,12:35-16:45",
        windows=("08:20-11:50", "12:35-16:45"),
        zoom="10:10-11:50",
    ),
    Scenario(
        name="no-break-day",
        build=_no_break_day,
        cover="08:15-17:30",
        windows=("08:15-17:30", "10:30-11:00", "13:00-13:35", "15:40-16:10"),
    ),
    Scenario(
        name="overnight-day",
        build=_overnight_day,
        cover="19:30-22:40,23:05-23:59",
        windows=("19:30-22:40",),
    ),
    Scenario(name="idle-day", build=_idle_day),
    Scenario(
        name="daylight-saving-day",
        build=_daylight_saving_day,
        cover="08:30-12:00,12:45-17:15",
        windows=("08:30-12:00",),
    ),
    Scenario(
        name="daylight-saving-transition-day",
        build=_daylight_saving_transition_day,
        cover="00:40-01:45,09:15-12:30,13:20-17:00",
        windows=("00:40-01:45", "09:15-12:30"),
        # The zoom is the timeline's own `parse_range` + web-watcher path, and it is aimed
        # at the pre-change session deliberately: that is the half a single offset put an
        # hour out, so it is the half worth rendering twice.
        zoom="00:40-01:45",
    ),
    Scenario(
        name="fall-back-repeated-hour-day",
        build=_fall_back_repeated_hour_day,
        # Written with the marker the scripts print, so a green run is evidence that a
        # block read out of one script's output resolves to the same hour when handed
        # back. Unmarked, `02:30*-04:15` would claim an hour of work that never happened.
        cover="01:30-02:30,02:30*-04:15",
        # The middle probe is the hour-long break. It used to be unwritable: both ends
        # resolved to one instant, so `parse_range` rejected it as reversed.
        windows=("01:30-02:30", "02:30-02:30*", "02:30*-04:15"),
        # Ends inside the repeated hour rather than past it, so the marker is load-bearing:
        # `03:00` is unambiguous and `03:00*` would be refused. Wide enough to hold both
        # web rows, which is what makes the golden pin their ordering.
        zoom="02:00-02:30*",
    ),
)

BY_NAME = {s.name: s for s in SCENARIOS}
