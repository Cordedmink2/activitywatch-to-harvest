"""Create a Harvest time entry. Compact output for low token cost.

Usage:
  python harvest_post.py PROJECT_ID TASK_ID YYYY-MM-DD HH:MM HH:MM 'notes' [--confirm]

**`--confirm` is the confirmation gate.** Without it nothing is written: the
script prints the exact body it would have sent and exits 0, so a forgotten flag
yields a preview rather than an error. The gate, the preview and the `OK` / `ERR`
contract are `harvest_write.py`'s, shared with `harvest_patch.py`; this script
declares the body and the guards in front of it. SKILL.md Step 8 is where the
user's yes is obtained; TESTING.md § "The confirmation gate" is why the gate is
in the invocation as well as there.

Times accept either 24h ("08:15") or 12h ("8:15am") — Harvest accepts both.
Always sends started_time + ended_time so accounts in start/end-time mode get
a fixed-duration entry (not a running timer). See SKILL.md Step 9 for context.

Harvest derives the duration from those two clock times, which is wrong by an
hour for an entry worked straight through the autumn change — so this needs
`TIMESHEET_TIMEZONE` to know when that is, and refuses such an entry rather
than billing it short. See `refusal_for_a_straddled_change()` below.

Use SINGLE quotes around notes in bash/PowerShell to avoid $variable
interpolation mangling money references like "$5k" or token-shaped substrings.

Success: prints `OK <entry_id>` and exits 0.
Preview: prints `WOULD POST <body>` and exits 0 — no entry exists.
Failure: prints `ERR <status> <body[:200]>` to stderr and exits 1.
"""
import datetime as dt
import sys

import aw_client
import harvest_write
from harvest_client import use_utf8

USAGE = ("Usage: harvest_post.py PROJECT_ID TASK_ID YYYY-MM-DD HH:MM HH:MM 'notes' "
         f"[{harvest_write.CONFIRM_FLAG}]\n"
         f"Without {harvest_write.CONFIRM_FLAG} the entry is previewed, not created.")


def clock(minutes: int) -> str:
    """Minutes-since-midnight as the plain `HH:MM` this script's own arguments are in.

    Deliberately not an echo of what the user typed: `8:15am` and `08:15` are the same
    entry, and a refusal below has to name times the user did *not* type, so all four
    times in that message are written one way or they cannot be compared by eye.
    """
    return f"{minutes // 60:02d}:{minutes % 60:02d}"


def _minutes(t: dt.time) -> int:
    """A clock reading as minutes since midnight, the unit every time here is compared in."""
    return t.hour * 60 + t.minute


def hours(minutes: int) -> str:
    """Minutes as the decimal hours Harvest bills them in — 165 -> `2.75`.

    Two decimals, then trailing zeros trimmed to one: `3.0` rather than `3`, which is the
    shape `references/output-format.md` writes hours in and the shape Harvest shows them
    back in. A stretch that is not a whole number of minutes' worth of quarter-hours reads
    rounded, e.g. 100 minutes as `1.67` — the times above it are exact, and they are what
    the entry is actually posted from.
    """
    text = f"{minutes / 60:.2f}".rstrip("0")
    return text + "0" if text.endswith(".") else text


def repeated_span(spent, zone) -> tuple[int, int] | None:
    """The minutes-since-midnight bounds of the span the clocks repeat on `spent`, or None.

    Measured, never assumed: `Australia/Lord_Howe` moves thirty minutes and
    `Antarctica/Troll` two hours, and both figures come off the zone's own two readings.

    None means there is nothing on this date an entry could straddle, which is three
    different facts and not one:

    - no transition at all, which is every date but two a year;
    - a spring-forward. The clock skips rather than repeating, so an entry across it is
      over-billed rather than short, and its two pieces would be separated by a gap where
      these two abut — a different message, and #23 put it out of scope. The `TESTING.md`
      Open gaps entry for the skipped hour carries it. `repeats` comes from the sign of
      the offset shift and not from the order of the two readings, which gets
      `America/Santiago` exactly backwards;
    - a repeated span that crosses midnight, as it does in `America/Santiago`, where the
      clocks go back at 00:00 to 23:00. Containment would then need an end past 1440, and
      `parse_time_to_minutes` caps a reading at 23:59 — so no entry these scripts can even
      express contains that span, and there is nothing to catch.

    Separate from the refusal below because `harvest_patch.py` asks the cheap half of the
    question first: on a date with no repeated span it can skip reading the entry it is
    about to patch, which is a request over the wire.
    """
    change = aw_client.transition_clocks(spent, zone)
    if change is None or not change.repeats:
        return None
    repeat_open, repeat_close = _minutes(change.once_passed), _minutes(change.as_reached)
    if repeat_open >= repeat_close:
        return None
    return repeat_open, repeat_close


def refusal_for_a_straddled_change(spent, start_min, end_min, zone) -> str | None:
    """Why this entry cannot be posted as one, or None if it can.

    Harvest stores two clock times and bills their difference. On the day the clocks go
    back, an entry worked straight through the change is short by exactly the span that
    happened twice: `01:30`-`04:15` in `Pacific/Auckland` on 2026-04-05 bills 2.75 hrs for
    3.75 hrs of work. Nothing raises — the entry is well-formed, and it reads correctly in
    every listing afterwards, so there is no later moment at which anyone finds out.

    That span is an hour in most zones and is never assumed to be: `Australia/Lord_Howe`
    moves thirty minutes and `Antarctica/Troll` two hours, and every figure in the message
    below is measured off the zone's own two readings.

    **It refuses only the entry that is unambiguously wrong**, which is the one whose clock
    interval contains the repeated span with both ends strictly outside it. The tempting
    rule — "the clock interval and the elapsed time disagree" — refuses the two
    replacements this message recommends, because `01:30`-`03:00` also spans 1.5 clock
    hours and 2.5 real ones if its end is read as the unambiguous `03:00` an hour after the
    change. That reading is why the ends have to be strict: an entry *ending* at
    `03:00` or *starting* at `02:00` is one of the two recommendations under one reading
    and an hour short under the other, and this cannot refuse its own advice. Inside the
    span the script likewise cannot know which pass a bare `02:30` means, and both readings
    bill correctly for their own pass. `references/output-format.md` keeps the hand-split
    guidance for everything left over.

    It refuses rather than splitting. Two entries out of one approval would put a body on
    the wire the user never previewed, which is the property the confirmation gate exists
    to hold.
    """
    span = repeated_span(spent, zone)
    if span is None:
        return None
    repeat_open, repeat_close = span
    if not (start_min < repeat_open and end_min > repeat_close):
        return None

    first, second = repeat_close - start_min, end_min - repeat_open
    repeated = repeat_close - repeat_open
    return (
        f"ERR {clock(start_min)}-{clock(end_min)} on {spent} runs straight through the "
        f"daylight-saving change in {aw_client.zone_label(zone)}.\n"
        f"  Harvest bills the difference between the two clock times, so this entry would "
        f"record {hours(end_min - start_min)} hrs against the {hours(first + second)} hrs "
        f"that really passed. Post two entries instead:\n"
        f"      {clock(start_min)} {clock(repeat_close)}   ({hours(first)} hrs)\n"
        f"      {clock(repeat_open)} {clock(end_min)}   ({hours(second)} hrs)\n"
        f"  Those two look like they overlap by {hours(repeated)} hrs and do not — they "
        f"abut. The clocks go back at one instant, and that instant reads "
        f"{clock(repeat_close)} as you reach it and {clock(repeat_open)} once it has "
        f"passed, so the first entry ends and the second begins at the same moment. "
        f"Closing the apparent overlap is what loses the {hours(repeated)} hrs that "
        f"happened twice, which is why this is refused rather than split for you. Say in "
        f"the day's notes that the clocks changed — the overlap is the first thing a "
        f"reviewer will query.")


def main() -> None:
    use_utf8()
    # `take_gate` says why it runs before anything is read positionally. What is left has
    # to be exactly the six positionals.
    args, confirmed = harvest_write.take_gate(sys.argv[1:])
    if len(args) != 6:
        sys.exit(USAGE)
    project_id, task_id, spent_date, started, ended, notes = args

    # Every guard runs before the gate is consulted, so an unconfirmed bad command fails
    # here and is never previewed.
    start_min, end_min = harvest_write.ordered_minutes(started, ended)

    try:
        project_id_n, task_id_n = int(project_id), int(task_id)
    except ValueError:
        harvest_write.err(
            f"project_id and task_id must be numeric Harvest ids, got "
            f"{project_id!r} and {task_id!r}. A project *code* like 'ACM-CR202' is not "
            "an id — run harvest_lookup.py to resolve it.")

    try:
        spent = dt.date.fromisoformat(spent_date)
    except ValueError:
        # Read rather than passed through because the guard below needs the date to know
        # whether the clocks changed on it. Harvest answers a malformed one with a 422 and
        # its own wording; saying so here costs a round trip less and names the format.
        harvest_write.err(f"spent_date must be YYYY-MM-DD, got {spent_date!r}.")

    # Last of the checks, and the only one that reads configuration: a plain typo in the
    # arguments should be answered as a typo, not as a missing setting. The zone is asked
    # for without an offset flag: this script has none to offer — see `resolve_zone`.
    refusal = refusal_for_a_straddled_change(
        spent, start_min, end_min,
        aw_client.resolve_zone(None, offers_offset_flag=False))
    if refusal:
        # Before the preview as well as before the post. The preview is what the user says
        # yes to, so an entry that must not be created must not be offered either.
        print(refusal, file=sys.stderr)
        sys.exit(1)

    body = {
        "project_id": project_id_n,
        "task_id": task_id_n,
        # The parsed date, not the string it came from. `date.fromisoformat` widened on
        # 3.11 to take `20260812` and `2026-W33-1`, so on a new enough interpreter the
        # check above admits spellings its own message says are not allowed — and the raw
        # one would then go on the wire, differently from how 3.10 (the declared minimum)
        # answers the same input. Sending what was parsed makes the wire body the same.
        "spent_date": spent.isoformat(),
        "started_time": started,
        "ended_time": ended,
        "notes": notes,
    }
    harvest_write.perform(harvest_write.create(body), confirmed)


if __name__ == "__main__":
    main()
