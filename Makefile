.PHONY: install install-dev lint format test lint-all pre-commit clean help web web-dev

PYTHON := python3

help:
	@echo "━━━ pi-loop — Makefile ━━━"
	@echo ""
	@echo "USAGE:  make <target>"
	@echo ""
	@echo "TARGETS:"
	@echo "  install       Install pi-loop as a system command via pip install -e ."
	@echo "  install-dev   Install with dev/test dependencies"
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
	pip install -e .

install-dev:
	pip install -e ".[test]"

lint:
	ruff check pi_loop/ web_app/

format:
	ruff format pi_loop/ web_app/

lint-all:
	ruff check pi_loop/ web_app/
	ruff format --check pi_loop/ web_app/

test:
	pip install -e ".[test]"
	python -m pytest tests/ -v

pre-commit:
	pip install pre-commit
	pre-commit install

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
