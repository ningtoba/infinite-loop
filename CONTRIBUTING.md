# Contributing to omp-loop

Thank you for your interest in contributing to omp-loop! This document provides guidelines and workflows for contributing effectively.

## Table of Contents

- [Development Setup](#development-setup)
- [Project Structure](#project-structure)
- [Development Workflow](#development-workflow)
- [Coding Standards](#coding-standards)
- [Testing Guidelines](#testing-guidelines)
- [Commit Conventions](#commit-conventions)
- [Pull Request Process](#pull-request-process)
- [Documentation](#documentation)

---

## Development Setup

### Prerequisites

- **Python 3.10+** (3.10, 3.11, 3.12, 3.13 are tested in CI)
- **Git**

### Clone and Install

```bash
git clone <repo-url>
cd omp-loop

# Install with dev and test dependencies
make install-dev

# Or manually:
pip install -e ".[test,dev]"
```

### Verify Installation

```bash
# Run the test suite (all 480+ tests should pass)
make test

# Run linting
make lint

# Run type checking
make mypy
```

---

## Project Structure

```
omp-loop/
├── omp_loop/              # Core daemon package
│   ├── cli.py            # CLI entry point and argparse setup
│   ├── loop.py           # Main loop engine (~820 lines)
│   ├── config.py         # Constants, paths, defaults, and LoopConfig
│   ├── functions.py      # Goal loading, startup banner, cooldown
│   ├── error_recovery.py # Automatic error recovery with escalation
│   ├── git_utils.py      # Git state capture and auto-commit
│   ├── heartbeat.py      # Session self-healing heartbeat monitor
│   ├── state.py          # Ledger loading/creation/crash recovery
│   ├── file_utils.py     # File I/O, locks, logging, JSON extraction
│   └── ...
├── web_app/              # Web UI server
│   ├── server.py         # FastAPI application and 20+ REST endpoints
│   ├── loop_manager.py   # Loop lifecycle management as subprocess
│   └── static/           # SPA frontend
│       ├── index.html
│       ├── style.css
│       └── app.js
├── tests/                # 25+ test files, 480+ tests
├── pyproject.toml        # Package configuration
├── Makefile              # Development targets
└── README.md
```

---

## Development Workflow

### Typical Development Cycle

1. **Pick a task** from `ENGINEERING_BACKLOG.md`
2. **Create a branch**: `git checkout -b feat/your-feature-name`
3. **Make changes** following coding standards
4. **Run tests**: `make test`
5. **Run linting**: `make lint-all`
6. **Format code**: `make format`
7. **Commit** following commit conventions
8. **Push** and open a Pull Request

### Makefile Targets

```bash
make install       # Install package
make install-dev   # Install with dev/test dependencies
make lint          # Run ruff checks
make format        # Run ruff formatter
make lint-all      # Full CI check: lint + format + mypy
make test          # Run all tests
make mypy          # Run type checker
make update-lock   # Re-generate pip lock files
make verify-lock   # Verify lock files are fresh
make clean         # Remove build artifacts and caches
make web           # Start web UI (production mode)
make web-dev       # Start web UI (development mode with auto-reload)
```

---

## Coding Standards

### Python

- **Formatting**: Ruff with 120-character line length
- **Style**: Follow [PEP 8](https://peps.python.org/pep-0008/) conventions
- **Types**: Use type hints for all function signatures (mypy-checked)
- **Imports**: Group as stdlib → third-party → local, sorted alphabetically
- **Naming**: `snake_case` for functions/variables, `PascalCase` for classes, `UPPER_CASE` for constants

### JavaScript (Web UI)

- **Formatting**: Standard JS conventions, 4-space indentation
- **XSS Prevention**: Always use `escapeHtml()` or `textContent` when inserting user-controlled data into the DOM
- **DOM Manipulation**: Prefer `textContent` + DOM element creation over `innerHTML` when possible

### Violations to Avoid

- Mutable module-level global state (use classes or dependency injection)
- Bare `except` clauses without logging
- Silent `pass` in exception handlers (always log the failure)
- Hardcoded paths (use `config.py` path resolution)
- Magic numbers (use named constants)
- `time.sleep()` in loops that should use event-based waiting

---

## Testing Guidelines

### Running Tests

```bash
# Run all tests
make test

# Run specific test files
python -m pytest tests/test_loop.py -v

# Run smoke tests only (needs external tools like `omp`)
python -m pytest tests/ -m smoke -v

# Run with coverage
python -m pytest tests/ --cov=omp_loop --cov=web_app --cov-report=term-missing
```

### Test Structure

- Tests live in `tests/` and mirror the `omp_loop/` and `web_app/` structure
- Shared fixtures are in `tests/conftest.py`
- Smoke tests (marked `@pytest.mark.smoke`) require external tools like the `omp` binary
- All other tests should be self-contained and not require external dependencies

### Writing Tests

- Use descriptive test names: `test_<function>_<scenario>`
- Test both success and failure paths
- Use `pytest.mark.parametrize` for multiple input variations
- Use `pytest-asyncio` for async test functions
- Mock external calls (subprocess, network) to keep tests fast and deterministic

### Test Conventions

- Tests should not depend on `/tmp/infinite-loop-state.json` or other runtime files
- Use `tmp_path` fixture for temporary file I/O tests
- Set `OMP_LOOP_NO_HYDRATE=1` for tests that interact with `LoopManager` to avoid log file reads

---

## Commit Conventions

We follow [Conventional Commits](https://www.conventionalcommits.org/):

```
<type>(<scope>): <description>

[optional body]
[optional footer]
```

### Types

| Type     | Usage                                          |
|----------|------------------------------------------------|
| `feat`   | New feature                                    |
| `fix`    | Bug fix                                        |
| `docs`   | Documentation only                             |
| `style`  | Formatting, whitespace (no code change)        |
| `refactor` | Code restructuring (no behavior change)      |
| `perf`   | Performance improvement                        |
| `test`   | Adding or fixing tests                         |
| `chore`  | Build, CI, dependencies, tooling               |
| `ci`     | CI/CD configuration changes                    |

### Examples

```
feat(loop): add convergence detection with configurable threshold
fix(server): prevent XSS in iteration log display
docs: add REST API reference to README
refactor(config): split LoopConfig into focused dataclasses
test(loop): add integration test for crash recovery
chore(deps): update fastapi from 0.100.0 to 0.115.0
```

---

## Pull Request Process

1. **Create a branch** from `main` with a descriptive name
2. **Make focused commits** — each commit should represent one logical change
3. **Keep PRs focused** — one feature/bugfix per PR. Large refactors can be split into multiple PRs
4. **Update tests** — add tests for new functionality or bug fixes
5. **Update documentation** — if behavior changes, update `README.md` or add inline docs
6. **Ensure CI passes** — all lint, type-check, and test jobs must pass
7. **Request review** — at least one review is required before merging

### PR Checklist

Before submitting:

- [ ] Code follows coding standards
- [ ] Tests pass (`make test`)
- [ ] Linting passes (`make lint-all`)
- [ ] Formatting is up to date (`make format`)
- [ ] New functions have type hints
- [ ] New features are tested
- [ ] API changes are documented
- [ ] Commit messages follow conventions

---

## Documentation

- **README.md**: User-facing documentation (installation, CLI usage, web UI, security)
- **CONTRIBUTING.md**: This file — developer-facing contribution guide
- **ENGINEERING_BACKLOG.md**: Prioritized list of future work, technical debt, and improvements
- **In-code docstrings**: All public functions and classes should have docstrings describing their purpose, parameters, and return values
- **OpenAPI docs**: The FastAPI server automatically generates OpenAPI documentation at `/docs` when running

When making changes, update relevant documentation in the same commit.
