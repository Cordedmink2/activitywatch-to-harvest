# Intent: Reconstruct work activity into a trustworthy timesheet

Author: Connor  
Status: draft  
Created: 2026-08-31

## Problem

Consultants working across multiple clients have to reconstruct their timesheets from memory.

Evidence of what they worked on already exists in their computer activity, but it is fragmented. Rebuilding the day manually is slow, error-prone, and makes legitimate billable work easy to forget.

## Proposed outcome

A user asks their agent to reconstruct a workday and receives a reviewable set of proposed time blocks based on recorded activity.

The result should be close enough to reality that reviewing and correcting it is substantially easier than rebuilding the day from memory.

Nothing is billed until the user explicitly approves it.

## Affected users and systems

Consultants working across multiple clients from one computer.

Today the workflow uses ActivityWatch as the activity source, an agent to interpret the evidence, and Harvest as the timesheet provider.

## Constraints

- Recorded activity is evidence, not the authoritative timesheet.
- Uncertainty must be surfaced rather than hidden.
- Personal or non-billable activity must not silently become billable work.
- User-specific clients and billing conventions must remain separate from the generic product.
- The product should not depend conceptually on ActivityWatch or Harvest, even though they are the current implementations.

## Open questions

- What evidence is sufficient to confidently attribute a period of work?
- How much supporting activity data is needed to resolve ambiguous periods?
- How far should the product extend beyond reconstructing a normal workday?
