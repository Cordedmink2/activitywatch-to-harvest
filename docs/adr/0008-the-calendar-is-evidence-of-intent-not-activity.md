# ADR-0008: The calendar is evidence of intent, not activity

**Status:** Accepted — 2026-09-03.
**Context:** the `daily` skill's reading of a day. Related: [`CONTEXT.md`](../../CONTEXT.md) § "The
services" (**calendar**, **calendar event**), the spec in issue #49, ADR-0007 — two boundaries, the provider written and the
sources read — which is not written yet (#44) and so is named here rather than linked.

## Context

A user sits in a Teams meeting for forty-five minutes, camera off, listening. They touch nothing for
twenty of those minutes. The activity source's AFK watcher marks them away at the threshold, the day
skeleton records a break, and the skill drafts nothing for the stretch — the skeleton is arithmetic
and is taken verbatim. The user's calendar is the one thing that knew where they were.

That is the request this ADR answers (raised 2026-09-03), and the tempting fix is the wrong one: let
the calendar tell the skeleton the user was not idle. It reads well and it breaks the one rule the
skill's accuracy rests on, that **AFK status is settled by the AFK watcher and nothing re-infers it**.
A calendar does not know whether the meeting was attended, skipped, or taken from a phone in the car.
It knows what was scheduled.

## Decision

**The calendar is a fourth source, and it is not an activity source.** The activity source records
what the machine saw; the calendar records what the user was meant to be doing. The glossary keeps
the two apart because the rules below depend on the difference.

**The skeleton does not change.** Breaks, `work_start`, `work_end` and `active_ratio` are computed
from the AFK watcher exactly as before. No calendar event ever turns a break into active time.

**A calendar event is a block candidate, ranked by corroboration.**

- **Corroborated** — a meeting window from the activity source falls inside the event's span. The
  event is drafted as a block covering the event, extended to the end of any meeting-window evidence
  that runs past it. This is the second sanctioned exception to "outer block edges are the script's
  spans, transcribed verbatim", beside shrunk thin blocks, and the break it covers is declared under
  the table. Confidence `HIGH`.
- **Uncorroborated** — no meeting window inside the span, whether the event sits inside the skeleton
  or outside it (a client site before the laptop opened). The event is **never drafted as a block**.
  It is listed under the table as a question, and it becomes a block only when the user says so at
  the preview. Silence leaves it unbilled.

**As an attribution signal, a calendar event's subject and attendees rank with the meeting-window
title**: below a work item, able to settle a client when nothing higher does, never able to override
a work item that names a different one.

**Opt-in, one calendar, a narrow adapter.** Absent configuration means today's behaviour exactly. The
first adapter reads classic Outlook's default calendar through its COM object model from a PowerShell
script emitting JSON; a standard-library Python wrapper owns the configuration and the output shape,
so a second adapter is another producer of the same JSON and the rules never learn which one ran. The
read is basic fields by default — subject, start, end, show-as, response status, attendees — with a
drill-down for one event's body and location, used the way the timeline zoom is used. Nothing is
cached to the workspace.

## Consequences

- Fergus's case is answered without touching the skeleton: the listening-only meeting has a Teams
  window somewhere inside it, so it is corroborated and drafted. The case the machine genuinely
  cannot see — a site visit, a phone call — becomes a question rather than a guess.
- The `.context.md` convention that a standup joined by phone bills despite a low ratio stays
  meaningful. It is the user pre-answering the question this ADR would otherwise ask.
- The hard guards in Step 6 gain one named exception and lose nothing: an uncorroborated event never
  reaches them, because it is not a block until the user makes it one.
- The stdlib-only rule for the plugin's Python survives. The Windows-only part is Windows-only anyway,
  because classic Outlook's object model is.
- A user on new Outlook alone has no adapter. Setup says so and the calendar stays off; that is a
  Graph adapter's job, later, behind the same JSON.
- The read/write line moves from "two read, one written" to "everything but the provider is read".
  ADR-0007 should say so when it is written.

## Alternatives considered

**Calendar as skeleton input.** A meeting on the calendar overrides the AFK break inside it. Rejected:
the skeleton stops being arithmetic, a skipped meeting bills as attended, and the rule that nothing
re-infers idle — the rule that stopped screenshots and window titles inventing activity — gets its
first exception for the least reliable of the sources.

**Calendar alone is enough to draft a block.** Rejected for the same reason at lower stakes: it puts
a `LOW` block into the table on the calendar's word, and a batch-accept at review bills it. Making it
a question means the user has to say yes.

**Microsoft Graph first.** Works on any Outlook, but needs an app registration and a token, which
puts credentials on a read boundary — the line `CONTEXT.md` draws is that credentials belong at the
write boundary and nowhere else. Deferred, not rejected: it is the second adapter.

**pywin32 rather than PowerShell.** One language for the adapter, at the cost of a third-party
package on a plugin whose scripts are stdlib-only by stated design, and a pip step in setup. The
PowerShell precedent already exists for the other Windows-only piece, the screenshot pipeline.

**An ActivityWatch calendar importer.** Keeps one source, and makes the calendar *look like*
activity, which is exactly the confusion the decision above exists to prevent.
