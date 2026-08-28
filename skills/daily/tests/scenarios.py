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


@dataclass
class Scenario:
    """One day plus the probes the skill would run against it."""
    name: str
    doc: str
    build: Callable[[], Day]
    cover: str | None = None            # --cover argument for afk_blocks
    windows: tuple[str, ...] = ()       # --window probes for afk_blocks
    zoom: str | None = None             # --window zoom for activity_timeline
    extra_args: tuple[str, ...] = field(default_factory=tuple)


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
    """The same clock times during NZ daylight saving, read at UTC+13.

    Every span is written in local time, so a correct offset reproduces the local
    rendering exactly; an offset bug shifts the whole day by an hour.
    """
    d = day(dt.date(2026, 1, 20), offset=13.0)
    d.classify(*ACME)
    d.afk("00:00", "08:30")
    d.active("08:30", "12:00")
    d.afk("12:00", "12:45")
    d.active("12:45", "17:15")
    d.afk("17:15", "24:00")
    d.window("08:30", "17:15", "Code.exe", "CasePlugins - ACME")
    return d


SCENARIOS: tuple[Scenario, ...] = (
    Scenario(
        name="locked-screen-day",
        doc=_locked_screen_day.__doc__,
        build=_locked_screen_day,
        cover="08:12-08:30,08:30-10:57,11:45-13:26,13:48-18:02",
        windows=("10:57-11:45", "11:45-13:26", "13:48-18:02", "18:02-18:53"),
        zoom="13:26-13:48",
    ),
    Scenario(
        name="blip-and-tail-day",
        doc=_blip_and_tail_day.__doc__,
        build=_blip_and_tail_day,
        cover="08:00-12:15,13:10-17:20",
        windows=("08:00-12:15", "17:20-19:31"),
    ),
    Scenario(
        name="interleaved-clients-day",
        doc=_interleaved_clients_day.__doc__,
        build=_interleaved_clients_day,
        cover="08:20-11:50,12:35-16:45",
        windows=("08:20-11:50", "12:35-16:45"),
        zoom="10:10-11:50",
    ),
    Scenario(
        name="no-break-day",
        doc=_no_break_day.__doc__,
        build=_no_break_day,
        cover="08:15-17:30",
        windows=("08:15-17:30", "10:30-11:00", "13:00-13:35", "15:40-16:10"),
    ),
    Scenario(
        name="overnight-day",
        doc=_overnight_day.__doc__,
        build=_overnight_day,
        cover="19:30-22:40,23:05-23:59",
        windows=("19:30-22:40",),
    ),
    Scenario(name="idle-day", doc=_idle_day.__doc__, build=_idle_day),
    Scenario(
        name="daylight-saving-day",
        doc=_daylight_saving_day.__doc__,
        build=_daylight_saving_day,
        cover="08:30-12:00,12:45-17:15",
        windows=("08:30-12:00",),
    ),
)

BY_NAME = {s.name: s for s in SCENARIOS}
