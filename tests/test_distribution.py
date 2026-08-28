"""Guards on the artifact that actually gets installed.

This repo is a marketplace whose single plugin is the repo root, so what a stranger
installs is not the code these tests import — it is two manifests plus `skills/`. Those
fail in ways no script-level test can see: a manifest that won't parse, a skill whose
declared name disagrees with its directory, a version that drifted from the changelog.
Nothing here reaches into the code that produced the artifact; every assertion is on
something a consumer can read.

The platform's own validator carries most of it. It is not vendored — asserting our idea
of the schema would be asserting our idea of the schema — so the tests that need it skip
when the `claude` CLI isn't on PATH, and the structural assertions below stand on their own
without it.
"""

import json
import re
import shutil
import subprocess
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]
MANIFEST_DIR = REPO / ".claude-plugin"
PLUGIN_MANIFEST = MANIFEST_DIR / "plugin.json"
MARKETPLACE_MANIFEST = MANIFEST_DIR / "marketplace.json"
SKILLS = REPO / "skills"

PLUGIN_NAME = "billables"
MARKETPLACE_NAME = "activity-to-timesheet"

CLAUDE = shutil.which("claude")
requires_claude = pytest.mark.skipif(not CLAUDE, reason="the claude CLI is not on PATH")


def validate(target: Path):
    """`claude plugin validate --strict <target>` — returncode plus combined output."""
    return subprocess.run([CLAUDE, "plugin", "validate", "--strict", str(target)],
                          capture_output=True, text=True, encoding="utf-8", errors="replace")


def validator_warnings(output: str) -> set[str]:
    """The `❯ <text>` lines the validator reports, one per warning."""
    return {m.group(1).strip() for m in re.finditer(r"^\s*❯ (.+)$", output, re.M)}


def manifest(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def skill_dirs() -> list[Path]:
    return sorted(p for p in SKILLS.iterdir() if (p / "SKILL.md").is_file())


def frontmatter_name(skill_md: Path) -> str | None:
    """The `name:` from the YAML frontmatter, or None if there is no frontmatter."""
    text = skill_md.read_text(encoding="utf-8")
    if not text.startswith("---"):
        return None
    head = text.split("---", 2)[1]
    match = re.search(r"^name:\s*(\S+)\s*$", head, re.M)
    return match.group(1) if match else None


# --------------------------------------------------------------------------------------
# The platform's validator
# --------------------------------------------------------------------------------------

@requires_claude
def test_the_marketplace_manifest_validates_strictly():
    """What `/plugin marketplace add` reads first. A stranger's install stops here."""
    res = validate(REPO)
    assert res.returncode == 0, res.stdout + res.stderr


@requires_claude
def test_the_shipped_skills_validate_strictly():
    """Frontmatter the harness rejects makes a skill silently absent, not broken."""
    res = validate(SKILLS)
    assert res.returncode == 0, res.stdout + res.stderr


# The plugin root is the repo root, so the repo's own `CLAUDE.md` is a file the plugin
# carries and does not use. Deleting it is not the fix: checked on 2026-08-28, a fresh
# Claude Code session in this repo with `CLAUDE.md` moved aside loads no project
# instructions at all — not `AGENTS.md`, which `CLAUDE.md` exists to import. So the
# warning is accepted, and pinned here rather than left to be rediscovered.
CLAUDE_MD_AT_PLUGIN_ROOT = re.compile(r"CLAUDE\.md at the plugin root")


@requires_claude
def test_the_plugin_manifest_carries_no_warning_but_the_accepted_one():
    """Pinned, not suppressed: a *second* warning fails this, which is the point.

    Asserting the set rather than the exit code is what keeps the accepted exception from
    turning into a blanket "warnings are fine here" — the next one has to be looked at.
    """
    res = validate(PLUGIN_MANIFEST)
    unexpected = {w for w in validator_warnings(res.stdout + res.stderr)
                  if not CLAUDE_MD_AT_PLUGIN_ROOT.search(w)}
    assert not unexpected, (
        "the plugin manifest has a warning nobody has decided about:\n  "
        + "\n  ".join(sorted(unexpected)))


# --------------------------------------------------------------------------------------
# Structure, without the CLI
# --------------------------------------------------------------------------------------

def test_the_plugin_is_the_repo_root():
    """The single-plugin-repo layout: manifests in `.claude-plugin/`, components beside it.

    Components nested inside `.claude-plugin/` are not discovered, and the failure is
    silence — the plugin installs and has nothing in it.
    """
    assert PLUGIN_MANIFEST.is_file() and MARKETPLACE_MANIFEST.is_file()
    assert SKILLS.is_dir(), "skills/ is not at the plugin root"
    assert not (MANIFEST_DIR / "skills").exists(), "skills/ nested where nothing reads it"


def test_the_plugin_name_is_the_one_that_prefixes_every_skill():
    """`/billables:daily`. The name prefixes every skill, so changing it breaks installs —
    it is treated as permanent, and this is what says so."""
    assert manifest(PLUGIN_MANIFEST)["name"] == PLUGIN_NAME


def test_the_marketplace_offers_this_repo_as_the_plugin():
    mkt = manifest(MARKETPLACE_MANIFEST)
    assert mkt["name"] == MARKETPLACE_NAME
    entries = [p for p in mkt["plugins"] if p["name"] == PLUGIN_NAME]
    assert len(entries) == 1, f"{PLUGIN_NAME} is not offered exactly once: {mkt['plugins']}"
    assert entries[0]["source"] == "./", "the plugin source is not the repo root"


def test_at_least_one_skill_ships():
    assert skill_dirs(), "the plugin ships no skills"


@pytest.mark.parametrize("skill", skill_dirs(), ids=lambda p: p.name)
def test_each_declared_skill_name_matches_its_directory(skill):
    """The directory is what a user types; the frontmatter is what a consumer reads. When
    they disagree there is no single answer to "what is this skill called", and the shared
    Agent Skills directory — flat and unnamespaced — has only the declared name to go on."""
    assert frontmatter_name(skill / "SKILL.md") == skill.name


# The `owner/repo` a user types into `/plugin marketplace add`. It is not the marketplace
# name and not the plugin name, so nothing else in here pins it — which is how the docs
# came to name a slug that returned 404 for a day.
SLUG = "Cordedmink2/activity-to-timesheet"
SLUG_DOCS = [REPO / "README.md", REPO / "llms.txt",
             SKILLS / "daily" / "references" / "reporting-issues.md"]


@pytest.mark.parametrize("doc", SLUG_DOCS, ids=lambda p: p.name)
def test_every_documented_repo_slug_is_the_same_one(doc):
    """One slug across the install commands, the manifest and the issue-filing command.

    `reporting-issues.md` matters most: it is the only route an installee has for a defect
    report, and a stale `-R owner/repo` there fails at the moment they are already annoyed.
    """
    found = set(re.findall(r"Cordedmink2/[A-Za-z0-9._-]+", doc.read_text(encoding="utf-8")))
    assert found <= {SLUG}, f"{doc.name} names another repo slug: {sorted(found - {SLUG})}"


def test_the_manifest_points_at_the_same_repo():
    mf = manifest(PLUGIN_MANIFEST)
    for field in ("homepage", "repository"):
        assert SLUG in mf[field], f"plugin.json {field} does not name {SLUG}: {mf[field]}"


GH = shutil.which("gh")


@pytest.mark.skipif(not GH, reason="the gh CLI is not on PATH")
def test_the_documented_slug_resolves_on_github():
    """The check that a doc sweep cannot do for itself.

    Renaming the repo leaves the docs naming a slug that 404s, and every local assertion
    still passes because they are all internally consistent. Only GitHub knows. Skipped
    rather than failed when the network or `gh` auth is unavailable, so it is evidence when
    it runs and never a false alarm when it can't.
    """
    res = subprocess.run([GH, "repo", "view", SLUG, "--json", "nameWithOwner"],
                         capture_output=True, text=True, encoding="utf-8", errors="replace")
    if res.returncode != 0:
        stderr = res.stderr.lower()
        if "not found" in stderr or "could not resolve" in stderr:
            pytest.fail(f"{SLUG} does not resolve on GitHub — the install commands 404")
        pytest.skip(f"cannot reach GitHub: {res.stderr.strip()[:120]}")
    assert json.loads(res.stdout)["nameWithOwner"] == SLUG


def test_every_version_marker_agrees():
    """Three markers exist while `VERSION` is still shipped — the manifest (what a
    marketplace displays), the `VERSION` file, and the changelog. Any one of them going
    stale is worse than it being absent, and the manifest/`VERSION` pair is the likeliest
    to drift because nothing bumps them together.
    """
    changelog = (REPO / "CHANGELOG.md").read_text(encoding="utf-8")
    released = re.search(r"^## \[(\d+\.\d+\.\d+)\]", changelog, re.M)
    assert released, "no released version heading in CHANGELOG.md"
    markers = {
        "plugin.json": manifest(PLUGIN_MANIFEST)["version"],
        "skills/daily/VERSION": (SKILLS / "daily" / "VERSION").read_text(encoding="utf-8").strip(),
        "CHANGELOG.md": released.group(1),
    }
    assert len(set(markers.values())) == 1, f"version markers disagree: {markers}"
