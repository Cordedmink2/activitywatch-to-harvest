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
than billing it short. See `harvest_write.refusal_for_a_straddled_change()`,
which `harvest_patch.py` refuses with too.

Use SINGLE quotes around notes in bash/PowerShell to avoid $variable
interpolation mangling money references like "$5k" or token-shaped substrings.

Success: prints `OK <entry_id>` and exits 0.
Preview: prints `WOULD POST <body>` and exits 0 — no entry exists.
Failure: prints `ERR <status> <body[:200]>` to stderr and exits 1.
"""
import datetime as dt
import sys

import harvest_write
import timezone
from harvest_client import use_utf8

USAGE = ("Usage: harvest_post.py PROJECT_ID TASK_ID YYYY-MM-DD HH:MM HH:MM 'notes' "
         f"[{harvest_write.CONFIRM_FLAG}]\n"
         f"Without {harvest_write.CONFIRM_FLAG} the entry is previewed, not created.")


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
    refusal = harvest_write.refusal_for_a_straddled_change(
        spent, start_min, end_min,
        timezone.resolve_zone(None, offers_offset_flag=False))
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
