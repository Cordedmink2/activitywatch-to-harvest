# Intent: Reconstruct work activity into a trustworthy timesheet

Author: Connor  
Status: draft  
Created: 2026-08-31

## Problem

Consultants working across multiple clients in the same day have to reconstruct their timesheets from memory.

The evidence of what they worked on already exists across their computer activity — applications, browser tabs, repositories, meetings, periods away from the computer, and other work signals — but it is fragmented and not directly useful for billing.

Reconstructing the day manually is slow, easy to get wrong, and makes it possible to forget legitimate billable work entirely.

## Proposed outcome

A user can ask their agent to reconstruct a workday from recorded activity and receive a clear, reviewable set of proposed time blocks.

The system should:

- determine when work happened;
- identify meaningful changes between clients and pieces of work;
- attribute blocks to the most likely client, project and type of work;
- use available evidence to explain ambiguous periods;
- surface uncertainty rather than hide it;
- let the user correct the proposed timesheet; and
- record only the entries the user explicitly approves.

The end result should make completing a reliable timesheet substantially easier than reconstructing the day manually.

## Affected users and systems

Primary users are consultants who work for multiple clients from the same computer and record their time in a timesheet system.

The system currently involves:

- an agent running the `billables` skills;
- ActivityWatch as the activity source;
- browser and application activity;
- optional screenshots as additional evidence;
- the user's local workspace and personal classification rules; and
- Harvest as the current timesheet provider.

ActivityWatch and Harvest are the implementations used today, not the definition of the problem the product solves.

## Constraints

- **The user remains the authority on what gets billed.** No entry is created or changed without deliberate user approval.
- Recorded activity is evidence, not an authoritative timesheet. The system proposes; the user decides.
- Uncertain attribution must be visible. The system must not manufacture certainty simply to produce a complete-looking timesheet.
- Personal or non-billable activity must not silently become billable work.
- Client names, project names, provider task names, personal billing conventions and similar user-specific facts belong to the user's configuration or workspace, not the generic product.
- Generic classification logic should use provider-neutral domain concepts so supporting another timesheet provider does not require rewriting how a day is understood.
- Provider-specific code may remain provider-specific where it actually talks to that provider.
- Harvest remains the bundled provider implementation until a real second provider provides enough evidence to design the correct abstraction.
- Credentials and other secrets must remain outside version-controlled product content.
- Updating or reinstalling the product must not overwrite the user's timesheets, configuration or learned conventions.
- The product should minimise the amount of manual setup and repeated configuration required without weakening the approval boundary.

## Out of scope

The product is not intended to:

- autonomously submit a timesheet without review;
- act as employee-monitoring or management-surveillance software;
- replace the user's timesheet provider;
- make billing-policy decisions that belong to the user or their organisation;
- solve provider abstraction in anticipation of hypothetical providers; or
- treat every period of computer activity as billable work.

## What success looks like

At the end of a normal workday, a user should be able to invoke the tool and get a proposed timesheet that is close enough to reality that reviewing and correcting it takes substantially less effort than rebuilding the day from memory.

A successful result:

- captures work the user would otherwise have forgotten;
- separates meaningful switches between clients and work;
- gives enough evidence for the user to understand questionable blocks;
- clearly identifies low-confidence periods;
- respects personal and non-billable time;
- produces entries using the user's actual projects and tasks; and
- cannot create those entries until the user explicitly confirms them.

The same underlying model of a workday should remain useful if the activity source or timesheet provider changes later.

## Open questions

- How much evidence should be required before an attribution is considered high confidence?
- When evidence conflicts, which signals should take precedence and which decisions should always be returned to the user?
- How little screenshot capture can be used while retaining enough information to resolve otherwise ambiguous activity?
- What privacy and retention defaults should apply to captured activity and screenshots?
- How much of setup can ultimately be automated while still making each important assumption visible to the user?
- What requirements from the first genuine second activity source or timesheet provider should define the eventual adapter boundaries?
- How far should the product expand beyond daily reconstruction — for example reconciliation of missed days — while remaining one coherent product rather than becoming general time-management software?
