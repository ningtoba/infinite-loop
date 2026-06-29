.PHONY: install install-dev lint format test lint-all mypy pre-commit pre-commit-run clean help web web-dev update-lock verify-lock

PYTHON := python3

help:
	@echo "━━━ pi-loop — Makefile ━━━"
	@echo ""
	@echo "USAGE:  make <target>"
	@echo ""
	@echo "TARGETS:"
	@echo "  install       Install pi-loop as a system command via pip install -e ."
	@echo "  install-dev   Install with dev/test dependencies"
	@echo "  update-lock   Re-generate requirements.txt + requirements-dev.txt"
	@echo "  verify-lock   Verify lock files are up to date with pyproject.toml"
	@echo "  lint          Run ruff check on pi_loop/ and web_app/"
	@echo "  format        Run ruff format (in-place) on pi_loop/ and web_app/"
	@echo "  lint-all      Full CI check: lint + format check (no write)"
	@echo "  test          Run tests with pytest (verbose)"
	@echo "  pre-commit    Install pre-commit hooks"
	@echo "  web           Start the web UI server (production mode)"
	@echo "  web-dev       Start the web UI server with auto-reload"
	@echo "  clean         Remove build artifacts, cache, and temp files"
	@echo ""

install:
	pip install -e . 2>/dev/null || pip install -e . --break-system-packages

install-dev:
	pip install -e ".[test,dev]" 2>/dev/null || pip install -e ".[test,dev]" --break-system-packages

update-lock:
	pip install pip-tools 2>/dev/null || pip install pip-tools --break-system-packages
	pip-compile pyproject.toml --output-file requirements.txt --quiet --strip-extras
	pip-compile pyproject.toml --output-file requirements-dev.txt --extra test --extra dev --quiet --strip-extras

verify-lock:
	pip install pip-tools 2>/dev/null || pip install pip-tools --break-system-packages
	pip-compile pyproject.toml --output-file /tmp/pi-loop-reqs.txt --quiet --strip-extras
	pip-compile pyproject.toml --output-file /tmp/pi-loop-reqs-dev.txt --extra test --extra dev --quiet --strip-extras
	cmp requirements.txt /tmp/pi-loop-reqs.txt || { echo "LOCK OUTDATED: re-run 'make update-lock'"; exit 1; }
	cmp requirements-dev.txt /tmp/pi-loop-reqs-dev.txt || { echo "LOCK OUTDATED: re-run 'make update-lock'"; exit 1; }
	rm -f /tmp/pi-loop-reqs.txt /tmp/pi-loop-reqs-dev.txt

lint:
	ruff check pi_loop/ web_app/

format:
	ruff format pi_loop/ web_app/

lint-all:
	ruff check pi_loop/ web_app/
	ruff format --check pi_loop/ web_app/
	mypy pi_loop/ --ignore-missing-imports --warn-unused-configs 2>/dev/null; true

test:
	python -m pytest tests/ -v

mypy:
	python -m mypy pi_loop/ --ignore-missing-imports --warn-unused-configs 2>/dev/null; true

pre-commit:
	pip install pre-commit
	pre-commit install
	@echo "pre-commit hooks installed."

pre-commit-run:
	pre-commit run --all-files

web:
	pip install -e .
	pi-loop-web

web-dev:
	pip install -e .
	pi-loop-web --reload

clean:
	rm -rf build/ dist/ *.egg-info .ruff_cache/ .pytest_cache/ .mypy_cache/
	find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true
	find . -type d -name '*.egg-info' -exec rm -rf {} + 2>/dev/null || true
	find . -type f -name '*.pyc' -delete
	find . -type d -name '.hypa' -exec rm -rf {} + 2>/dev/null || true
	find . -type d -name '.benchmarks' -exec rm -rf {} + 2>/dev/null || true
	rm -f /tmp/infinite-loop-state.json /tmp/infinite-loop-stop /tmp/infinite-loop.log
