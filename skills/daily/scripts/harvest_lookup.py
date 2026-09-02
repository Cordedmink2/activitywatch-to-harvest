"""Look up a Harvest project + its tasks by code, project-name or client-name
fragment, searching ALL paginated assignment catalog pages.

The skill's .mcp/ holds the user's /users/me/project_assignments split across
several files (harvest_assignments.json, _p2.json, ...). A naive "read the
latest file" lookup misses projects on other pages — this searches every page
and de-dupes projects that appear on more than one.

When the catalog has no match, the lookup falls back to the user's own recent
time entries via the live API. The assignments endpoint only returns *active*
assignments, so a project whose assignment was archived (common for short-lived
ticket-synced projects) disappears from the catalog even though it exists and
has entries against it — the user's entry history is the reliable place to
recover its project_id and task ids. Disable with --no-live (e.g. offline).

Usage:
  python scripts/harvest_lookup.py ACM-CR202
  python scripts/harvest_lookup.py "Field Services"
  python scripts/harvest_lookup.py Contoso           # matches on client name
  python scripts/harvest_lookup.py BET --task Development
  python scripts/harvest_lookup.py ACM-CR202 --mcp-dir /path/to/.mcp --json
"""
import argparse
import glob
import io
import json
import os
import sys

from skill_config import find_workspace, has_value

def find_catalog_dir(explicit: str | None) -> str:
    """Locate the `.mcp/` directory holding the catalogs.

    `--mcp-dir` first, then the workspace — the flag-beats-configuration order
    `skill_config` documents, down to its `has_value()` test, so a blank `--mcp-dir` is
    an omitted flag rather than a directory named "". Resolution delegates to
    `skill_config.find_workspace()`, the same resolver refresh_catalogs.py writes
    through, so the reader and the writer cannot disagree about where catalogs live.
    Falls back to the current directory when the workspace can't be resolved: a missing
    catalog is not fatal here, since main() reports the path it looked in and recovers
    via the live time-entries API.
    """
    if has_value(explicit):
        return explicit
    ws = find_workspace()
    if ws is None:
        return os.path.join(os.getcwd(), ".mcp")
    return str(ws / ".mcp")


def iter_assignments(mcp_dir):
    """Yield each project_assignment dict across all catalog pages, de-duped by project id."""
    files = sorted(glob.glob(os.path.join(mcp_dir, "harvest_assignments*.json")))
    seen = set()
    for f in files:
        try:
            with open(f, encoding="utf-8") as fh:
                d = json.load(fh)
        except Exception:
            continue
        rows = d if isinstance(d, list) else d.get("project_assignments", d.get("assignments", []))
        for pa in rows:
            pid = (pa.get("project") or {}).get("id")
            if pid in seen:
                continue
            seen.add(pid)
            yield pa


def match_kind(q, code, name, client):
    """How a project matched the query, or None. Client name counts: a project is often
    named for the work it covers, carrying the client's name only on `client.name`, so a
    code/name-only search misses it entirely — and can leave a stale shell project named
    after the client as the sole hit."""
    if code.lower() == q:
        return "code"
    if q in code.lower() or q in name.lower():
        return "code/name"
    if q in (client or "").lower():
        return "client"
    return None


def lookup(query, mcp_dir, task_filter=None):
    q = query.lower()
    matches = []
    for pa in iter_assignments(mcp_dir):
        p = pa.get("project") or {}
        code = p.get("code") or ""
        name = p.get("name") or ""
        client = (pa.get("client") or {}).get("name") or ""
        kind = match_kind(q, code, name, client)
        if kind is None:
            continue
        tasks = []
        for ta in pa.get("task_assignments", []):
            t = ta.get("task") or {}
            tname = t.get("name") or ""
            if task_filter and task_filter.lower() not in tname.lower():
                continue
            tasks.append({"id": t.get("id"), "name": tname, "billable": bool(ta.get("billable"))})
        matches.append({"code": code, "project_id": p.get("id"), "name": name,
                        "client": client, "matched_on": kind, "tasks": tasks})
    # exact code first, then code/name matches, then client-name-only matches
    rank = {"code": 0, "code/name": 1, "client": 2}
    matches.sort(key=lambda m: (rank[m["matched_on"]], m["code"]))
    return matches


def lookup_from_entries(query, days=180, task_filter=None):
    """Search the user's own recent time entries for a project the catalog misses.

    Returns matches in the same shape as lookup(), with source='time_entries' and
    each task carrying the billable flag observed on the most recent entry using it.
    Only this path needs credentials — harvest_client reads `.env` on first request(),
    so cache-only lookups still work without one.
    """
    import datetime

    from harvest_client import request

    q = query.lower()
    frm = (datetime.date.today() - datetime.timedelta(days=days)).isoformat()
    # Scope to the caller, the way harvest_list.py does. Unscoped, an admin-scope PAT
    # paginates the whole company's entries and can surface a project/task pair the user
    # has no assignment to — which then fails, or mis-bills, at post time.
    user_id = request("GET", "/users/me")["id"]
    projects = {}  # project_id -> {code, name, tasks: {task_id: {...}}}
    page = 1
    while True:
        payload = request("GET", "/time_entries",
                          query={"user_id": user_id, "from": frm, "per_page": 100, "page": page})
        for e in payload.get("time_entries", []):
            p = e.get("project") or {}
            code = p.get("code") or ""
            name = p.get("name") or ""
            client = (e.get("client") or {}).get("name") or ""
            kind = match_kind(q, code, name, client)
            if kind is None:
                continue
            t = e.get("task") or {}
            tname = t.get("name") or ""
            if task_filter and task_filter.lower() not in tname.lower():
                continue
            proj = projects.setdefault(p.get("id"), {"code": code, "project_id": p.get("id"), "name": name,
                                                     "client": client, "matched_on": kind, "tasks": {}})
            # Entries arrive newest-first; keep the first (most recent) billable flag per task.
            proj["tasks"].setdefault(t.get("id"), {"id": t.get("id"), "name": tname, "billable": bool(e.get("billable"))})
        if not payload.get("next_page"):
            break
        page += 1
    matches = [{**m, "tasks": list(m["tasks"].values()), "source": "time_entries"} for m in projects.values()]
    rank = {"code": 0, "code/name": 1, "client": 2}
    matches.sort(key=lambda m: (rank[m["matched_on"]], m["code"]))
    return matches


def main():
    # Not `harvest_client.use_utf8()`: that also sets PYTHONIOENCODING for child
    # processes, and this script spawns none — reaching for it would pull the Harvest
    # client, its base URL and its credential machinery into a script that never bills.
    # In `main()` rather than at module scope because an import must have no side effect
    # (issue #21); a captured or redirected stream is not a TextIOWrapper and is skipped.
    for stream in (sys.stdout, sys.stderr):
        if isinstance(stream, io.TextIOWrapper):
            stream.reconfigure(encoding="utf-8")
    ap = argparse.ArgumentParser(description="Look up a Harvest project + tasks by code/name.")
    ap.add_argument("query", help="project code (exact) or code/name fragment")
    ap.add_argument("--task", help="filter task rows by name substring (case-insensitive)")
    ap.add_argument("--mcp-dir", help="directory holding harvest_assignments*.json")
    ap.add_argument("--json", action="store_true", help="emit JSON instead of the human-readable listing")
    ap.add_argument("--no-live", action="store_true", help="cache only; skip the time-entries API fallback")
    ap.add_argument("--days", type=int, default=180, help="how far back the time-entries fallback looks")
    args = ap.parse_args()

    mcp_dir = find_catalog_dir(args.mcp_dir)
    matches = lookup(args.query, mcp_dir, args.task)
    fell_back = False
    if not matches and not args.no_live:
        try:
            matches = lookup_from_entries(args.query, args.days, args.task)
            fell_back = True
        except Exception as e:
            print(f"WARN time-entries fallback failed: {e}", file=sys.stderr)
    if not matches:
        print(f"ERR no project matching '{args.query}' in {mcp_dir} or recent time entries", file=sys.stderr)
        return 1
    if fell_back:
        print(
            "NOTE not in assignments catalog (assignment likely archived); "
            f"recovered from own time entries, last {args.days} days",
            file=sys.stderr,
        )
    if args.json:
        print(json.dumps(matches, indent=2))
        return 0
    for m in matches:
        client = f"  [{m['client']}]" if m.get("client") else ""
        print(f"{m['code']}  {m['project_id']}  {m['name']}{client}")
        for t in m["tasks"]:
            b = "billable" if t["billable"] else "NON-billable"
            print(f"    {t['id']}  {t['name']}  ({b})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
