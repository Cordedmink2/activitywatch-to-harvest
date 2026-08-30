"""Create a Harvest time entry. Compact output for low token cost.

Usage:
  python harvest_post.py PROJECT_ID TASK_ID YYYY-MM-DD HH:MM HH:MM 'notes' [--confirm]

**`--confirm` is the confirmation gate.** Without it nothing is written: the
script prints the exact body it would have sent and exits 0, so a forgotten flag
yields a preview rather than an error. SKILL.md Step 8 is where the user's yes is
obtained; TESTING.md § "The confirmation gate" is why the gate is here as well as
there.

Times accept either 24h ("08:15") or 12h ("8:15am") — Harvest accepts both.
Always sends started_time + ended_time so accounts in start/end-time mode get
a fixed-duration entry (not a running timer). See SKILL.md Step 9 for context.

Use SINGLE quotes around notes in bash/PowerShell to avoid $variable
interpolation mangling money references like "$5k" or token-shaped substrings.

Success: prints `OK <entry_id>` and exits 0.
Preview: prints `WOULD POST <body>` and exits 0 — no entry exists.
Failure: prints `ERR <status> <body[:200]>` to stderr and exits 1.
"""
import json
import os
import sys

os.environ["PYTHONIOENCODING"] = "utf-8"
for _s in (sys.stdout, sys.stderr):   # a captured or redirected stream lacks reconfigure
    try:
        _s.reconfigure(encoding="utf-8")
    except Exception:
        pass

from harvest_client import parse_time_to_minutes, request

CONFIRM_FLAG = "--confirm"

USAGE = ("Usage: harvest_post.py PROJECT_ID TASK_ID YYYY-MM-DD HH:MM HH:MM 'notes' "
         f"[{CONFIRM_FLAG}]\n"
         f"Without {CONFIRM_FLAG} the entry is previewed, not created.")


def main() -> None:
    # The flag is removed wherever it appears, so it can be typed before or after the
    # positionals. Notes spelled exactly `--confirm` would be eaten too — and the argument
    # count then falls short, which is a usage error rather than a silent post.
    args = [a for a in sys.argv[1:] if a != CONFIRM_FLAG]
    confirmed = len(args) != len(sys.argv) - 1
    if len(args) != 6:
        sys.exit(USAGE)
    project_id, task_id, spent_date, started, ended, notes = args

    try:
        start_min = parse_time_to_minutes(started)
        end_min = parse_time_to_minutes(ended)
    except ValueError as e:
        print(f"ERR {e}", file=sys.stderr)
        sys.exit(1)
    if end_min <= start_min:
        print(
            f"ERR start ({started}) must be before end ({ended}). "
            "Harvest otherwise silently stores reversed times as 23h entries "
            "and zero-duration as 0h — the script blocks both.",
            file=sys.stderr,
        )
        sys.exit(1)

    try:
        project_id_n, task_id_n = int(project_id), int(task_id)
    except ValueError:
        print(
            f"ERR project_id and task_id must be numeric Harvest ids, got "
            f"{project_id!r} and {task_id!r}. A project *code* like 'ACM-CR202' is not "
            "an id — run harvest_lookup.py to resolve it.",
            file=sys.stderr,
        )
        sys.exit(1)

    body = {
        "project_id": project_id_n,
        "task_id": task_id_n,
        "spent_date": spent_date,
        "started_time": started,
        "ended_time": ended,
        "notes": notes,
    }
    if not confirmed:
        # The body itself, not a rendering of it: a preview that describes the entry in
        # its own words is a second description that can drift from the first, and the
        # user would then be approving the paraphrase rather than the entry.
        print(f"WOULD POST {json.dumps(body, ensure_ascii=False)}")
        print(f"Nothing was posted. Re-run with {CONFIRM_FLAG} to create this entry.")
        return
    try:
        resp = request("POST", "/time_entries", body=body)
    except RuntimeError as e:
        print(f"ERR {e}", file=sys.stderr)
        sys.exit(1)
    print(f"OK {resp['id']}")


if __name__ == "__main__":
    main()
