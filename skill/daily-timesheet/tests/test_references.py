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
        text = open(path, encoding="utf-8").read()
        for lineno, line in enumerate(text.splitlines(), 1):
            for script in SKILL_RELATIVE.findall(line):
                if script not in shipped:
                    missing.append(f"{os.path.basename(path)}:{lineno} -> scripts/{script}")
    assert not missing, (
        "documented as `python scripts/…` (skill-relative) but not shipped in the skill; "
        "qualify the path if it lives in the user's workspace:\n  " + "\n  ".join(missing)
    )
