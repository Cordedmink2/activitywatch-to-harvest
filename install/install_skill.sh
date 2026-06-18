#!/usr/bin/env bash
# Install the daily-timesheet skill into your Claude Code skills folder.
#
# Copies skill/daily-timesheet from this repo to ~/.claude/skills/daily-timesheet.
# Never copies a .env (yours stays local) or __pycache__. Safe to re-run.
#
# Usage: ./install/install_skill.sh [SKILLS_DIR]
set -euo pipefail

SKILLS_DIR="${1:-$HOME/.claude/skills}"

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(dirname "$SCRIPT_DIR")"
SOURCE="$REPO_ROOT/skill/daily-timesheet"
DEST="$SKILLS_DIR/daily-timesheet"

if [ ! -d "$SOURCE" ]; then
  echo "ERROR: cannot find skill source at: $SOURCE" >&2
  exit 1
fi

mkdir -p "$SKILLS_DIR"

echo "Installing daily-timesheet skill..."
echo "  from: $SOURCE"
echo "  to:   $DEST"

if command -v rsync >/dev/null 2>&1; then
  rsync -a --delete --exclude='.env' --exclude='__pycache__' "$SOURCE/" "$DEST/"
else
  rm -rf "$DEST"
  mkdir -p "$DEST"
  # cp then prune the bits we never want to ship
  cp -R "$SOURCE/." "$DEST/"
  rm -f "$DEST/.env"
  find "$DEST" -type d -name '__pycache__' -prune -exec rm -rf {} +
fi

echo "Done. Skill installed to $DEST"
echo
echo "Next steps:"
echo "  1. Scaffold your workspace:  ./install/setup_workspace.sh"
echo "  2. Add your Harvest creds:   cp '$DEST/.env.example' '$DEST/.env' and fill it in"
echo "  3. (Windows only) screenshots: pwsh -File '$DEST/scripts/setup_screenshot_pipeline.ps1'"
