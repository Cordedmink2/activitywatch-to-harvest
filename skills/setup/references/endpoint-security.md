# When endpoint security blocks a step

Read this when a step in `SKILL.md` fails in a way that looks like it was blocked. It has two halves, in this order: how to establish that it actually was, and what to ask for once that is established. Doing the second without the first is how this goes wrong.

## Why this setup attracts attention

Nothing here is unusual on its own, and the combination is exactly what spyware looks like: a scheduled task runs a windowless Python process every couple of minutes, grabs the screen, and writes image files. A browser extension rewrites every window title. Neither is malicious and neither is unusual on a consultant's machine, but a detection engine has no way to tell.

So expect it, and treat a block as a normal outcome with a normal remedy — not as a fault, and not as a reason to work around the control.

## Prove the block before escalating

**The failure that looks most like endpoint security is a broken Python install.** The first coworker install of this pipeline ended with its user raising an EDR allow-list ticket; the actual fault was a split Python whose `sys.prefix` did not resolve, which needed no ticket at all. A wrongly-raised ticket costs that user days and costs the next person credibility.

So before you tell anyone this was blocked, name the thing you actually read. One of:

- **A quarantine entry.** `Get-MpThreatDetection` on Windows Defender lists detections; the `Resources` field names the path that was quarantined. An empty result is not proof of innocence — a third-party agent will not appear here — but a result naming `screenshot_capture.py` or its folder is proof of guilt, and it is the single most useful line to put in a ticket.
- **A denied registration.** The error text from the scheduled-task registration itself. `Access is denied` is usually a previously-elevated task rather than a security product; a policy denial reads differently and quotes a policy.
- **A blocked download.** A `pip install` that fails with a proxy or TLS error rather than a resolution error — the message names the proxy.
- **A missing file.** The capture script was on disk before and is not now, or the folder is empty where it used to have files. Confirm it with a directory listing, not by inference.

If none of those is available, say exactly that: "the task registers and never captures, and I cannot find a quarantine record — this may be endpoint security or it may be the interpreter." Then rule out the interpreter first, because that is the one you can test yourself.

## What to ask for

An allow-list request has to name things a security team can enter into a console. "Allow-list the skill" is not one of those, and comes back with questions. Read the real values off this machine and quote them.

### The capture task and its script

Read the resolved values back rather than describing them:

```powershell
(Get-ScheduledTask -TaskName WorkScreenshots).Actions | Select-Object Execute, Arguments
```

That prints the interpreter's absolute path and, as its first argument, the absolute path of `screenshot_capture.py`. The request is those two paths, plus the task name `WorkScreenshots`, described honestly: a scheduled task that runs a Python script to capture the user's own screen to their own Pictures folder, for their own timesheet, with no network egress.

Include the capture directory too — the configured `TIMESHEET_SCREENSHOTS_DIR`, or `~/Pictures/WorkScreenshots` when it is unset — since a write-blocking rule and an execution-blocking rule are different exclusions.

### The browser extension

A managed Edge or Chrome refuses extensions not on the policy allow-list, and the request is the extension's ID rather than its name:

- **URL in Title** — `ignpacbgnbnkaiooknalneoeladjnfgb`

The policy is `ExtensionInstallAllowlist` (and, if the ID appears there, removal from `ExtensionInstallBlocklist`). The extension reads the URL of the current tab and writes it into the window title; it sends nothing anywhere.

### Reaching the package index

If `pip install` was blocked by a proxy rather than by a detection, the ask is index access for two packages, `mss` and `Pillow`, both from PyPI. Where an internal mirror exists, using it is usually faster than getting an exception approved.

## What not to ask for

- **Do not ask for a blanket exclusion of a folder.** A folder-wide exclusion is more than this needs, is more likely to be refused, and leaves a hole that outlives the install.
- **Do not ask the user to disable protection, even briefly.** A step that only works with protection off is a step that will break again on the next scan, and the request itself will be remembered.
- **Do not retry a blocked step hoping it takes.** Repeated attempts against a detection engine escalate on their own, and the user hears about it from someone else.

## Once it is allow-listed

Re-run the step and re-run its check from `SKILL.md` — the allow-list being in place is not evidence that the step now works. For the capture task specifically, fire one capture by hand and confirm the files land before believing the schedule will.
