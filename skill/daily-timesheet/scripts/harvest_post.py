"""Create a Harvest time entry. Compact output for low token cost.

Usage:
  python harvest_post.py PROJECT_ID TASK_ID YYYY-MM-DD HH:MM HH:MM 'notes'

Times accept either 24h ("08:15") or 12h ("8:15am") — Harvest accepts both.
Always sends started_time + ended_time so accounts in start/end-time mode get
a fixed-duration entry (not a running timer). See SKILL.md Step 9 for context.

Use SINGLE quotes around notes in bash/PowerShell to avoid $variable
interpolation mangling money references like "$5k" or token-shaped substrings.

Success: prints `OK <entry_id>` and exits 0.
Failure: prints `ERR <status> <body[:200]>` to stderr and exits 1.
"""
import os
import sys

os.environ["PYTHONIOENCODING"] = "utf-8"
sys.stdout.reconfigure(encoding="utf-8")
sys.stderr.reconfigure(encoding="utf-8")

from harvest_client import parse_time_to_minutes, request


def main() -> None:
    if len(sys.argv) != 7:
        sys.exit(
            "Usage: harvest_post.py PROJECT_ID TASK_ID YYYY-MM-DD HH:MM HH:MM 'notes'"
        )
    project_id, task_id, spent_date, started, ended, notes = sys.argv[1:7]

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

    body = {
        "project_id": int(project_id),
        "task_id": int(task_id),
        "spent_date": spent_date,
        "started_time": started,
        "ended_time": ended,
        "notes": notes,
    }
    try:
        resp = request("POST", "/time_entries", body=body)
    except RuntimeError as e:
        print(f"ERR {e}", file=sys.stderr)
        sys.exit(1)
    print(f"OK {resp['id']}")


if __name__ == "__main__":
    main()
