# Developer tasks for voicebench. Run `make` to list them.
PYTHON ?= python3
VENV ?= .venv
BIN := $(VENV)/bin

.DEFAULT_GOAL := help
.PHONY: help setup lint fmt typecheck test test-all cov bench build exe image docs docs-serve clean

help: ## List the available targets
	@awk 'BEGIN {FS = ":.*## "} /^[a-zA-Z_-]+:.*## / {printf "  %-12s %s\n", $$1, $$2}' $(MAKEFILE_LIST)

setup: ## Create .venv and install the package with the dev and docs extras
	$(PYTHON) -m venv $(VENV)
	$(BIN)/python -m pip install --upgrade pip
	$(BIN)/python -m pip install -e ".[dev,docs]"

lint: ## Run the linters (ruff check and ruff format --check)
	$(BIN)/ruff check .
	$(BIN)/ruff format --check .

fmt: ## Format the code and apply safe lint fixes
	$(BIN)/ruff format .
	$(BIN)/ruff check --fix .

typecheck: ## Run mypy in strict mode
	$(BIN)/mypy

test: ## Run the fast test suite (skips realtime and benchmark tests)
	$(BIN)/pytest -m "not realtime"

test-all: ## Run every test, including realtime tests, with coverage
	$(BIN)/pytest --cov --cov-report=term

bench: ## Run the benchmarks and compare against the committed baseline
	$(BIN)/python scripts/bench_check.py

build: ## Build the wheel and sdist into dist/
	$(BIN)/python -m pip install build
	$(BIN)/python -m build

exe: ## Build the standalone executable into dist/voicebench
	$(BIN)/python -m pip install pyinstaller
	$(BIN)/pyinstaller --noconfirm --clean packaging/voicebench.spec

image: ## Build the container image as voicebench:dev
	docker build -t voicebench:dev .

docs: ## Build the documentation site into site/
	$(BIN)/mkdocs build --strict

docs-serve: ## Serve the documentation site with live reload
	$(BIN)/mkdocs serve

clean: ## Remove build outputs and caches
	rm -rf build dist site .coverage coverage.xml .pytest_cache .mypy_cache .ruff_cache .benchmarks voicebench-results
