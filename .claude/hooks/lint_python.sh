#!/usr/bin/env bash
# Auto-lint Python files after Claude writes/edits them.
# Claude Code PostToolUse hook — runs in project root.

FILE=$(echo "$CLAUDE_TOOL_INPUT" | python3 -c "import sys,json; d=json.load(sys.stdin); print(d.get('file_path',''))" 2>/dev/null)

if [[ "$FILE" == *.py ]]; then
  black "$FILE" --quiet 2>/dev/null
  ruff check "$FILE" --fix --quiet 2>/dev/null
fi
