.PHONY: install install-dev lint format test test-ci test-simple lint-all mypy security pre-commit pre-commit-run clean help web web-dev update-lock verify-lock

PYTHON := $(shell command -v python3 2>/dev/null || command -v python 2>/dev/null || echo python3)

help:
	@echo "━━━ omp-loop — Makefile ━━━"
	@echo ""
	@echo "USAGE:  make <target>"
	@echo ""
	@echo "TARGETS:"
	@echo "  install       Install omp-loop as a system command via pip install -e ."
	@echo "  install-dev   Install with dev/test dependencies"
	@echo "  update-lock   Re-generate requirements.txt + requirements-dev.txt"
	@echo "  verify-lock   Verify lock files are up to date with pyproject.toml"
	@echo "  lint          Run ruff check on omp_loop/ and web_app/"
	@echo "  format        Run ruff format (in-place) on omp_loop/ and web_app/"
	@echo "  lint-all      Full CI check: lint + format check (no write)"
	@echo "  security      Run security scanning (bandit + safety)"
	@echo "  test          Run tests with pytest (verbose + coverage)"
	@echo "  test-simple   Run tests with pytest only - no coverage"
	@echo "  test-ci       Run tests with coverage + XML report (for CI)"
	@echo "  pre-commit    Install pre-commit hooks"
	@echo "  web           Start the web UI server (production mode)"
	@echo "  web-dev       Start the web UI server with auto-reload"
	@echo "  clean         Remove build artifacts, cache, and temp files"
	@echo ""

install:
	$(PYTHON) -m pip install -e . 2>/dev/null || $(PYTHON) -m pip install -e . --break-system-packages

install-dev:
	$(PYTHON) -m pip install -e ".[test,dev]" 2>/dev/null || $(PYTHON) -m pip install -e ".[test,dev]" --break-system-packages

update-lock:
	$(PYTHON) -m pip install pip-tools 2>/dev/null || $(PYTHON) -m pip install pip-tools --break-system-packages
	pip-compile pyproject.toml --output-file requirements.txt --quiet --strip-extras
	pip-compile pyproject.toml --output-file requirements-dev.txt --extra test --extra dev --quiet --strip-extras

verify-lock:
	$(PYTHON) -m pip install pip-tools 2>/dev/null || $(PYTHON) -m pip install pip-tools --break-system-packages
	pip-compile pyproject.toml --output-file /tmp/omp-loop-reqs.txt --quiet --strip-extras
	pip-compile pyproject.toml --output-file /tmp/omp-loop-reqs-dev.txt --extra test --extra dev --quiet --strip-extras
	cmp requirements.txt /tmp/omp-loop-reqs.txt || { echo "LOCK OUTDATED: re-run 'make update-lock'"; exit 1; }
	cmp requirements-dev.txt /tmp/omp-loop-reqs-dev.txt || { echo "LOCK OUTDATED: re-run 'make update-lock'"; exit 1; }
	rm -f /tmp/omp-loop-reqs.txt /tmp/omp-loop-reqs-dev.txt

lint:
	ruff check omp_loop/ web_app/

format:
	ruff format omp_loop/ web_app/

lint-all:
	ruff check omp_loop/ web_app/
	ruff format --check omp_loop/ web_app/
	$(PYTHON) -m mypy omp_loop/ web_app/ --ignore-missing-imports --warn-unused-configs

security:
	bandit -r omp_loop/ web_app/ -f json -o bandit-report.json
	safety scan --continue-on-error --file requirements.txt --file requirements-dev.txt

test:
	$(PYTHON) -m pytest tests/ -v --cov=omp_loop --cov=web_app --cov-report=term-missing

test-ci:
	$(PYTHON) -m pytest tests/ -v --cov=omp_loop --cov=web_app --cov-report=term-missing --cov-report=xml:coverage.xml

test-simple:
	$(PYTHON) -m pytest tests/ -v

mypy:
	$(PYTHON) -m mypy omp_loop/ web_app/ --ignore-missing-imports --warn-unused-configs

pre-commit:
	$(PYTHON) -m pip install pre-commit
	pre-commit install
	@echo "pre-commit hooks installed."

pre-commit-run:
	pre-commit run --all-files

web:
	$(PYTHON) -m pip install -e .
	omp-loop-web

web-dev:
	$(PYTHON) -m pip install -e .
	omp-loop-web --reload

clean:
	rm -rf build/ dist/ *.egg-info .ruff_cache/ .pytest_cache/ .mypy_cache/
	find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true
	find . -type d -name '*.egg-info' -exec rm -rf {} + 2>/dev/null || true
	find . -type f -name '*.pyc' -delete
	find . -type d -name '.hypa' -exec rm -rf {} + 2>/dev/null || true
	find . -type d -name '.benchmarks' -exec rm -rf {} + 2>/dev/null || true
	rm -f /tmp/infinite-loop-state.json /tmp/infinite-loop-stop /tmp/infinite-loop.log
