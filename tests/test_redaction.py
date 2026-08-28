"""A guard that keeps the redacted names out of the repo.

The repo used to name the maintainer's clients, employer and colleagues across shipped
instructions, reference docs, script docstrings, test scenarios and golden fixtures. Those
names were replaced with neutral placeholders. Without a guard that is a cleanup somebody
did once, and the next paste of a real window title puts one back.

The names themselves are not in this file: a list of them would be exactly the leak the
test exists to prevent. Each is stored as the SHA-256 of its normalised form — lowercased
and cut into words at every run of non-alphanumerics *and* at each letter/digit boundary —
and the scan cuts up the repo's own text the same way and looks for a collision. That last
cut is what makes a glued job code like `ABC2232S` reach the scan as `abc`.

To add a name, run `python tests/test_redaction.py "Some Name"`: it prints the digest line
to paste and the group to paste it into, and nothing here needs the name spelled out. Paste
it under the wrong word count and it can never fire, which is why the helper says which
group. Then bump that group's number in EXPECTED — deleting a digest to green a failing run
is the one way this guard quietly stops guarding.

Matching is on whole words, so a name reaches the scan through `ACME-CR202` or
`acme.example.com` but not through `AcmePortal` glued into one word, and a two-word name
only fires on the whole phrase — its halves are usually ordinary English. Short CRM codes
are in only where the code is not also a word somebody might write: the one guarding an
asset tag doubles as shorthand for an access-control list, and would rather fire on that
sentence than miss the tag. That is deliberate: a guard that fires on prose gets deleted,
and a near-miss costs one review comment.
"""

import hashlib
import re
import subprocess
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]

# SHA-256 of each redacted name, grouped by how many words it normalises to.
REDACTED = {
    1: frozenset({
        "0667bd893799ba7a888de6d210b773825f25e1576e9ad503c0061015868192e1",
        "0b22f8557ca1617cdc0d4b7d8764f63af5f7677415b2ef7f447c22f6d86b39f4",
        "0c818d05069e278205f3adbc8c9bcd495a5100bc7cdd6b22d726e1be087746be",
        "109e0db9f5c1d1d658493222f60c778dcee07c8a3c4696a81b72d42f696826aa",
        "254602a0aa2dfa1e30da7a51e9b81d45e729ef071f0b2a7c66e1f9c83ecf797a",
        "2344f08e51026cf9ab687357a588e941f1a861cfed58272911c2288a7ab1f52b",
        "3155a6c3f230073da9ca322589b479fafe92e3304971b1fba724a8b24c2f335b",
        "3bf39bf3fe465c0600105b3451f274fa9f05b3c706f022608c0fb28285fe5cbf",
        "49992130d1d16c9cb0b2c369c18288904bf48a6fc2cc3a9a230f7687fe7a3ffc",
        "64808eb7b5360b4a304f5e5e49ad4563ce38a2fa0daed7fd4c720e6ab96a6eb7",
        "6dd1a46715dce1d52cb51e15df66869442deee3fb90fb04bb6a145f136ea34fd",
        "7e30cb8b63fde7d4f89ef30c59061782d5b4ea8375c0ed640bca836adf274787",
        "98f9b97f860b4f858ac206ddcbf5306cb8b2bfb1451688be35ac53396980b16b",
        "a2b012cc08eaf562a692503dada9fb4c76bf61802f2442d42878b1085a7c19b7",
        "c7a86bd72bd1ace4906422f8d02e99a6ab9319f66bd3e2722214d3591798711e",
        "cf55a3780f10f837fc77d851440ff00e232ac1e85a75baff910af3a975dfe44c",
        "d6e0ee7bc9c0152722569560c3a972706e2e6f469f43a695c2290191385ef5bc",
    }),
    2: frozenset({
        "46fdc5659b28cd63257572d4e112df30285347dde1c3222ed737529be8be2dcd",
        "94fa92e9114b394812f8e39c39c03fb85e23005605bd8882d16b83535da2a470",
        "b1de89d633541505522e9489eb1d636c6559caaddde9898e2f28b7fce03aa5d8",
        "ef2bcb18bd7e96ff76df94d0b077b1baed13b1e909042015359ec2f48f197c61",
    }),
}

# How many digests each group is supposed to hold. A tripwire, not a fact worth knowing:
# a digest can be deleted to green a failing run and nothing else in here would notice.
EXPECTED = {1: 17, 2: 4}

WORD = re.compile(r"[a-z]+|[0-9]+")

FIX = """
Those are real client, employer or colleague names. Replace each with a neutral
placeholder in the house style — Acme, Beta Industries, Contoso, Northwind Consulting;
`skill/daily-timesheet/references/context.md.example` is the model — rather than deleting
the sentence around it. A genuine coincidence (an ordinary word that happens to collide)
is a reason to reword that line, not to drop the digest.
"""


def words(text: str) -> list[str]:
    return WORD.findall(text.lower())


def digest(phrase: str) -> str:
    return hashlib.sha256(phrase.encode()).hexdigest()


def redacted_names_in(text: str, redacted=REDACTED) -> set[str]:
    """Every redacted name the text contains, normalised — `NZ-Widgets` comes back as
    `nz widgets`, which is enough to find the line it came from."""
    found = set()
    ws = words(text)
    for length, digests in redacted.items():
        phrases = {" ".join(ws[i:i + length]) for i in range(len(ws) - length + 1)}
        found |= {phrase for phrase in phrases if digest(phrase) in digests}
    return found


def tracked_files(repo: Path = REPO) -> list[Path]:
    """Everything git knows about — so a name added to a brand new file is caught the
    moment that file is staged, not only in the files that were once cleaned."""
    out = subprocess.run(["git", "ls-files", "-z"], cwd=repo, check=True,
                         capture_output=True, text=True, encoding="utf-8").stdout
    return [repo / name for name in out.split("\0") if name]


def read_text(path: Path) -> str | None:
    """None for anything binary — a screenshot's bytes have no words in them."""
    try:
        raw = path.read_bytes()
    except OSError:
        return None
    if b"\0" in raw[:8192]:
        return None
    return raw.decode("utf-8", errors="replace")


def scan_repo(redacted=REDACTED, repo: Path = REPO) -> dict[str, set[str]]:
    offenders = {}
    for path in tracked_files(repo):
        text = read_text(path)
        if text is None:
            continue
        hits = redacted_names_in(text, redacted)
        if hits:
            offenders[path.relative_to(repo).as_posix()] = hits
    return offenders


def test_the_guarded_names_are_all_still_guarded():
    """The way this guard dies is a contributor deleting the digest their line collided
    with. Adding a name means bumping the count here too."""
    assert {length: len(digests) for length, digests in REDACTED.items()} == EXPECTED


def test_no_redacted_name_appears_in_a_tracked_file():
    offenders = scan_repo()
    report = "\n".join(f"  {path}: {', '.join(sorted(hits))}"
                       for path, hits in sorted(offenders.items()))
    assert not offenders, f"redacted names are back in the repo:\n{report}\n{FIX}"


# --- that the guard would actually fire -------------------------------------------------
# Proving it with a real name would mean writing one down, so these plant a made-up one and
# hand the scan a digest table containing only that.

PROBE_NAME = "Umbrella Diagnostics"
PROBE = {len(words(PROBE_NAME)): frozenset({digest(" ".join(words(PROBE_NAME)))})}
PROBE_ONE = {1: frozenset({digest("umbrella")})}


def test_the_scan_finds_a_name_however_it_is_written():
    for written in (PROBE_NAME, PROBE_NAME.upper(), "umbrella-diagnostics",
                    f"Call with {PROBE_NAME} - handover", "umbrella_diagnostics.example.com"):
        assert redacted_names_in(written, PROBE), f"missed the name in {written!r}"


def test_the_scan_leaves_ordinary_prose_alone():
    assert not redacted_names_in("An umbrella is not diagnostics.", PROBE)


def test_a_name_in_a_brand_new_file_is_caught(tmp_path):
    """The scan walks `git ls-files`, so a file nobody has ever cleaned is covered the
    moment it is staged. Proved against a throwaway repo rather than by planting a file in
    this one, so a run leaves the working tree and the index exactly as it found them."""
    subprocess.run(["git", "init", "--quiet", str(tmp_path)], check=True, capture_output=True)
    (tmp_path / "handover.md").write_text(f"Ticket handover for {PROBE_NAME}.\n",
                                          encoding="utf-8")
    subprocess.run(["git", "add", "--all"], cwd=tmp_path, check=True, capture_output=True)
    assert scan_repo(PROBE, tmp_path) == {"handover.md": {PROBE_NAME.lower()}}


def test_a_glued_job_code_still_reaches_the_scan():
    """`ABC2232S` is one word to a naive tokeniser, which is how a real job code slips
    back in beside names that are caught."""
    assert redacted_names_in("Raised UMBRELLA2232S against the case", PROBE_ONE)


if __name__ == "__main__":  # the digest line to paste for a name you want guarded
    import sys
    for name in sys.argv[1:]:
        ws = words(name)
        print(f'        "{digest(" ".join(ws))}",'
              f'   <- into REDACTED[{len(ws)}], then EXPECTED[{len(ws)}] += 1')
