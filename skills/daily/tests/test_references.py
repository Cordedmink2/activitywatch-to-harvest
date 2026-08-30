"""Guards on the skill's own documentation.

SKILL.md tells the model that `python scripts/…` resolves inside the skill
folder. Any command written that way therefore has to name a script the skill
actually ships — otherwise the model runs a path that doesn't exist and reports
a missing file instead of taking the documented route.
"""

import os
import re

SKILL = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SCRIPTS = os.path.join(SKILL, "scripts")

# `python scripts/foo.py`, the shape SKILL.md defines as skill-relative.
SKILL_RELATIVE = re.compile(r"python\s+scripts/([A-Za-z0-9_]+\.py)")


def docs():
    yield os.path.join(SKILL, "SKILL.md")
    refs = os.path.join(SKILL, "references")
    for name in sorted(os.listdir(refs)):
        if name.endswith(".md"):
            yield os.path.join(refs, name)


def test_every_skill_relative_command_names_a_shipped_script():
    shipped = set(os.listdir(SCRIPTS))
    missing = []
    for path in docs():
        with open(path, encoding="utf-8") as fh:
            text = fh.read()
        for lineno, line in enumerate(text.splitlines(), 1):
            for script in SKILL_RELATIVE.findall(line):
                if script not in shipped:
                    missing.append(f"{os.path.basename(path)}:{lineno} -> scripts/{script}")
    assert not missing, (
        "documented as `python scripts/…` (skill-relative) but not shipped in the skill; "
        "qualify the path if it lives in the user's workspace:\n  " + "\n  ".join(missing)
    )


# `[--confirm]` in a list of a script's optional flags is documentation; a bare `--confirm`
# on a command line is a template someone will copy.
OPTIONAL = re.compile(r"\[[^\]]*\]")
WRITE_COMMAND = re.compile(r"python\s+scripts/harvest_(post|patch)\.py")


def test_no_documented_command_hands_over_the_confirmation_flag_ready_typed():
    """The write scripts do nothing without `--confirm`, and that gate is only worth
    anything while adding the flag stays a deliberate act.

    A copy-paste command with the flag already in it makes writing the default action of
    the template — so a model that skipped the Step 8 confirmation, which is the case the
    flag exists to catch, posts anyway by pasting what the doc handed it. The instructions
    say to append it after the user's yes; nothing that reads as a command may pre-empt
    that. A bracketed `[--confirm]` among a script's other optional flags is fine.
    """
    offenders = []
    for path in docs():
        with open(path, encoding="utf-8") as fh:
            for lineno, line in enumerate(fh.read().splitlines(), 1):
                match = WRITE_COMMAND.search(line)
                if not match:
                    continue
                # The command runs to the closing backtick of an inline-code span, or to
                # the end of the line inside a fenced block. Prose after it — which is
                # where the instruction to append the flag belongs — is not the command.
                command = line[match.start():].split("`")[0]
                if "--confirm" in OPTIONAL.sub("", command):
                    offenders.append(f"{os.path.basename(path)}:{lineno}: {command.strip()}")
    assert not offenders, (
        "a documented command hands over `--confirm` ready-typed, which makes posting the "
        "default action of a copied template; append it in the surrounding prose instead, "
        "or write it as an optional `[--confirm]`:\n  " + "\n  ".join(offenders)
    )
