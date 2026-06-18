# Catalog refresh

The skill relies on cached catalogs in `Work/.mcp/`. They're cached because the underlying APIs are slow (Harvest pagination, ticket-store queries) and the data changes slowly. Refresh when stale.

## When to refresh

- Cached file is missing → refresh
- `.mtime` is older than 7 days → refresh
- The user mentions a project / ticket the catalog doesn't have → refresh
- A classification fails to find a matching `project.code` even though the ticket pattern looks valid → refresh

## Harvest project assignments

**Endpoint:** `GET https://api.harvestapp.com/api/v2/users/me/project_assignments?per_page=100&page=<N>`

**Why this endpoint specifically:** many users' Harvest PATs are *member-scope* (`expenses:read:own`, `timers:read:own/write:own`). Admin endpoints like `/projects` and `/clients` return 403 for member-scope tokens. The `/users/me/project_assignments` endpoint is self-scoped and returns the same shape — project + client + task_assignments — for projects the authenticated user is personally assigned to. Works on both member and admin tokens.

**Auth headers:**
```
Harvest-Account-ID: <user's account id>
Authorization: Bearer <HARVEST_API_KEY>
User-Agent: <something descriptive>
```

The token comes from the skill's `.env` file (see `SKILL.md` → Setup → "First-run: Harvest credentials"). `scripts/refresh_catalogs.py` resolves it through the same shared `harvest_client.load_creds()` helper the other Harvest scripts use, so configuring `.env` once covers everything.

**Pagination:** loop pages at `per_page=100` until `next_page` is null. Most consultants have <1000 assignments total.

**Output:** save raw page JSON to `.mcp/harvest_assignments_p<N>.json` (and `harvest_assignments.json` for page 1). Don't reformat — downstream readers expect Harvest's shape.

**Read-replica lag (important).** This endpoint is eventually consistent: identical back-to-back requests can hit a fresh replica or a lagging one, and the lagging one can even report the new `total_entries` while still serving stale rows. So a single refresh — and the row count — are NOT reliable for a *just-created* project. No client-side trick fixes a bulk pull. To bill against a brand-new project, call `refresh_catalogs.wait_for_project(code)`, which polls across minutes (each read re-rolls the replica) and returns the assignment dict once the code surfaces. Don't treat a one-off miss as failure.

## User-specific ticket catalogs (optional)

If the user maintains a ticket dump (e.g. an active-incidents list from a CRM, a Jira/Linear export), `scripts/refresh_catalogs.py` can refresh it. The exact query is user-specific — see `.context.md` for the user's ticket-source configuration.

The script's design assumes:
- Output goes to `.mcp/<catalog>.txt` or `.mcp/<catalog>.json`
- Format is tabular text or JSON — readable line-by-line by downstream classifiers
- Auth uses whatever CLI the user has configured for their backend (e.g. `pac` CLI for Dataverse, `gh` for GitHub Issues)

## Creating a backend ticket/case to bill against (optional, org-specific)

Sometimes a block belongs to new work with no Harvest project yet. If your organisation
creates a ticket/case in a backend CRM that then syncs to Harvest as a new project
(`project.code` == the ticket id), the general flow is:

1. Create the ticket/case in your CRM (whatever tooling you use). The CRM typically assigns
   the ticket number; in many setups the **customer account determines the ticket prefix**, so
   you supply the client + title and the system assigns the number. It's usually a client-facing
   CRM, so confirm the resolved client + title with the user before creating anything.
2. The new project lags in Harvest (see read-replica lag above) — use
   `refresh_catalogs.wait_for_project(code)` to get its `project_id`/`task_id` before posting.

> **Note:** the actual ticket-creation/lookup helpers are org-specific and are **not bundled**
> with this skill (they depend on your CRM, its auth, and your schema). If you work in Dataverse
> the bundled `refresh_catalogs.py --dataverse-only` can still build the read-only
> `.mcp/dv_active_incidents.txt` catalog via `pac env fetch` once you set `DATAVERSE_URL` and
> `PAC_PROFILE` in `.env`. Writing new cases is left to your own helper.

## Sanity checks after refresh

- Harvest file has >10 entries → looks reasonable for most consultants
- Ticket-catalog file has the expected row count and column headers → looks reasonable
- If either looks empty / wrong, restore the previous file from backup before overwriting

`scripts/refresh_catalogs.py` does all the above in one go.
