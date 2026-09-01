#!/usr/bin/env python3
"""Generate the shared Agent Skills export from this plugin.

    python install/export_agent_skills.py [DEST]      # default: ~/.agents/skills

`~/.agents/skills/` is where the harnesses that aren't Claude Code look for skills —
Codex, OpenCode, Hermes and the rest of the Agent Skills clients. This script writes one
directory there per skill in `skills/`, so those users get the same skills without a
plugin marketplace.

Three properties are the whole design, and each is asserted by a test:

**One direction.** The plugin is the source; the export is an artifact. Nothing here reads
the export to decide what to write, so a hand-edit to it survives exactly until the next
run — which is the point. Two copies that can both be edited is the drift this replaces.

**Prefixed and renamed.** The shared directory is flat and unnamespaced: a bare `daily`
sitting among a user's other skills says nothing about where it came from, and collides
with anyone else's. Directories are therefore `<plugin>-<skill>`, and the declared `name:`
in the frontmatter is rewritten to match, because the spec requires the two to agree and
the declared name is all an activation-time consumer has to go on.

**Idempotent.** Running it twice leaves the tree byte-identical, and whatever has left the
plugin leaves the export too — a file, or a whole skill that was renamed or retired. A
stale reference a model still reads is worse than a missing one, and a stale *skill*
activates as readily as the live one. The single exception is an exported install's
`.env`, which is the user's credentials and the one piece of their data that lives inside
the artifact.

Pruning a whole skill deletes, so it takes proof rather than a guess. Each export carries
a stamp, and only a stamped directory is a candidate — `<plugin>-something` is a name a
user is free to give a skill of their own, and being in the neighbourhood is not evidence
of authorship.

No third-party deps — stdlib only, so it runs on a machine that has nothing but Python.
"""
from __future__ import annotations

import json
import os
import re
import shutil
import sys
from pathlib import Path
from typing import NoReturn

REPO = Path(__file__).resolve().parents[1]
PLUGIN_MANIFEST = REPO / ".claude-plugin" / "plugin.json"
SKILLS = REPO / "skills"
DEFAULT_DEST = Path.home() / ".agents" / "skills"

# The README section a hand-installed copy is sent to, and the GitHub anchor GitHub gives
# it. Named rather than inlined because the note below has to link it, and the repo-level
# tests check the heading still exists — a quoted heading is a link with nothing behind it.
MIGRATION_SECTION = "Coming from a hand-installed copy"
MIGRATION_ANCHOR = "#" + MIGRATION_SECTION.lower().replace(" ", "-")

# Claude Code's own global skills directory — where the retired installer put the skill,
# and not somewhere this script writes. A leftover found *there* belongs to a hand install
# whose settings are declared plugin configuration now, so its way forward is the plugin;
# one found in the export destination belongs to an export, whose way forward is this
# script. Same leftover, two different people, two different next steps.
HARNESS_SKILLS = Path.home() / ".claude" / "skills"

# Never leaves the plugin: a maintainer's own credentials sitting in their working tree,
# and the scratch pytest and CPython drop into the skill folder when its tests run.
EXCLUDED_DIRS = {"__pycache__", ".pytest_cache"}
EXCLUDED_FILES = {".env"}

# Never pruned from an existing export. An exported install has no harness to hold
# credentials, so its `.env` sits at the exported skill's root.
PRESERVED = {".env"}

# Written into every exported skill, and the only proof that a directory in the shared
# folder is this script's to retire. The prefix alone is not proof: `billables-mine` is a
# name a user is free to pick, and retirement deletes. Read to decide what to *delete*,
# never to decide what to *write* — a hand-edit still survives exactly until the next run.
STAMP = ".agent-skills-export"

# Where the installers put the skill before this export existed: unprefixed, under the
# harness's own skills directory. Such a copy still activates, and nothing here writes or
# deletes it — it may hold the `.env` the user filled in — so it is reported instead.
LEGACY_NAMES = ("daily", "daily-timesheet")


def fail(message: str) -> NoReturn:
    """Stop with one `ERROR:` line and a non-zero exit — never a traceback.

    Same contract as the bundled scripts (`skill_config.fail_missing`), and for the same
    reason: this is run from an install script, and a traceback reads as "the tool is
    broken" rather than "you pointed it somewhere I won't write".
    """
    sys.exit(f"ERROR: {message}")


def manifest() -> dict:
    return json.loads(PLUGIN_MANIFEST.read_text(encoding="utf-8"))


def source_skills() -> list[Path]:
    return sorted(p for p in SKILLS.iterdir() if (p / "SKILL.md").is_file())


def rewrite_declared_name(text: str, name: str) -> str:
    """Replace the frontmatter's `name:` with `name`, leaving every other byte alone.

    Byte-level rather than a YAML round-trip: the export has to be identical to its source
    everywhere except this one line, or the diff between the plugin and what a Codex user
    reads is a diff nobody can check by eye.
    """
    block = re.match(r"---[ \t]*\r?\n(.*?)^---[ \t]*(?:\r?\n|$)", text, re.S | re.M)
    if not block:
        fail("SKILL.md has no YAML frontmatter, so there is no name to rewrite")
    head, count = re.subn(r"^name:[^\r\n]*", f"name: {name}", block.group(1), count=1,
                          flags=re.M)
    if count != 1:
        fail("SKILL.md frontmatter declares no `name:`, which the spec requires")
    return text[:block.start(1)] + head + text[block.end(1):]


def is_ours(target: Path, prefix: str) -> bool:
    """Whether this script wrote `target`, on the evidence it left behind."""
    stamp = target / STAMP
    return stamp.is_file() and stamp.read_text(encoding="utf-8").strip() == prefix


def refuse_unless_ours(target: Path, prefix: str) -> None:
    """This script overwrites, so it has to be sure of what it is overwriting.

    Three things are safe to write over: our own stamp, a `SKILL.md` (the shape every
    export made before the stamp existed has), and nothing at all. A directory left
    holding only the user's `.env` counts as nothing: that is what retiring a skill leaves
    behind, and re-adding a skill of the same name must not then be a hard error.

    Anything else is a directory this script did not write, and the user is told rather
    than losing it.
    """
    if not target.exists():
        return
    if not target.is_dir():
        fail(f"{target} exists and is not a directory")
    if is_ours(target, prefix) or (target / "SKILL.md").is_file():
        return
    if any(p for p in target.iterdir() if p.name not in PRESERVED):
        fail(f"{target} holds files this script did not generate — move it aside first")


def export_skill(source: Path, target: Path, name: str, prefix: str) -> None:
    target.mkdir(parents=True, exist_ok=True)
    (target / STAMP).write_text(f"{prefix}\n", encoding="utf-8")
    written = {STAMP}
    for path in sorted(source.rglob("*")):
        rel = path.relative_to(source)
        if EXCLUDED_DIRS & set(rel.parts) or rel.name in EXCLUDED_FILES:
            continue
        if not path.is_file():
            continue
        out = target / rel
        out.parent.mkdir(parents=True, exist_ok=True)
        if rel.as_posix() == "SKILL.md":
            renamed = rewrite_declared_name(path.read_bytes().decode("utf-8"), name)
            out.write_bytes(renamed.encode("utf-8"))
        else:
            shutil.copy2(path, out)
        written.add(rel.as_posix())
    prune(target, written)


def prune(target: Path, written: set[str]) -> None:
    """Delete whatever this run did not write, then the directories left empty.

    Deepest paths first, so a directory is considered after the files inside it.

    Compared case-insensitively where the filesystem is: on Windows a rename upstream that
    changes only case writes through to the file already on disk under the old spelling,
    which the exact comparison then reads as "not written this run" and deletes.
    """
    kept = {os.path.normcase(rel) for rel in written | PRESERVED}
    for path in sorted(target.rglob("*"), reverse=True):
        rel = path.relative_to(target).as_posix()
        if path.is_dir():
            if not any(path.iterdir()):
                path.rmdir()
        elif os.path.normcase(rel) not in kept:
            path.unlink()


def retire_departed_skills(dest: Path, prefix: str, current: set[str]) -> list[str]:
    """Empty out exports of skills that have left the plugin, and name what was retired.

    `prune()` one level up. Without it a skill renamed or retired upstream sits in the
    shared directory forever and activates just as readily as the live one — two skills
    answering the same request, one of them frozen at whatever it said when it left.

    Only this script's own output is a candidate, and the stamp is what says so. The
    prefix on its own is not proof of authorship: `billables-mine` is a name a user is
    free to give a skill of their own, and this path deletes rather than overwrites —
    an unstamped directory is therefore left exactly where it is.

    A `.env` survives even here: the skill it belonged to is gone, the user's credentials
    are still not ours to delete, and what is left behind holds no `SKILL.md`, so nothing
    activates from it.
    """
    retired = []
    for path in sorted(dest.glob(f"{prefix}-*")):
        if path.name in current or not path.is_dir() or not is_ours(path, prefix):
            continue
        prune(path, set())
        if not any(path.iterdir()):
            path.rmdir()
        retired.append(path.name)
    return retired


def legacy_installs(dest: Path) -> list[Path]:
    """Older, unprefixed copies of this skill that are still live on this machine."""
    roots = {dest, HARNESS_SKILLS}
    return sorted(root / name for root in roots for name in LEGACY_NAMES
                  if (root / name / "SKILL.md").is_file())


def main(argv: list[str]) -> int:
    if len(argv) > 1:
        fail(f"usage: {Path(__file__).name} [DEST]   (default: {DEFAULT_DEST})")
    dest = Path(argv[0]).expanduser() if argv else DEFAULT_DEST

    plugin = manifest()
    prefix, version = plugin["name"], plugin["version"]
    skills = source_skills()
    if not skills:
        fail(f"no skills found under {SKILLS}")

    if dest.exists() and not dest.is_dir():
        fail(f"{dest} is not a directory")
    try:
        dest.mkdir(parents=True, exist_ok=True)
    except OSError as exc:
        fail(f"cannot create {dest}: {exc.strerror or exc}")

    print(f"Exporting {prefix} v{version} to {dest}")
    exported = set()
    for skill in skills:
        name = f"{prefix}-{skill.name}"
        refuse_unless_ours(dest / name, prefix)
        export_skill(skill, dest / name, name, prefix)
        exported.add(name)
        print(f"  {name}")

    for name in retire_departed_skills(dest, prefix, exported):
        print(f"  {name} (no longer part of this plugin — removed)")

    print(f"Done. {len(skills)} skill(s) exported as {prefix}-*.")
    for legacy in legacy_installs(dest):
        print()
        print(f"NOTE: an older, unprefixed copy of this skill is still at {legacy}.")
        print("      It activates too, and this script neither writes nor deletes it — so")
        print("      this run has not updated it, and no run of this script ever will.")
        if legacy.parent == HARNESS_SKILLS:
            print("      That copy was hand-installed, and the settings it holds are")
            print("      declared plugin configuration now. The way off it is the plugin,")
            print(f'      not this export — "{MIGRATION_SECTION}":')
            # The URL, not just the filename: this can be run by someone who has no clone
            # (the README documents asking an agent to fetch and regenerate), and naming a
            # file they do not have is the same as naming nothing.
            print(f"      {plugin['repository']}{MIGRATION_ANCHOR}")
        else:
            print("      Move any .env you filled in there across, then delete that folder.")
    print("An exported install has no harness to hold credentials: copy the exported")
    print("skill's `.env.example` to `.env` beside it and fill it in. That file is kept")
    print("across regenerations; everything else in the export is rewritten.")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
