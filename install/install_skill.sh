#!/usr/bin/env bash
# Generate the shared Agent Skills export from this plugin.
#
# This script finds an interpreter and hands over to export_agent_skills.py, which is
# where the export and its rules are documented. It does nothing else: the plugin is
# installed with /plugin install, and a second install path that could drift from it is
# exactly what the export replaces.
#
# Usage: ./install/install_skill.sh [SKILLS_DIR]     # default: ~/.agents/skills
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
EXPORT="$SCRIPT_DIR/export_agent_skills.py"
# Read once, not passed through as "$@": bash before 4.4 — which is what macOS still
# ships — treats "$@" as unset under `set -u`, so the documented no-argument invocation
# would abort. Blank counts as unset, the same as everywhere else in this skill.
DEST="${1:-}"

# `py` last: it is the Windows launcher, and this script also runs under Git Bash, where
# `python` is often a stub the probe below rejects.
for candidate in python3 python py; do
  # Probed, not just found: a `python` that exists on PATH and cannot run is the usual
  # Windows story, and selecting on existence picks it.
  if command -v "$candidate" >/dev/null 2>&1 && "$candidate" -c "import sys" >/dev/null 2>&1; then
    if [ -n "$DEST" ]; then
      exec "$candidate" "$EXPORT" "$DEST"
    fi
    exec "$candidate" "$EXPORT"
  fi
done

echo "ERROR: no usable Python on PATH. The export needs Python 3.10 or newer." >&2
exit 1
