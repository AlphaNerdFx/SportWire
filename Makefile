# SportWire task runner.
#
# The point of a Makefile here is that CI and a human run the *same commands*. If CI runs
# `pytest --some --flags` and you run plain `pytest`, then "works on my machine" and "passes
# in CI" stop meaning the same thing. `make check` is the single definition of "is this
# code acceptable", used by both.

PYTHON := .venv/bin/python
PIP    := .venv/bin/pip
RUFF   := .venv/bin/ruff

.PHONY: help venv install lint format test check run dry-run clean

help:  ## Show this help
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) \
		| awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-12s\033[0m %s\n", $$1, $$2}'

venv:  ## Create the virtual environment
	python3 -m venv .venv

install: venv  ## Install runtime and development dependencies
	$(PIP) install --quiet --upgrade pip
	$(PIP) install --quiet -e ".[dev]"

lint:  ## Check formatting and lint rules without changing anything
	$(RUFF) format --check .
	$(RUFF) check .

format:  ## Apply formatting and safe lint fixes
	$(RUFF) format .
	$(RUFF) check --fix .

test:  ## Run the test suite (network tests excluded by default)
	$(PYTHON) -m pytest -v

check: lint test  ## Everything CI runs. Green here means green there.

run:  ## Fetch and send a brief
	$(PYTHON) main.py

dry-run:  ## Fetch and print a brief without sending or recording anything
	$(PYTHON) main.py --dry-run

clean:  ## Remove caches and the local database
	rm -rf .pytest_cache .ruff_cache
	find . -type d -name __pycache__ -not -path "./.venv/*" -exec rm -rf {} +
	rm -f sportwire.db
