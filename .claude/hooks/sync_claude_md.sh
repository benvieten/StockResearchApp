#!/usr/bin/env bash
# Keeps the ## Current Status section of CLAUDE.md up to date.
# Runs at most once per Claude Code session (PPID-gated) and only when
# there are commits that post-date the last CLAUDE.md update.

set -euo pipefail

# ── Recursion guard ─────────────────────────────────────────────────────────
# If this hook was triggered by a `claude --print` subprocess, the env var
# is already set — exit immediately to prevent an infinite loop.
[ -n "${CLAUDE_SYNC_RUNNING:-}" ] && exit 0

# ── Per-session rate limit ──────────────────────────────────────────────────
# Use the parent Claude Code process PID so this fires at most once per session.
STAMP="/tmp/claude_md_sync_${PPID}"
[ -f "$STAMP" ] && exit 0
touch "$STAMP"

# ── Only run when there's something new to reflect ──────────────────────────
cd "$(git rev-parse --show-toplevel 2>/dev/null)" || exit 0

CLAUDE_MD=".claude/CLAUDE.md"
[ -f "$CLAUDE_MD" ] || exit 0

# Get timestamp of last CLAUDE.md commit
CLAUDE_MD_TS=$(git log -1 --format="%ct" -- "$CLAUDE_MD" 2>/dev/null || echo "0")
# Get timestamp of most recent commit overall
LATEST_TS=$(git log -1 --format="%ct" 2>/dev/null || echo "0")

# If CLAUDE.md is already at the latest commit, nothing to do
[ "$LATEST_TS" -le "$CLAUDE_MD_TS" ] && exit 0

# ── Build context for the LLM ───────────────────────────────────────────────
RECENT_COMMITS=$(git log --oneline -8 2>/dev/null)
TODAY=$(date +%Y-%m-%d)

PROMPT="You are maintaining a concise engineering reference file.

Update ONLY the '## Current Status' section in .claude/CLAUDE.md.

Rules — follow every one:
- Set the date in the section heading to: $TODAY
- Update 'What's Built' to reflect any new features visible in recent commits (add new bullets, remove stale ones)
- Update 'Pending' list — mark anything that appears done in commits, add new tasks if obvious from the code
- Do NOT touch any other section of the file
- The entire Current Status section must stay under 55 lines
- One line per item — no nested sub-bullets unless already there
- If nothing meaningful changed, just update the date and exit

Recent commits for context:
$RECENT_COMMITS"

# ── Run the update ───────────────────────────────────────────────────────────
export CLAUDE_SYNC_RUNNING=1
claude --print \
  --allowedTools "Read,Edit" \
  --max-turns 4 \
  "$PROMPT" 2>/dev/null || true
