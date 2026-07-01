"""Look up a Harvest project + its tasks by code or name fragment, searching
ALL paginated assignment catalog pages.

The skill's .mcp/ holds the user's /users/me/project_assignments split across
several files (harvest_assignments.json, _p2.json, ...). A naive "read the
latest file" lookup misses projects on other pages — this searches every page
and de-dupes projects that appear on more than one.

Usage:
  python scripts/harvest_lookup.py NLS-CR202
  python scripts/harvest_lookup.py "Short Courses"
  python scripts/harvest_lookup.py CON --task Development
  python scripts/harvest_lookup.py NLS-CR202 --mcp-dir /path/to/.mcp --json
"""
import argparse
import glob
import json
import os
import sys

for _s in (sys.stdout, sys.stderr):   # pytest's captured stdout lacks reconfigure
    try:
        _s.reconfigure(encoding="utf-8")
    except Exception:
        pass


def find_catalog_dir(explicit):
    if explicit:
        return explicit
    for cand in [os.path.join(os.getcwd(), ".mcp"),
                 os.path.join(os.path.expanduser("~"), "Claude", "Work", ".mcp")]:
        if os.path.isdir(cand):
            return cand
    return os.path.join(os.getcwd(), ".mcp")


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


def lookup(query, mcp_dir, task_filter=None):
    q = query.lower()
    matches = []
    for pa in iter_assignments(mcp_dir):
        p = pa.get("project") or {}
        code = p.get("code") or ""
        name = p.get("name") or ""
        if not (code.lower() == q or q in code.lower() or q in name.lower()):
            continue
        tasks = []
        for ta in pa.get("task_assignments", []):
            t = ta.get("task") or {}
            tname = t.get("name") or ""
            if task_filter and task_filter.lower() not in tname.lower():
                continue
            tasks.append({"id": t.get("id"), "name": tname, "billable": bool(ta.get("billable"))})
        matches.append({"code": code, "project_id": p.get("id"), "name": name, "tasks": tasks})
    matches.sort(key=lambda m: (m["code"].lower() != q, m["code"]))  # exact code first
    return matches


def main():
    ap = argparse.ArgumentParser(description="Look up a Harvest project + tasks by code/name.")
    ap.add_argument("query", help="project code (exact) or code/name fragment")
    ap.add_argument("--task", help="filter task rows by name substring (case-insensitive)")
    ap.add_argument("--mcp-dir", help="directory holding harvest_assignments*.json")
    ap.add_argument("--json", action="store_true", help="emit JSON instead of machine-readable output")
    args = ap.parse_args()

    mcp_dir = find_catalog_dir(args.mcp_dir)
    matches = lookup(args.query, mcp_dir, args.task)
    if not matches:
        print(f"ERR no project matching '{args.query}' in {mcp_dir}", file=sys.stderr)
        return 1
    if args.json:
        print(json.dumps(matches, indent=2))
        return 0
    for m in matches:
        print(f"{m['code']}  {m['project_id']}  {m['name']}")
        for t in m["tasks"]:
            b = "billable" if t["billable"] else "NON-billable"
            print(f"    {t['id']}  {t['name']}  ({b})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
