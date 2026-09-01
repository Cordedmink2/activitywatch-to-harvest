"""Guards on the `setup` skill — the walkthrough for the parts only a person can do.

Every other skill in this plugin fails loudly: a script exits non-zero and says why. This
one fails *silently*, because what it is walking someone through is a machine the agent
cannot see. A step that is described but never checked reads exactly like a step that
worked, and the cost lands days later as a timesheet with nothing in it.

So the assertions here are about the shape of the walkthrough rather than its prose: that
every step carries a check and a recourse, that the allow-list ask names the strings the
screenshot setup script actually registers, and that the skill can find its sibling
whichever way the plugin was installed. Each one is something that goes stale on an edit
somewhere else in the tree — which is the only kind of prose worth a test.
"""

import re
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]
SKILLS = REPO / "skills"
SETUP = SKILLS / "setup"
SETUP_MD = SETUP / "SKILL.md"
SCREENSHOT_SETUP = SKILLS / "daily" / "scripts" / "setup_screenshot_pipeline.ps1"


def setup_text() -> str:
    """Empty when the skill is absent, so that reads as one failed test rather than a
    collection error that takes the rest of this module down with it."""
    return SETUP_MD.read_text(encoding="utf-8") if SETUP_MD.is_file() else ""


def shipped_text() -> str:
    """SKILL.md plus every reference, joined — the whole of what a run can read.

    Which file a given sentence lives in is an editorial decision that should stay free to
    change; that it is somewhere in the skill is the promise.
    """
    parts = [setup_text()]
    parts += [p.read_text(encoding="utf-8") for p in sorted(SETUP.rglob("*.md"))
              if p != SETUP_MD]
    return "\n".join(parts)


def steps() -> list[tuple[str, str]]:
    """Each `### ` step under `## Steps`, as (heading, body)."""
    text = setup_text()
    if "## Steps" not in text:
        return []
    section = text.split("## Steps", 1)[1].split("\n## ", 1)[0]
    found = re.split(r"^### (.+)$", section, flags=re.M)[1:]
    return list(zip(found[0::2], found[1::2]))


def step_ids() -> list[str]:
    return [h.strip() for h, _ in steps()]


def test_the_setup_skill_ships():
    assert SETUP_MD.is_file(), "there is no setup skill"


def test_it_walks_through_more_than_one_step():
    assert len(steps()) >= 2, "a walkthrough with one step is not a walkthrough"


@pytest.mark.parametrize("step", steps(), ids=step_ids())
def test_every_step_is_verified_rather_than_assumed(step):
    """The whole reason this skill exists rather than a paragraph in the README.

    A desktop app the user says they installed, an extension they say they added, a
    scheduled task that registered without error — none of those are evidence, and each
    has been observed to fail while looking fine.
    """
    heading, body = step
    assert "**Verify**" in body, (
        f"step '{heading.strip()}' tells the user what to do and never checks that it "
        "took effect")


@pytest.mark.parametrize("step", steps(), ids=step_ids())
def test_every_step_says_what_to_do_when_the_check_fails(step):
    """A check with no recourse hands the failure straight back to the user, which is the
    state this skill was written to replace."""
    heading, body = step
    assert "**If it fails**" in body, (
        f"step '{heading.strip()}' checks itself and says nothing about a check that "
        "comes back bad")


# The two strings a user has to hand their security team. Both are defined in the
# screenshot setup script, not here, so renaming either there is what this catches — the
# skill would go on naming a task that no longer exists, in a request nobody can action.
def screenshot_setup_defaults() -> dict[str, str]:
    src = SCREENSHOT_SETUP.read_text(encoding="utf-8-sig")
    task = re.search(r"\$TaskName\s*=\s*[\"']([^\"']+)[\"']", src)
    assert task, "no default -TaskName in the screenshot setup script"
    capture = re.search(r"([A-Za-z0-9_]+\.py)", src)
    assert capture, "the screenshot setup script names no capture script"
    return {"task": task.group(1), "capture": capture.group(1)}


@pytest.mark.parametrize("field", ["task", "capture"])
def test_the_allow_list_ask_names_what_the_setup_script_actually_registers(field):
    """"Allow-list the skill" is not a request a security team can action; a task name and
    a filename are. Pinned against the script so the ask cannot go stale on a rename."""
    value = screenshot_setup_defaults()[field]
    assert value in shipped_text(), (
        f"the allow-list guidance never names {value!r}, which is what the screenshot "
        "setup script registers")


def test_a_block_has_to_be_evidenced_before_it_is_escalated():
    """The first coworker install sent its user to IT for an EDR allow-list when the real
    fault was a split Python install that needed no ticket at all. Naming the log line,
    quarantine entry or denied registration actually read is what separates the two."""
    text = shipped_text().lower()
    assert "quarantine" in text, "nothing tells the run how to evidence a block"
    assert re.search(r"before (you |)(ask|escalat|rais)", text), (
        "the skill never says to prove the block before sending the user to their "
        "security team")


# The skill has to reach the screenshot setup script, which lives in the `daily` skill
# beside it. Both names are real: a plugin install keeps the directory name, and the
# shared Agent Skills export prefixes it, because that directory is flat.
@pytest.mark.parametrize("sibling", ["daily", "billables-daily"])
def test_it_can_find_its_sibling_skill_on_either_install_shape(sibling):
    assert re.search(rf"(?<![\w-]){re.escape(sibling)}(?![\w-])", shipped_text()), (
        f"the skill never mentions a sibling directory named {sibling}, so one of the two "
        "install shapes cannot resolve the screenshot setup script")


def test_it_states_when_setup_is_finished():
    """The line between "installed" and "ready to use". Without it the user is left
    guessing whether the silence means done or stuck."""
    text = setup_text()
    assert re.search(r"^## .*\b(done|finished|complete)\b", text, re.M | re.I), (
        "SKILL.md has no section that says setup is over")


def test_it_points_at_the_configuration_dialog_rather_than_asking_for_values():
    """Declared configuration already holds the credentials, the timezone and the paths.
    A walkthrough that asks for them again is a second place for them to be wrong, and
    puts a token into a session transcript that gets written to disk."""
    assert "/plugin configure billables" in shipped_text(), (
        "the skill never routes a missing configured value to the dialog that owns it")
