# Stock Research App — Test Runner
# Usage: make test-phase1, make test-phase2, etc.
#
# Venv: C:/Users/Olive/.venvs/stock-research-app  (Python 3.13.3)
# Activate (PowerShell): C:/Users/Olive/.venvs/stock-research-app/Scripts/Activate.ps1
# Activate (bash/cmd):   C:/Users/Olive/.venvs/stock-research-app/Scripts/activate
#
PYTHON = C:/Users/Olive/.venvs/stock-research-app/Scripts/python.exe
PIP    = C:/Users/Olive/.venvs/stock-research-app/Scripts/pip.exe

.PHONY: test test-unit test-phase1 test-phase2 test-phase3 test-phase4 \
        validate-phase1 validate-phase2 validate-phase3 validate-phase4 \
        lint format install fixtures

# ── Install ────────────────────────────────────────────────────────────────────
install:
	$(PIP) install -r requirements.txt
	$(PYTHON) -m pre_commit install

# ── Linting ────────────────────────────────────────────────────────────────────
lint:
	$(PYTHON) -m ruff check backend/

format:
	$(PYTHON) -m black backend/
	$(PYTHON) -m ruff check backend/ --fix

# ── Test suites by phase ───────────────────────────────────────────────────────

# Pure unit tests — no I/O, no API calls, always runnable
test-unit:
	$(PYTHON) -m pytest -m unit -v

# Phase 1: Data layer — validates fetched data shape and cache writes
# Uses fixture data if present; set LIVE_DATA=1 to force real network calls
test-phase1:
	$(PYTHON) -m pytest -m phase1 -v

# Phase 2: Schemas, config, model router — no I/O
test-phase2:
	$(PYTHON) -m pytest -m phase2 -v

# Phase 3: Agent outputs — validates signal schemas against cached fixture data
test-phase3:
	$(PYTHON) -m pytest -m phase3 -v

# Phase 4: LangGraph graph — runs full pipeline against fixtures
# Requires ANTHROPIC_API_KEY set in .env
test-phase4:
	$(PYTHON) -m pytest -m phase4 -v

# Run all tests except phase4 (no API calls)
test:
	$(PYTHON) -m pytest -m "not phase4" -v

# Run everything including live pipeline
test-all:
	$(PYTHON) -m pytest -v

# ── Phase validation commands (mirrors README checkpoints) ─────────────────────

# Validate Phase 1: runs each data module standalone for AAPL
validate-phase1:
	@echo "── price.py ──────────────────────────────────────"
	$(PYTHON) -m backend.data.price AAPL
	@echo "── news.py ───────────────────────────────────────"
	$(PYTHON) -m backend.data.news AAPL
	@echo "── reddit.py ─────────────────────────────────────"
	$(PYTHON) -m backend.data.reddit AAPL
	@echo "── stocktwits.py ─────────────────────────────────"
	$(PYTHON) -m backend.data.stocktwits AAPL
	@echo "✓ Phase 1 standalone validation complete"

# Validate Phase 2: instantiates ModelRouter and checks model assignments
validate-phase2:
	$(PYTHON) -c "\
from backend.core.config import get_config; \
from backend.core.model_router import ModelRouter; \
cfg = get_config(); \
router = ModelRouter(cfg); \
agents = ['fundamental','technical','quant','sector','sentiment','synthesis']; \
[print(f'{a}: {router.get_model(a)}') for a in agents]; \
print('✓ Phase 2 validation complete')"

# Validate Phase 3: runs each agent standalone for AAPL
validate-phase3:
	@echo "── fundamental ───────────────────────────────────"
	$(PYTHON) -m backend.agents.fundamental AAPL
	@echo "── technical ─────────────────────────────────────"
	$(PYTHON) -m backend.agents.technical AAPL
	@echo "── quant ─────────────────────────────────────────"
	$(PYTHON) -m backend.agents.quant AAPL
	@echo "── sector ────────────────────────────────────────"
	$(PYTHON) -m backend.agents.sector AAPL
	@echo "── sentiment ─────────────────────────────────────"
	$(PYTHON) -m backend.agents.sentiment AAPL
	@echo "── synthesis ─────────────────────────────────────"
	$(PYTHON) -m backend.agents.synthesis AAPL
	@echo "✓ Phase 3 standalone validation complete"

# Validate Phase 4: runs full pipeline via run_research
validate-phase4:
	$(PYTHON) -c "\
import asyncio; \
from backend.core.graph import run_research; \
report = asyncio.run(run_research('AAPL')); \
print(report.model_dump_json(indent=2)); \
print('✓ Phase 4 validation complete')"

# ── Fixture generation ─────────────────────────────────────────────────────────
# Populates backend/tests/fixtures/ from real AAPL data
# Run this once after Phase 1 is validated — tests use these fixtures forever
fixtures:
	$(PYTHON) backend/tests/generate_fixtures.py AAPL
	@echo "✓ Fixtures written to backend/tests/fixtures/"
