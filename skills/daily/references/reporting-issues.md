# Reporting a defect in this skill

Step 11 sends you here when a run found something wrong with the **skill itself** — a
script returning a wrong answer, a guard that didn't fire, an instruction wrong for
everyone — rather than a fact about this user or a setting on their machine. Skip this
file on a normal run.

**If the user maintains this skill, this is the wrong file.** `references/self-development.md`
owns editing it, and shipping the change is a commit to the repo below — there is no separate
release ritual. Ask if you don't know; the answer is stable, so it is worth recording under
`## Preferences` in `.context.md` once rather than re-asking every run.

## The repository

    https://github.com/Cordedmink2/activity-to-timesheet

Nothing an agent reads on a run names the origin — `SKILL.md` does not, and there is no
version marker beside it — so read it from here rather than asking the user, who may well
not remember either. The version the issue form asks for is the plugin's: `/plugin` lists
it in Claude Code, and the export prints it as `Exporting billables v...`.

## Redact before drafting, not after

A GitHub issue is public and permanent. It is more exposed than a Harvest note, which at
least only reaches the client it belongs to.

This skill reads window titles, screenshots and Harvest entries, so **everything it can
quote is client-identifying**: client and project names, project codes, ticket numbers,
colleague names, SharePoint and CRM URLs, environment names, local paths. Replace each one
with a stable placeholder as you draft — `Client A`, `ACME-001`, `<ticket>`, `<env>` — and
keep the shape, because a rollup with realistic minutes and category counts is what makes a
report reproducible. Timestamps, durations, ratios, hours and script flags are all safe and
are usually the whole evidence.

Never paste `.env`, a Harvest token, or any part of `.context.md`.

## Filing

**You may file it — after showing the user and getting an explicit yes.** Not filing at all
is the wrong default: a defect that stays on one machine gets rediscovered by the next
person. Show the full title and body, then:

```
gh issue create -R Cordedmink2/activity-to-timesheet \
  --title "<what goes wrong, not what to change>" \
  --body-file <path>
```

Write the body to a file; inlining it through `--body` mangles newlines and backticks.

The yes has to be for *filing*. The user agreeing the defect is real is not it, and neither
is Step 11 completing. If `gh` is missing or unauthenticated, or GitHub is unreachable,
don't improvise another route — save the draft as `Timesheets/<date>_skill-issue.md`, say
where it is and what to run, and move on.

## Not every defect is one

Three shapes look like skill defects at the end of a run and aren't. Sort them back before
drafting:

- **"It didn't know this client / signal / convention"** — a `.context.md` fact.
- **"A title came back `uncategorized`"** — an ActivityWatch category rule on this machine;
  `references/setup.md` § categories.
- **"`harvest_lookup.py` can't find the project"** — usually a project that doesn't exist
  yet; `references/new-client-work.md`. A miss *after* the live-entry fallback is not a
  lookup bug.
