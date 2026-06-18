#!/usr/bin/env bash
# Scaffold a workspace for the daily-timesheet skill.
#
# Creates Timesheets/, daily_exports/, .mcp/ in the chosen workspace and seeds
# Timesheets/.context.md from the bundled template if it doesn't already exist.
# Never overwrites an existing .context.md.
#
# Usage: ./install/setup_workspace.sh [WORKSPACE]   (defaults to current directory)
set -euo pipefail

WORKSPACE="${1:-$(pwd)}"

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(dirname "$SCRIPT_DIR")"
TEMPLATE="$REPO_ROOT/skill/daily-timesheet/references/context.md.example"

echo "Scaffolding workspace at: $WORKSPACE"

for d in Timesheets daily_exports .mcp; do
  mkdir -p "$WORKSPACE/$d"
  echo "  created  $d/"
done

CONTEXT_DEST="$WORKSPACE/Timesheets/.context.md"
if [ -f "$CONTEXT_DEST" ]; then
  echo "  kept     Timesheets/.context.md (already exists — not overwritten)"
elif [ -f "$TEMPLATE" ]; then
  cp "$TEMPLATE" "$CONTEXT_DEST"
  echo "  seeded   Timesheets/.context.md (from template — edit it next)"
else
  echo "  WARNING  template not found at $TEMPLATE; create Timesheets/.context.md by hand"
fi

echo
echo "Done. Now open Timesheets/.context.md and fill in your clients, colleagues,"
echo "ticket prefixes, timezone, and billing style. See the README for a walkthrough."
