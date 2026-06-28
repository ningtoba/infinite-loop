.PHONY: install lint format clean help

PYTHON := python3

help:
	@echo "━━━ pi-loop — Makefile ━━━"
	@echo ""
	@echo "USAGE:  make <target>"
	@echo ""
	@echo "TARGETS:"
	@echo "  install      Install pi-loop as a system command via pip install -e ."
	@echo "  lint         Run ruff check on pi_loop/"
	@echo "  format       Run ruff format on pi_loop/"
	@echo "  clean        Remove build artifacts, cache, and temp files"
	@echo ""

install:
	pip install -e .

lint:
	ruff check pi_loop/

format:
	ruff format pi_loop/

clean:
	rm -rf build/ dist/ *.egg-info __pycache__/ .ruff_cache/
	find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true
	find . -type f -name '*.pyc' -delete
	rm -f /tmp/infinite-loop-state.json /tmp/infinite-loop-stop /tmp/infinite-loop.log
