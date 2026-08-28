"""Update an existing Harvest time entry. PATCH semantics — only passed fields change.

WARNING: --hours is a footgun on start/end-time accounts.
If the account stores entries as started_time + ended_time (most accounts,
including the typical consultancy setup), patching with just --hours leaves the
entry inconsistent or converts it to a running timer. Always prefer
--start HH:MM --end HH:MM to change duration. --hours is retained for
duration-mode accounts only.

Same shape of trap with --start or --end on their own: if you pass --start
without --end (or vice versa), Harvest recomputes hours from the unchanged
side, which is rarely what you meant. To shift a block, pass BOTH --start
and --end. Only pass one alone if you genuinely want Harvest to grow/shrink
the entry by holding the other side fixed.

Usage:
  python harvest_patch.py ENTRY_ID [--start HH:MM] [--end HH:MM]
                                   [--notes '...'] [--hours N]
                                   [--project-id N] [--task-id N]
                                   [--date YYYY-MM-DD]

At least one flag must be provided.
Use SINGLE quotes around --notes values to avoid shell $variable interpolation
mangling money references and other dollar-prefixed substrings.

Success: prints `OK <entry_id>` and exits 0.
Failure: prints `ERR <status> <body[:200]>` to stderr and exits 1.
"""
import os
import sys

os.environ["PYTHONIOENCODING"] = "utf-8"
for _s in (sys.stdout, sys.stderr):   # a captured or redirected stream lacks reconfigure
    try:
        _s.reconfigure(encoding="utf-8")
    except Exception:
        pass

from harvest_client import parse_time_to_minutes, request

FLAGS = {
    "--start": ("started_time", str),
    "--end": ("ended_time", str),
    "--notes": ("notes", str),
    "--hours": ("hours", float),  # footgun on start/end-time accounts — see module docstring
    "--project-id": ("project_id", int),
    "--task-id": ("task_id", int),
    "--date": ("spent_date", str),
}

USAGE = (
    "Usage: harvest_patch.py ENTRY_ID "
    "[--start HH:MM] [--end HH:MM] [--notes '...'] "
    "[--hours N] [--project-id N] [--task-id N] [--date YYYY-MM-DD]"
)


def parse_args(argv: list[str]) -> tuple[str, dict]:
    if len(argv) < 2:
        sys.exit(USAGE)
    entry_id = argv[1]
    body: dict = {}
    i = 2
    while i < len(argv):
        flag = argv[i]
        if flag not in FLAGS:
            sys.exit(f"Unknown flag: {flag}\n{USAGE}")
        if i + 1 >= len(argv):
            sys.exit(f"Missing value for {flag}")
        key, caster = FLAGS[flag]
        if key in body:
            # Last-wins would send the second value and exit 0, so the caller believes
            # both landed. A repeated flag is never deliberate — it is a command
            # assembled twice — and every other guard here blocks before the request.
            sys.exit(f"{flag} given more than once; pass it once with the final value")
        raw = argv[i + 1]
        try:
            body[key] = caster(raw)
        except ValueError:
            print(f"ERR {flag} expects a {caster.__name__}, got {raw!r}", file=sys.stderr)
            sys.exit(1)
        i += 2
    if not body:
        sys.exit("Provide at least one field to update.")
    return entry_id, body


def main() -> None:
    entry_id, body = parse_args(sys.argv)

    if "started_time" in body and "ended_time" in body:
        try:
            start_min = parse_time_to_minutes(body["started_time"])
            end_min = parse_time_to_minutes(body["ended_time"])
        except ValueError as e:
            print(f"ERR {e}", file=sys.stderr)
            sys.exit(1)
        if end_min <= start_min:
            print(
                f"ERR --start ({body['started_time']}) must be before "
                f"--end ({body['ended_time']}).",
                file=sys.stderr,
            )
            sys.exit(1)

    try:
        resp = request("PATCH", f"/time_entries/{entry_id}", body=body)
    except RuntimeError as e:
        print(f"ERR {e}", file=sys.stderr)
        sys.exit(1)
    print(f"OK {resp['id']}")


if __name__ == "__main__":
    main()
