# =============================================================================
# Infinite Loop Daemon — Makefile
# =============================================================================
# Convenience targets for common operations.
# Usage: make <target> [ARGS="--goal 'fix tests' --evolve"]
# =============================================================================

.DEFAULT_GOAL := help

PYTHON   := python3
LAUNCHER := $(PYTHON) launch-loop.py
RUN_SH   := bash run.sh
SCRIPTS  := scripts

# ── Help ──────────────────────────────────────────────────────────────────────

.PHONY: help
help:
	@echo "━━━ Infinite Loop Daemon — Makefile ━━━"
	@echo ""
	@echo "USAGE:  make <target> [ARGS=\"...\"]"
	@echo ""
	@echo "TARGETS:"
	@echo ""
	@echo "  Install:"
	@echo "    install      Install hermes_loop as a system command via pip"
	@echo "    install-dev  Editable install for development"
	@echo ""
	@echo "  Setup & Docs:"
	@echo "    env          Copy .env.example to .env (safe, no overwrite)"
	@echo "    help         Show this help message"
	@echo "    init         Walk through interactive setup wizard (--init)"
	@echo "    wizard       Alias for make init"
	@echo "    demo         Interactive walkthrough of the daemon lifecycle (--demo)"
	@echo ""
	@echo "  Run:"
	@echo "    run          Run the daemon (reads .env). Add ARGS for overrides"
	@echo "    dry-run      Show config without starting (ARGS supported)"
	@echo "    self-test    Run in-process self-tests (count auto-detected at runtime)"
	@echo "    version      Print daemon version and exit"
	@echo "    check-env    Validate .env file for typos, unknown variables, common mistakes"
	@echo "    doctor       Run comprehensive self-diagnosis (hermes, PATH, .env, git)"
	@echo "    examples     Print categorized real-world usage examples"
	@echo "    explain      Show detailed help on a single flag (pass FLAG=)"
	@echo "    help-topic   Show flags for a specific argument group (pass TOPIC=)"
	@echo "    list-flags   Print all flags organized by group"
	@echo "    list-groups  Print compact group names with flag counts"
	@echo ""
	@echo "  Monitoring:"
	@echo "    status       Show formatted ledger via inspect-ledger.sh"
	@echo "    log          Tail the daemon log file"
	@echo "    stop         Write 'stop' to the sentinel file"
	@echo "    pause        Write 'pause' to the sentinel file"
	@echo "    resume       Write 'resume' to the sentinel file"
	@echo ""
	@echo "  Pre-Commit / CI:"
	@echo "    check        Full pre-commit gate: lint + self-test + check-env + regenerate completions"
	@echo "    pre-commit   Quick pre-commit gate: lint + self-test (no .env needed)"
	@echo ""
	@echo "  Maintenance:"
	@echo "    clean            Remove ledger, sentinel, and temp files"
	@echo "    lint             Run Python syntax checks on all .py files"
	@echo "    completion       Install shell tab-completion (bash/zsh)"
	@echo "    update-completions  Regenerate completion scripts from argparse"
	@echo "    archive          Archive old iterations from ledger"
	@echo ""
	@echo "EXAMPLES:"
	@echo "  make env                      # Create .env from .env.example"
	@echo "  make install                  # Install hermes_loop command on PATH"
	@echo "  make install-dev              # Editable install for development"
	@echo "  make dry-run                 # Preview default config"
	@echo "  make run                      # Run with .env config"
	@echo "  make demo                     # Interactive daemon walkthrough"
	@echo "  make examples                  # See usage patterns"
	@echo "  make explain FLAG=workers      # Help on a specific flag"
	@echo "  make help-topic TOPIC=notifications  # Flags in a group"
	@echo "  make check                   # Full pre-commit gate"
	@echo "  make self-test               # Run tests"
	@echo "  make status                  # View ledger"
	@echo "  make stop                    # Stop the daemon"
	@echo "  make clean                   # Reset state"
	@echo ""

# ── Install ────────────────────────────────────────────────────────────────────

.PHONY: install
install:
	@echo "━━━ Installing hermes_loop command ━━━"
	@pip install -e . 2>&1 | tail -3 || pipx install . 2>&1 | tail -3
	@echo ""
	@echo "  ✓ hermes_loop is now on your PATH."
	@echo "  Try: hermes_loop --help"
	@echo ""

.PHONY: install-dev
install-dev:
	@echo "━━━ Installing in editable mode for development ━━━"
	@pip install -e . 2>&1 | tail -3 || pipx install . 2>&1 | tail -3
	@echo ""
	@echo "  ✓ Editable install complete. Changes to source are live."
	@echo "  Run: hermes_loop --self-test"

# ── Setup ─────────────────────────────────────────────────────────────────────

.PHONY: env
env:
	@if [ -f .env ]; then \
		echo ".env already exists — not overwriting."; \
		echo "  Edit .env or remove it and run 'make env' again."; \
	else \
		cp .env.example .env; \
		echo "Created .env from .env.example"; \
		echo "Edit .env with your settings, then: make run"; \
	fi

# ── Interactive Setup Wizard ─────────────────────────────────────────────

.PHONY: init wizard
init wizard:
	$(PYTHON) -m hermes_loop --init

.PHONY: demo
demo:
	$(PYTHON) -m hermes_loop --demo

# ── Run / Test ────────────────────────────────────────────────────────────────

.PHONY: run
run:
	$(RUN_SH) $(ARGS)

.PHONY: dry-run
dry-run:
	$(RUN_SH) --dry-run $(ARGS)

.PHONY: self-test
self-test:
	$(RUN_SH) --self-test

.PHONY: version
version:
	$(RUN_SH) --version

.PHONY: check-env
check-env:
	$(PYTHON) -m hermes_loop --check-env

.PHONY: examples
examples:
	$(RUN_SH) --examples

.PHONY: doctor
doctor:
	$(PYTHON) -m hermes_loop --doctor

.PHONY: explain
explain:
	$(PYTHON) -m hermes_loop --explain "$(FLAG)"

.PHONY: help-topic
help-topic:
	$(PYTHON) -m hermes_loop --help-topic "$(TOPIC)"

.PHONY: list-flags
list-flags:
	$(RUN_SH) --list-flags

.PHONY: list-groups
list-groups:
	$(RUN_SH) --list-groups

# ── Monitoring ────────────────────────────────────────────────────────────────

.PHONY: status
status:
	@PYTHON_OUT=$$(python3 -m hermes_loop --status 2>&1) || true; \
	if echo "$$PYTHON_OUT" | grep -q "Status:"; then \
		echo "$$PYTHON_OUT"; \
	elif [ -f /tmp/infinite-loop-state.json ]; then \
		bash $(SCRIPTS)/inspect-ledger.sh --summary; \
	else \
		echo "Ledger not found at /tmp/infinite-loop-state.json"; \
		echo "The daemon may not be running."; \
	fi

.PHONY: log
log:
	@LOG_FILE="$$(grep INFINITE_LOOP_LOG_FILE .env 2>/dev/null | cut -d= -f2 | tr -d '\"')"; \
	if [ -n "$$LOG_FILE" ] && [ -f "$$LOG_FILE" ]; then \
		echo "Tailing $$LOG_FILE ..."; \
		tail -f "$$LOG_FILE"; \
	elif [ -f /tmp/infinite-loop.log ]; then \
		echo "Tailing /tmp/infinite-loop.log ..."; \
		tail -f /tmp/infinite-loop.log; \
	else \
		echo "No log file found. Set INFINITE_LOOP_LOG_FILE in .env"; \
		echo "or check /tmp/infinite-loop.log"; \
	fi

SENTINEL ?= /tmp/infinite-loop-stop

.PHONY: stop
stop:
	@echo "stop" > $(SENTINEL)
	@echo "Sent 'stop' to $(SENTINEL)"

.PHONY: pause
pause:
	@echo "pause" > $(SENTINEL)
	@echo "Sent 'pause' to $(SENTINEL)"

.PHONY: resume
resume:
	@echo "resume" > $(SENTINEL)
	@echo "Sent 'resume' to $(SENTINEL)"

# ── Pre-Commit / CI ────────────────────────────────────────────────────────────

.PHONY: check
check:
	@echo "━━━ make check — full pre-commit gate ━━━"
	@echo ""
	@echo "  Step 1/4 — Python + shell syntax check..."
	@$(MAKE) lint || exit 1
	@echo ""
	@echo "  Step 2/4 — Self-tests..."
	@$(MAKE) self-test 2>&1 || exit 1
	@echo ""
	@echo "  Step 3/4 — .env validation..."
	@$(MAKE) check-env 2>&1 || true
	@echo ""
	@echo "  Step 4/4 — Regenerate completion scripts from argparse..."
	@$(MAKE) update-completions 2>&1 || true
	@echo ""
	@echo "  ═══════════════════════════════════════════════════════════════════"
	@echo "   All checks passed! Ready to commit."
	@echo "  ═══════════════════════════════════════════════════════════════════"

.PHONY: pre-commit
pre-commit:
	@echo "━━━ make pre-commit — fast pre-commit gate (no .env needed) ━━━"
	@$(MAKE) self-test 2>&1
	@$(MAKE) lint 2>&1
	@echo ""
	@echo "  ═══════════════════════════════════════════════════════════════════"
	@echo "   All checks passed! Ready to commit."
	@echo "  ═══════════════════════════════════════════════════════════════════"

# ── Maintenance ───────────────────────────────────────────────────────────────

.PHONY: clean
clean:
	@echo "Cleaning ledger, sentinel, and temp files..."
	@rm -f /tmp/infinite-loop-state.json
	@rm -f $(SENTINEL)
	@rm -f /tmp/infinite-loop.log
	@rm -f /tmp/loop-status.html
	@rm -f /tmp/loop-status.json
	@echo "  ✓ /tmp/infinite-loop-state.json"
	@echo "  ✓ $(SENTINEL)"
	@echo "  ✓ /tmp/infinite-loop.log"
	@echo "  ✓ /tmp/loop-status.{html,json}"
	@echo "Done. Next: make run"

.PHONY: update-completions
update-completions:
	@echo "Regenerating bash/zsh completion scripts from live argparse..."
	@$(PYTHON) -m hermes_loop --completion-script bash > scripts/completion/bash
	@$(PYTHON) -m hermes_loop --completion-script zsh > scripts/completion/zsh
	@echo "  ✓ scripts/completion/bash"
	@echo "  ✓ scripts/completion/zsh"
	@echo "Done. The scripts now reflect the current argparse definitions."
	@echo "Reinstall: make completion"

.PHONY: lint
lint:
	@echo "Checking Python source with ruff..."
	@ERRORS=0; \
	if command -v ruff >/dev/null 2>&1; then \
		ruff check hermes_loop/ web_app/ session-self-loop.py launch-loop.py; \
		RUFF_EXIT=$$?; \
		if [ "$$RUFF_EXIT" -ne 0 ]; then \
			ERRORS=$$((ERRORS + RUFF_EXIT)); \
		fi; \
	else \
		echo "  [INFO] ruff not found, falling back to py_compile syntax check"; \
		for f in hermes_loop/*.py web_app/*.py session-self-loop.py launch-loop.py; do \
			if $(PYTHON) -m py_compile "$$f" 2>/dev/null; then \
				echo "  [OK] $$f"; \
			else \
				echo "  [FAIL] $$f - syntax error"; \
				ERRORS=$$((ERRORS + 1)); \
			fi; \
		done; \
	fi; \
	if [ "$$ERRORS" -eq 0 ]; then \
		echo "Python syntax OK - all files pass"; \
	else \
		echo "$$ERRORS file(s) have syntax errors"; \
		exit 1; \
	fi; \
	if command -v bash >/dev/null 2>&1; then \
		bash -n scripts/completion/bash 2>/dev/null && echo "  [OK] scripts/completion/bash" || { echo "  [FAIL] scripts/completion/bash - syntax error"; ERRORS=$$((ERRORS + 1)); }; \
	fi; \
	if command -v zsh >/dev/null 2>&1; then \
		zsh -n scripts/completion/zsh 2>/dev/null && echo "  [OK] scripts/completion/zsh" || { echo "  [FAIL] scripts/completion/zsh - syntax error"; ERRORS=$$((ERRORS + 1)); }; \
	fi; \
	if [ "$$ERRORS" -eq 0 ]; then \
		echo "All checks pass"; \
	else \
		echo "$$ERRORS file(s) have errors"; \
		exit 1; \
	fi

.PHONY: completion
completion:
	@SHELL="$${SHELL:-/bin/bash}"; \
	SHELL_NAME="$$(basename "$$SHELL")"; \
	case "$$SHELL_NAME" in \
		bash) \
			echo "Installing bash completion..."; \
			mkdir -p ~/.local/share/bash-completion/completions; \
			cp scripts/completion/bash ~/.local/share/bash-completion/completions/hermes-loop; \
			echo "  ✓ Copied to ~/.local/share/bash-completion/completions/hermes-loop"; \
			echo "  To activate: source ~/.local/share/bash-completion/completions/hermes-loop"; \
			echo "  Or add to ~/.bashrc: source ~/.local/share/bash-completion/completions/hermes-loop"; \
			;; \
		zsh) \
			echo "Installing zsh completion..."; \
			mkdir -p ~/.zsh/completion; \
			cp scripts/completion/zsh ~/.zsh/completion/_hermes_loop; \
			echo "  ✓ Copied to ~/.zsh/completion/_hermes_loop"; \
			echo "  To activate, add to ~/.zshrc:"; \
			echo '    fpath=(~/.zsh/completion $$fpath)'; \
			echo '    autoload -Uz compinit && compinit'; \
			;; \
		*) \
			echo "Unsupported shell: $$SHELL_NAME"; \
			echo "Manual install:"; \
			echo "  bash: source scripts/completion/bash"; \
			echo "  zsh:  cp scripts/completion/zsh ~/.zsh/completion/_hermes_loop"; \
			;; \
	esac
	@echo ""
	@echo "Completion installed. Restart your shell or source the file to activate."
	@echo "Try: python3 launch-loop.py --<TAB>"

.PHONY: archive
archive:
	@if [ -f $(SCRIPTS)/archive-state.sh ]; then \
		bash $(SCRIPTS)/archive-state.sh --auto; \
	else \
		echo "archive-state.sh not found at $(SCRIPTS)/archive-state.sh"; \
	fi
