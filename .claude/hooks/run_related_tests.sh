#!/usr/bin/env bash
# Run the relevant pytest suite whenever a backend Python file is edited.
# On failure, injects test output into Claude's context as additionalContext
# so failures surface immediately without requiring a manual test run.
#
# Claude Code PostToolUse hook — receives JSON on stdin.

FILE=$(jq -r '.tool_input.file_path // ""' 2>/dev/null)

[[ "$FILE" == *.py ]] || exit 0

PROJECT_ROOT="/Users/benvieten/Desktop/StockResearch/StockResearchApp"
cd "$PROJECT_ROOT" || exit 0

# Map edited file → most relevant test module
case "$FILE" in
  *backend/core/data_models.py)
    TEST="backend/tests/phase2/test_data_models.py"
    ;;
  *backend/agents/fundamental.py)
    TEST="backend/tests/phase3/test_fundamental_math.py"
    ;;
  *backend/agents/quant.py)
    TEST="backend/tests/phase3/test_quant_math.py"
    ;;
  *backend/agents/sentiment.py)
    TEST="backend/tests/phase3/test_sentiment_heuristics.py"
    ;;
  *backend/agents/technical.py)
    TEST="backend/tests/phase3/test_technical_indicators.py"
    ;;
  *backend/agents/synthesis.py | *backend/core/graph.py)
    TEST="backend/tests/phase4/test_graph.py"
    ;;
  *)
    exit 0
    ;;
esac

source .venv/bin/activate 2>/dev/null
OUTPUT=$(python -m pytest "$TEST" -q --tb=short --no-header 2>&1)
EXIT_CODE=$?

if [[ $EXIT_CODE -ne 0 ]]; then
  # Inject failures into Claude's context so they're visible immediately
  python3 -c "
import json, sys
msg = 'TEST FAILURES after editing ' + sys.argv[2] + ':\n\n' + sys.argv[1]
print(json.dumps({
    'hookSpecificOutput': {
        'hookEventName': 'PostToolUse',
        'additionalContext': msg
    }
}))
" "$OUTPUT" "$FILE"
fi
