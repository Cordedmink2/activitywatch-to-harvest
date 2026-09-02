"""One guard, for the two skills that have to find a sibling on either install shape.

`setup` and `reconcile` both reach into the `daily` skill beside them — one for the
screenshot setup script, the other for the scripts a per-day investigation runs. Neither
can hardcode where that directory is: a plugin install keeps the name `daily`, and the
shared Agent Skills export prefixes it to `billables-daily`, because that directory is
flat and unnamespaced. A skill that names only one of the two fails on the other as "file
not found", which reads like a broken install rather than a wrong path.

It lives here rather than in either skill's own module because it was written twice, once
each, with bodies that differed in nothing but the tail of the failure message — so a
correction to the check was a correction to one skill's copy of it, and the next skill to
reach for a sibling would have been a third. What each skill needs the sibling *for* is
the part that genuinely differs, so that travels as a parameter and still names itself in
the failure.
"""

import re

import pytest

from shipped import SKILLS, shipped_text

# (skill, what a wrong prefix costs that skill), which is the half of the old message
# worth keeping: "cannot resolve" on its own does not tell a reader what stopped working.
NEEDS_A_SIBLING = [
    pytest.param("setup", "the screenshot setup script", id="setup"),
    pytest.param("reconcile", "the scripts it runs", id="reconcile"),
]

INSTALL_SHAPES = ["daily", "billables-daily"]


@pytest.mark.parametrize("skill,resolves", NEEDS_A_SIBLING)
@pytest.mark.parametrize("sibling", INSTALL_SHAPES)
def test_it_can_find_its_sibling_skill_on_either_install_shape(skill, resolves, sibling):
    """A skill that names only one directory works on the install it was written against
    and fails on the other with "file not found" — which reads as a broken install, not as
    a wrong path, and sends the user reinstalling."""
    text = shipped_text(SKILLS / skill)
    assert re.search(rf"(?<![\w-]){re.escape(sibling)}(?![\w-])", text), (
        f"the {skill} skill never mentions a sibling directory named {sibling}, so one of "
        f"the two install shapes cannot resolve {resolves}")
