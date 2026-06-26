# Changelog

All notable changes to the **Infinite Loop Daemon** project are documented here.

---

## [14.23.0] — 2026-06-26

### Added
- **`--init` / `--wizard` flag**: New interactive setup wizard that walks first-time
  users through the most common configuration options step by step and generates a
  `.env` file. Covers: goal/goals-file, workers (parallelism), git integration
  (git, git-commit, store-git-diff), evolve mode, max iterations, notifications
  (desktop, ntfy, Pushbullet), quiet mode, and output path. Pre-argparse — no
  `--goal` required. Example: `hermes_loop --init` or `make init`.
- **`make init` / `make wizard` target**: New Makefile targets that launch the
  interactive setup wizard. Example: `make init`.

### Changed
- `hermes_loop/wizard.py` — **New module** (313 lines). Contains `run_wizard()`
  with 8-step interactive questionnaire, `.env` writer that preserves existing
  non-daemon variables, and CLI-flag fallback instructions for users who skip
  file saving.
- `hermes_loop/cli.py` — Added `--init` and `--wizard` pre-argparse handlers,
  introspection flags, argparse group definitions, standalone flags set, and
  `--init` hint in the `--goal` missing error message. Added wizard entry to
  `--examples` output (Help & Diagnostics section).
- `hermes_loop/config.py` — Bumped `LAUNCH_LOOP_VERSION` from 14.22.0 to 14.23.0.
- `Makefile` — Added `init`/`wizard` targets and help section entries.

---

## [14.22.0] — 2026-06-26

### Added
- **`make check` target**: New `make check` full pre-commit gate that runs
  `lint` + `self-test` + `check-env` + `update-completions` in sequence with
  clear step-by-step output. Exits on the first failure for fast feedback.
  Example: `make check` before every commit.
- **`make pre-commit` target**: Quick pre-commit gate that runs `self-test` +
  `lint` in sequence. No `.env` file needed — works in any state.
  Example: `make pre-commit` for a fast syntax + test check.

### Changed
- `Makefile` — Added `check` and `pre-commit` targets, updated `help` section
  with a new "Pre-Commit / CI" subsection showing both targets with descriptions.
- `hermes_loop/config.py` — Bumped `LAUNCH_LOOP_VERSION` from 14.21.0 to 14.22.0.
- `run.sh` — Banner version updated to v14.22.0.

---

## [14.20.0] — 2026-06-26

### Added
- **`--status` flag**: New built-in `hermes_loop --status` command that reads the
  iteration ledger and displays a compact, colorized status summary in the terminal.
  No `--goal` required. Shows daemon status (running/paused/stopped), iteration
  count with success/error/stuck breakdown, duration, current goal, last iteration
  summary with error info, worker/evolve/git config, and quick-action stop/pause/log
  commands. Replaces the need for `cat /tmp/infinite-loop-state.json | python3 -m json.tool`
  or `bash scripts/inspect-ledger.sh --summary` for quick status checks.
  Example output:
  ```
  \---------------------------------------------------------------------
    Status:        ✓ running
    Iterations:    10  (✓8 ok, ✗2 err)
    Errors:        timeout=2
    Duration:     45s
    Goal:         Fix lint errors one at a time
    Updated:      2026-06-26T12:00:00

    [Last Iteration]
      #10  Resolved 3 ESLint warnings in src/utils.ts

    Workers: 1  Evolve: yes  Git: yes

    Quick actions:
      Stop:   echo stop > /tmp/infinite-loop-stop
      Pause:  echo pause > /tmp/infinite-loop-stop
      Logs:   tail -f /tmp/infinite-loop-state.json
      Full:   bash scripts/inspect-ledger.sh
  ```
- **`--status` in `Makefile`**: `make status` now uses `python3 -m hermes_loop --status`
  (the built-in) instead of `bash scripts/inspect-ledger.sh --summary`. Falls back to
  the shell script if the built-in fails.
- **`--status` in `--help` description**: The `Status:` line in `--help` now shows
  `python3 -m hermes_loop --status` instead of `cat /tmp/... | python3 -m json.tool`.
- **`--status` in `--examples` Help & Diagnostics section**: New "Status & Monitoring"
  subsection with `--status` usage examples.
- **`--status` added to `Standalone_flags` set**: Works without `--goal`.

### Changed
- `hermes_loop/cli.py` — New `_display_status()` function (130 lines). Added `--status`
  to pre-argparse handler, introspection flags, and Startup & Debug argparse group.
- `hermes_loop/config.py` — Bumped `LAUNCH_LOOP_VERSION` from 14.19.0 to 14.20.0.
- `run.sh` banner updated to v14.20.0.
- `README.md` — Updated changelog, quick-start status command, and feature references.
- `Makefile` — `make status` now calls the built-in `python3 -m hermes_loop --status`.

---

## [14.21.0] — 2026-06-26

### Added
- **`--explain` flag**: New `hermes_loop --explain <flag>` command that shows
  detailed help for any single CLI flag. Accepts full flag names or unambiguous
  prefixes (e.g., `--explain workers`, `--explain converge` for single matches,
  shows alternatives for ambiguous prefixes). Displays: argument group, type
  (boolean/integer/float/string/choice), default value, full help text with
  word-wrapping, aliases, related flags in the same group, and a usage example
  tailored to the flag type. Pre-argparse — no `--goal` required. Example
  output:
  ```
  --workers
    ===========

    Group:     Parallelism
    Type:      integer
    Default:  1

    Description:
      Run N concurrent Hermes sessions per iteration

    Related:   (no other flags in this group)

    Usage:
      --workers N       # e.g. --workers 10
  ```
- **`--explain` in `--examples` output**: New "Flag Reference" section with
  detailed `--explain` usage examples alongside existing `--list-flags` and
  `--list-groups` commands. Also added `--explain` to the "Help & Diagnostics"
  section.
- **`--explain` added to `Standalone_flags` set**: Works without `--goal`.

### Changed
- `hermes_loop/cli.py` — New `_explain_flag()` function (90 lines) that
  introspects the argparse parser to find and display detailed flag info.
  Added `--explain` to Startup & Debug argparse group, pre-argparse handler,
  introspection flags, and standalone flags set.
- `hermes_loop/config.py` — Bumped `LAUNCH_LOOP_VERSION` from 14.20.0 to 14.21.0.
- `README.md` — Updated changelog, version in header.

---

## [14.20.1] — 2026-06-26

### Changed
- `run.sh` — Banner version updated to v14.20.0, "What's new" section now highlights
  `--status` and shutdown summary features (was still showing v14.18.0 content).
- `CONTRIBUTING.md` — Fixed stale version reference (14.18.0 → 14.20.0), stale
  module count (32 → 35), stale self-test count (45 cases / 9 groups → 50 cases /
  10 groups), and stale flag counts (87 → 90). Added `validate_env_vars()` to the
  self-test reference table.
- `README.md` — Updated module count reference from 32 to 35 in two places.
- `CHANGELOG.md` — Added missing v14.20.1 entry with docs fixup details.

---

## [14.19.0] — 2026-06-26

### Added
- **Shutdown summary banner** in `hermes_loop/loop.py`: New `_print_shutdown_summary()`
  function that prints a comprehensive final summary when the daemon stops — total
  iterations, duration, success/fail counts, error type breakdown, git stats, and
  actionable next-steps (how to view the ledger, re-run, or get help). Called from
  every exit path: signal, sentinel, max-iterations, idle, convergence, goals-exhausted,
  error-backoff, and persistent-failure. Example output:
  ```
  ═══════════════ SHUTDOWN SUMMARY ═══════════════
    Status:       stopped: max_iterations (10)
    Iterations:   10
    Duration:     1245s (20.8m)
    Success:      ✓8
    Errors:       ✗2
    Breakdown:    timeout=2
    Final goal:  Fix lint errors one at a time

  Next steps:
    View ledger:     bash scripts/inspect-ledger.sh
    Summary:         bash scripts/inspect-ledger.sh --summary
    Errors:          bash scripts/inspect-ledger.sh --errors-only
    Re-run:          bash run.sh
    Restart with:    python3 -m hermes_loop --goal "..." --run
    Help:            python3 -m hermes_loop --help
    Examples:        python3 -m hermes_loop --examples
  ══════════════════════════════════════════════
  ```
- **Signal handler shutdown summary** in `hermes_loop/signal_handlers.py`: When
  SIGINT (Ctrl+C) or SIGTERM is received, a compact shutdown summary is printed
  before the process exits, showing the signal name, iteration count, and status.
- **Improved post-run message** in `hermes_loop/cli.py`: Changed "Done." to
  `[DONE] Daemon finished. Ledger at /tmp/infinite-loop-state.json` so users
  always know where to find the ledger.

### Changed
- `hermes_loop/loop.py` — Added `_print_shutdown_summary()` function and
  wired it into all 7 exit paths in `run_loop()`.
- `hermes_loop/signal_handlers.py` — Added signal-safe shutdown summary using
  imported colorizer and inline summary generation.
- `hermes_loop/cli.py` — Post-run loop message now includes ledger path.
- `hermes_loop/config.py` — Bumped `LAUNCH_LOOP_VERSION` from 14.18.0 to 14.19.0.

---

## [14.18.0] — 2026-06-26

### Added
- **`count_self_test_cases()` function** in `hermes_loop/self_test.py`: Static-code-analysis
  function that auto-detects the number of test groups and cases by introspecting the
  `_run_self_test()` function body. Uses `re.findall()` to count `_test_*` functions
  and `cases.append()` calls. Never goes stale as tests evolve.

### Changed
- **Self-test counts are now auto-detected at runtime**, eliminating the stale
  "9 groups, 45 cases" / "10 groups, 52 cases" hardcoded references across the
  codebase. All documentation now says "auto-detected at runtime" instead of
  hardcoded numbers:
  - `README.md` (2 places), `Makefile`, `CONTRIBUTING.md`, `.env.example`,
    `SKILL.md`, `run.sh`, `hermes_loop/cli.py`
- `run.sh` banner: Replaced stale "Docs now consistent: \"9 groups, 45 cases\""
  with "Self-test count auto-detected (never stale)"
- `hermes_loop/cli.py` — `--self-test` help text and `--examples` output now
  reference auto-detection instead of hardcoded counts
- `hermes_loop/config.py` — Bumped `LAUNCH_LOOP_VERSION` from 14.17.0 to 14.18.0.

---

## [14.17.0] — 2026-06-26

### Added
- **`--check-env` flag**: Validate your `.env` file for typos, unknown variables, and
  common mistakes without needing `--goal`. Every `INFINITE_LOOP_*` variable is checked
  against the canonical list of 82 recognized variables. Misspellings like
  `INFINITE_LOOP_COOL_DOWN` are detected and corrected (`→ INFINITE_LOOP_COOLDOWN`).
  Non-prefixed variables are flagged as warnings. The exit code is 0 when no issues
  are found, 1 when typos/unknowns/deprecated vars are present.
  Examples:
  ```bash
  python3 -m hermes_loop --check-env              # validate .env in cwd
  make check-env                                   # same via Makefile
  bash run.sh --check-env                          # same via run.sh wrapper
  ```
- **`hermes_loop/env_utils.py`** — New module with `parse_env_vars_from_file()`,
  `validate_env_vars()`, `format_validation_results()`, `check_env_file()`,
  and `_find_closest_match()` (fuzzy matching via `difflib.get_close_matches`).
  All 82 known env vars are defined as the `KNOWN_ENV_VARS` set, which should be
  kept in sync with `.env.example` and `run.sh`.
- **`--dry-run` now validates .env**: Running `--dry-run` automatically checks the
  `.env` file for issues and reports them as part of the dry-run output. Issues
  are non-blocking (suggestive only), so the dry-run still proceeds.
- **`make check-env` target**: New Makefile convenience target for env validation.
- **`self_test.py` — `test_validate_env_vars`**: 7 new self-test cases covering
  known vars, typo detection, unknown vars, non-prefix vars, fuzzy matching, no-match
  fallback, and missing-required-var warnings.

### Changed
- `run.sh` — Added `--check-env` to the Actions section in `--help` and to the
  while-loop passthrough so it forwards correctly.
- `Makefile` — Added `check-env` target and documented it in the help/usage section.
- `hermes_loop/cli.py` — `main()` now handles `--check-env` as a pre-argparse flag
  (no `--goal` required) and validates env during `--dry-run`. Added import of
  `check_env_file`, `validate_env_vars`, `parse_env_vars_from_file`. Added
  `--check-env` to the `Standalone_flags` set and the Startup & Debug argparse group.
- `hermes_loop/config.py` — Bumped `LAUNCH_LOOP_VERSION` from 14.16.0 to 14.17.0.
- Updated self-test references from "9 groups, 45 cases" to "10 groups, 52 cases" across 5 files (README.md, Makefile, CONTRIBUTING.md, .env.example, cli.py).

---

### Added
- **`--completion-script {bash|zsh}` flag**: Generate shell completion scripts
  directly from the live argparse parser, eliminating the need for manually
  maintained static completion files. Never worry about flag drift again.
  Examples:
  ```bash
  python3 -m hermes_loop --completion-script bash    # print bash completions
  python3 -m hermes_loop --completion-script zsh     # print zsh completions
  python3 -m hermes_loop --completion-script bash | source /dev/stdin
  ```
- **`hermes_loop/completions.py`** — New module with `generate_bash_completion()`
  and `generate_zsh_completion()` functions that introspect an argparse parser
  and emit ready-to-use completion scripts. Both scripts pass `bash -n` / `zsh -n`
  syntax checking. Covers boolean flags, value flags, and choice-constrained flags.
- **`make update-completions`** — New Makefile target that regenerates the
  completion scripts at `scripts/completion/bash` and `scripts/completion/zsh`
  from the live argparse definitions. Run after adding/removing flags.

### Changed
- `hermes_loop/cli.py` — `main()` now checks for `--completion-script` before
  argparse (similar to `--examples` / `--list-flags`), so it works without
  requiring `--goal`. Added `--completion-script` to the Introspection section
  in `--list-flags` output. Added the flag to the Startup & Debug argument group.
- `Makefile` — `make lint` now also checks shell syntax of the completion scripts
  via `bash -n` and `zsh -n`. New `update-completions` target regenerates from
  `--completion-script`.
- `run.sh` — Added `--completion-script` to the `--help` info section and the
  while-loop for direct pass-through to launch-loop.py.
- `hermes_loop/config.py` — Bumped `LAUNCH_LOOP_VERSION` from 14.15.0 to 14.16.0.

---
## [14.15.0] — 2026-06-26

### Added
- **Auto-colorized `_log()` tags**: Every structured log tag (`[INFO]`, `[WARN]`,
  `[ERROR]`, `[DAEMON]`, `[GOALS]`, `[PREFLIGHT]`, `[COOLDOWN]`, `[BEAT]`,
  `[NOTE]`, `[SUGGEST]`, `[OK]`, `[DONE]`, `[SUMMARY]`, `[AUTO-RELOAD]`,
  `[CONFIG]`, `[STATUS]`, `[ARCHIVE]`, `[COMPACT]`, `[LOG]`, `[CONTEXT]`,
  `[OUTPUT]`, `[HEARTBEAT]`, `[MODE]`) is now automatically colorized in the
  `_log()` function — no per-call changes needed. Tags are bold-red (error),
  bold-yellow (warn/cooldown), bold-green (ok/done), bold-cyan (summary),
  bold-blue (daemon/preflight/config/auto-reload), bold-magenta (suggest/goals),
  and dimmed (beat/status/archive/log/context/output/compact/heartbeat).
  Respects `--color=auto|always|never` and `NO_COLOR` automatically.
  This means every module that calls `_log()` gets colorized output for free.
- **Colorized startup banner** in `cli.py` `main()`: Header separator lines are
  now bold blue, the version header is bold cyan, and feature descriptions use
  dimmed text with colored `[SUMMARY]`, `[SUGGEST]` tags and `--examples`/`--quiet`
  flags. The "Starting loop..." message is bold green with a colored sentinel path.
- **New `_colorize_log_tags()` function** in `file_utils.py`: Centralized tag
  pattern → colorizer mapping with 24 tag patterns. Clean fallback when color
  is disabled — no string allocations when color is off.

### Changed
- `hermes_loop/file_utils.py` — `_log()` now auto-colorizes known log tags.
- `hermes_loop/cli.py` — startup banner sections, feature lines, and
  "Starting loop..." message use colorizer for richer output.
- `hermes_loop/config.py` — bumped LAUNCH_LOOP_VERSION from 14.14.0 to 14.15.0.

---

## [14.14.0] — 2026-06-26

### Added
- **`--color=[auto|always|never]` flag**: Choose when ANSI color is applied to CLI output.
  `auto` (default) enables colors when stdout is a TTY, `always` forces colors even when
  piped, `never` disables all color. Also respects the `NO_COLOR` environment variable.
- **Colorized `--list-flags` and `--list-groups` output**: Group titles are now bold magenta,
  flag names are cyan, descriptions are dimmed — making the 87-flag reference visually scannable.
  Flag column padded to 38 chars for readability.
- **Colorized `--examples` output**: Section headers are bold cyan, command examples are yellow,
  comments are dimmed. Inner helper functions (`_section`, `_cmd`, `_comment`) keep the code tidy.
- **Colorized iteration output**: `[SUMMARY]` tag is bold cyan on success, `[FAIL]` is bold red
  on errors. `[DONE]` tag is bold green for OK, bold red for errors. `[SUGGEST]` tag is bold magenta.
  Error summaries use `[FAIL]` instead of `[SUMMARY]` for immediate visual recognition.
- **New `hermes_loop/color_utils.py` module**: ANSI `Colorizer` class with terminal detection
  (TTY + `NO_COLOR`), named color helpers, tag formatters, and `strip_ansi()` utility.
  Exposes a module-level `colorizer` singleton callable from anywhere in the package.
- **`--color` pre-argparse detection**: Color mode is detected before argparse parsing so that
  pre-argparse flags (`--list-flags`, `--examples`, `--self-test`) also benefit from color.

### Changed
- `hermes_loop/cli.py` — `_list_flags()`, `_list_examples()`, `_create_parser()`, and `main()` 
  all updated for ANSI color support. `_list_examples()` refactored with helper functions
  (`_section`, `_cmd`, `_comment`) for cleaner code.
- `hermes_loop/loop.py` — `[SUMMARY]`, `[DONE]`, and `[SUGGEST]` log lines now use
  colored tags from `colorizer`.
- `hermes_loop/config.py` — bumped LAUNCH_LOOP_VERSION from 14.13.0 to 14.14.0.

---

## [14.13.0] — 2026-06-26

### Changed
- **`--list-flags` and `--list-groups` now auto-generate from argparse**: Replaced the 134-line hardcoded dictionary of flag help text with live introspection of the argparse parser via `_create_parser()` and `parser._action_groups`. Every flag's help text now comes directly from `add_argument(help=...)` — no more drift between `--help` and `--list-flags`. New flags added to argparse appear in `--list-flags` automatically.
- **Extracted `_create_parser()` from `main()`**: The full argument parser setup is now a standalone function callable from both `main()` and `_list_flags()`. It accepts `for_introspection=True` to make `--goal` non-required (needed for pre-argparse flag listing).
- **New `[Introspection]` section in `--list-flags`**: Pre-argparse flags (`--help`, `--list-flags`, `--list-groups`, `--examples`, `--version`) now appear in a dedicated group at the end of the output, separate from the 22 argparse groups.
- **Auto-generated flag count**: The "87 flags in 23 groups" summary is now computed from the actual parser, ensuring it stays accurate as flags change.

### Removed
- **Hardcoded `flags_by_group` dictionary**: The 134-line hardcoded dict in `_list_flags()` is gone. No more manual maintenance of a separate flag catalog.

---

## [14.12.0] — 2026-06-26

### Added
- **`make examples`, `make list-flags`, `make list-groups` Makefile targets**: Three new convenience targets for the Makefile, alongside existing `make self-test` / `make version`. Users can now run `make examples` to see categorized usage patterns, `make list-flags` for the full organized flag listing, and `make list-groups` for compact group overviews — all without remembering the underlying CLI flag names.
- **`run.sh --help` now documents `--list-groups` and `--examples`**: The info section of `run.sh --help` now explicitly lists all three introspection flags (`--list-flags`, `--list-groups`, `--examples`) with updated descriptions showing flag counts and category counts. Previously only `--list-flags` and `--examples` were listed.
- **`run.sh` banner mentions v14.11.0 docs consistency fix**: Added "Docs now consistent: '9 groups, 45 cases'" to the "What's new" banner section so users immediately see the latest documentation improvement.

### Changed
- **`CONTRIBUTING.md` Common Commands table**: Expanded with `make examples`, `make list-flags`, `make list-groups`, `make status`, `make log`, and `make stop` entries. Removed duplicate rows for `make status` and `make stop` that had conflicting descriptions.
- **`README.md` Quick Start Makefile section**: Added `make examples`, `make list-flags`, and `make list-groups` to the Makefile usage examples in the Quick Start section.
- **`run.sh --help` descriptions**: Updated `--list-flags` description from "Print organized flag listing" to "Print all 87 flags organized by group with help text" and added missing `--list-groups` entry with "Print compact group names with flag counts".

---

## [14.11.0] — 2026-06-26

### Fixed
- **"~40 tests" documentation mismatch**: All docs referenced "~40 tests" or "~40 checks" for the self-test suite, but the actual output reports 9 test groups (45 individual cases). Updated every occurrence across 6 files to use consistent "9 groups, 45 cases" language: `README.md` (2 places), `Makefile`, `hermes_loop/cli.py`, `.env.example`, `CONTRIBUTING.md` (2 places), `SKILL.md`. Also fixed a stale missing-quote typo in `CONTRIBUTING.md` (`"14.10.0` → `"14.10.0"`).

### Added
- **`--list-flags`, `--list-groups`, `--examples` in README flag table**: These three pre-argparse convenience flags were missing from the Startup/Debug section of the README's "All CLI Flags" reference. Added with descriptions and default values.
- **`--list-flags`, `--list-groups`, `--examples` in CONTRIBUTING.md**: Added to the Common Commands table so new contributors can discover them immediately.
- **`CONTRIBUTING.md` test table correction**: Updated the self-test coverage table with accurate case counts (text_similarity: 3→5, validate_json_output: 3→4, GoalSpec: 3 with corrected descriptions, _classify_progress: 6→4, _suggest_actionable_fix: 7→9) and added actionable suggestions test group.

### Changed
- `CONTRIBUTING.md` — test table now reflects reality: 9 test groups, 45 total cases, accurate descriptions per group.

---

The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/) and this
project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

---

## [14.10.0] — 2026-06-26

### Added
- **Rich post-iteration summary (`[SUMMARY]`)**: Replaces the plain `[DONE]` / `[PROGRESS]` / `[STATS]` lines with a single consolidated summary showing iteration count, task type, duration, classification, git changes (if enabled), system resource usage (CPU seconds and memory), worker breakdown (success/fail counts), progress bar with percentage, and ETA. Error iterations include the error type. Normal iterations show classification (completed/progress/partial/stuck).

### Removed
- **Separate `[PROGRESS]` and `[STATS]` log lines**: Merged into the new `[SUMMARY]` line for a cleaner, more scannable log output.

### Changed
- `hermes_loop/loop.py` — replaced the 3-line [DONE]/[PROGRESS]/[STATS] block with a unified rich summary function that conditionally displays git diffs, system CPU/memory usage, worker breakdowns, and ETA/progress bar.
- `hermes_loop/config.py` — bumped LAUNCH_LOOP_VERSION from 14.9.0 to 14.10.0.

---

The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/) and this
project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

---

## [14.9.0] — 2026-06-26

### Added
- **`--examples` flag**: Prints categorized real-world usage examples covering 7 categories: Basic Single-Goal Loop, Git-Integrated Evolution, Batch/Goals-File Processing, Notifications & Monitoring, Monitoring & Control, Advanced Patterns, and Help & Diagnostics. Accessible before argparse (no `--goal` required), same as `--list-flags`. Includes shell commands for common operations (stop, pause, status, inspect-ledger, dashboard) and quick-reference diagnostics.
- **Missing `--goal` error improvement**: Now also points users to `python3 -m hermes_loop --examples` for usage patterns, alongside the existing `--help` reference.
- **Tab-completion update**: `--examples` added to both bash and zsh completion scripts.

### Changed
- `cli.py` — new `_list_examples()` function (145 lines) with categorized real-world usage examples. Pre-argparse handler for `--examples` (bypasses `--goal` requirement). Added to standalone_flags set.
- `scripts/completion/bash` — added `--examples` to bool_flags array.
- `scripts/completion/zsh` — added `--examples` completion definition.
- `hermes_loop/config.py` — bumped LAUNCH_LOOP_VERSION from 14.7.0 to 14.9.0.
- `run.sh` — banner updated to v14.9.0 with --examples listed as new feature.
- `README.md` — updated v14.9.0 changelog entry in the README, added --examples to the "v14.9.0 Changelog" table in the README.

---

## [14.8.0] — 2026-06-26

### Changed
- **Project structure documentation** — Updated `README.md` file tree to show the `hermes_loop/` package (32 modules) instead of describing `launch-loop.py` as the main daemon. The shim is now correctly documented as a thin backward-compatible wrapper (18 lines).
- **`CONTRIBUTING.md`** — Complete overhaul for the package architecture: updated every reference from `launch-loop.py` (the old monolithic 7.7K-line file) to the `hermes_loop/` package; fixed stale version reference (`14.2.0` → `14.7.0`); updated project structure tree with all 32 modules, `references/` and `research/` directories; fixed version bump instructions to point to `hermes_loop/config.py`; added package-aware syntax-check commands.
- **`Makefile` lint target** — Now checks all 32 `hermes_loop/*.py` modules in addition to `session-self-loop.py` and `launch-loop.py`. Uses a loop that reports per-file pass/fail with a final summary.

### Added
- `hermes_loop/` package added to the README scripts table with description.

### Fixed
- Stale project structure references throughout documentation — the repo has been a `hermes_loop/` package since v14.0.0 but CONTRIBUTING.md and README.md still described the old flat architecture.

---

## [14.7.0] — 2026-06-26

### Added
- **`--list-flags` and `--list-groups` flags**: Quick-reference flag listing that doesn't require `--goal`. `--list-flags` prints all 80+ flags organized by group with help text. `--list-groups` prints only group names with flag counts. Much faster than scrolling through the full `--help` output. Usage: `python3 -m hermes_loop --list-flags` or `python3 launch-loop.py --list-groups`.
- **Shell tab-completion scripts** for bash and zsh: Auto-completes all 80+ CLI flags with deduplication (flags already on the command line are hidden). Supports `python3 launch-loop.py --<TAB>`, `python3 -m hermes_loop --<TAB>`, and `bash run.sh --<TAB>`. Boolean flags and value flags are distinguished — value flags show file/directory completion where applicable. `--task-type` and `--cooldown-mode` offer specific choice values.
- **`make completion` target**: Installs the appropriate completion script for your current shell (bash or zsh) when run with `make completion`. Also shows manual install instructions.
- **Bumped from v14.6.0 to v14.7.0**

### Changed
- `cli.py` — new `_list_flags()` function (150 lines) with all flags organized by 22 groups. Added pre-argparse handlers for `--list-flags` and `--list-groups` (bypasses `--goal` requirement).
- `scripts/completion/bash` — new bash completion script (224 lines). Uses `_init_completion` for robust Zsh-incompatible-bash completion. Deduplicates flags already on the command line. `--task-type` and `--cooldown-mode` offer specific choice values; file-type flags offer `_filedir`.
- `scripts/completion/zsh` — new zsh completion script (140 lines). Uses `#compdef` header and `_arguments -C` with `_files` fallback.
- `Makefile` — new `completion` target that detects shell and installs the right script.
- `README.md` — updated to v14.7.0, added Shell Completion section to feature deep-dive and TOC.
- `run.sh` — banner updated to v14.7.0 with new features listed.
- `.env.example` — documented `INFINITE_LOOP_QUIET` and `--list-flags` in Startup & Debug section.
- `scripts/run-loop.sh` — version bump.

---


### Added
- **`--quiet` flag**: Suppresses the verbose startup banner, per-iteration headers (`=== Iteration N ===`), and config dump. Shows only compact one-line status updates. Ideal for background daemon runs (`bash run.sh --quiet` or `INFINITE_LOOP_QUIET=true` in `.env`).
- **Iteration heartbeat (`[BEAT]` messages)**: A background thread logs periodic `[BEAT] Iteration #N still running (120s elapsed)...` messages during long-running iterations (every 2 minutes). No more ambiguous silence: you can tell if the daemon is working or hung without cross-referencing logs.
- **Bumped from v14.5.0 to v14.6.0**

### Changed
- `cli.py` — wrapped config dump (50+ lines) in `if not args.quiet:` block, added `quiet=` forwarding to `run_loop()` and `_log_startup_banner()`
- `functions.py` — `_log_startup_banner()` accepts `quiet` parameter; when True, prints a compact one-line status instead of the full categorized banner
- `loop.py` — iteration header is compact (`[ITER #N] goal`) in quiet mode; passes `quiet` to `_execute_iteration()`
- `iteration.py` — new background heartbeat thread during spawned session execution; `_execute_iteration()` accepts `quiet` parameter
- `run.sh` — `--quiet`/`-q` now forwards `--quiet` to daemon (was banner-only); `INFINITE_LOOP_QUIET` env var support; banner shows `quiet=on/off`
- `.env.example` — documented `INFINITE_LOOP_QUIET` variable

---

## [14.5.0] — 2026-06-26

### Added
- **Actionable [SUGGEST] messages after errors/stuck/regression iterations**: Each iteration now shows context-aware, actionable suggestions when something goes wrong. Maps error types (timeout → increase session-timeout, network → check connectivity, schema → review schema) and classifications (stuck → reduce workers/try use-library, regression → review git diff) to specific CLI flags the user can adjust.
- **Self-tests for `_suggest_actionable_fix()`**: 9 test cases covering all suggestion patterns: completed/progress (no suggestion), timeout, network, schema, stuck with workers >1, stuck in library mode, regression, consecutive errors, and schema errors.
- **Bumped from v14.4.0 to v14.5.0**

### Changed
- `_suggest_actionable_fix()` imported in `loop.py` and called after every [DONE] line
- Suggestion output prefixed with `[SUGGEST]` for clear log distinction
- `error_utils.py` — new `_suggest_actionable_fix()` function (90 lines)
- `loop.py` — displays suggestion after [DONE] when applicable
- `self_test.py` — 9 new test cases for suggestion engine

---

## [14.4.0] — 2026-06-26

### Added
- **Readable startup banner**: Replaced the wall-of-text feature dump (one giant `_log()` call listing 15+ features) with a categorized, conditional configuration overview. Only shows features that are actually enabled, grouped by category (Iteration, Parallel, Sessions, Spawn, Git, Output). Uses `[DAEMON] ═══` header and indented categories for visual hierarchy.
- **Iteration header shows goal + progress bar**: The `=== Iteration N ===` header now displays the current goal (truncated to 100 chars), a Unicode progress bar with percentage (when `--max-iterations` is set), and active config (workers, turns). No more scrolling up to find what the current goal is.
- **Informative [DONE] line**: Now includes status icon (✓/✗), duration in seconds, and progress classification alongside the summary. At a glance: was it successful, how long did it take, was it progress or stuck?
- **Updated run.sh banner**: Restructured with "What's new ⚡" section, expanded info panel (toolsets, evolve status), and organized "Commands:" section with Pause/Help added.

### Changed
- Bumped `launch-loop.py` from v14.3.0 to v14.4.0
- Removed 15 redundant `_log()` lines from startup banner (now covered by categorized overview)
- Shrunk `_log_startup_banner()` by ~30 lines while adding more useful information
- `_log_startup_banner()` now accepts `max_iterations` parameter
- Updated run.sh banner version and content

---

## [14.3.0] — 2026-06-26

### Added
- **Organized `--help` output**: All 80+ CLI flags now grouped into 22 logical
  sections (Core Task, Toolsets, Iteration Control, Parallelism, Timeouts &
  Retries, Git Integration, Goals File, Rate Limiting, Convergence Detection,
  Structured Output, Shutdown, Profile/Model, Webhook/HTTP, Notifications,
  Logging, Status/Dashboard, Ledger Management, Archiving, File Watcher,
  Worker, Spawned Session Flags, Startup/Debug) for much more readable
  `--help` output.
- **Structured `--help` description**: Replaced the wall-of-text argparse
  description with a readable multi-line summary: "Features at a glance"
  grouped by category (Iteration, Parallel, Notify, Sessions, Spawn, Debug,
  Git, Web), common usage examples, and stop/pause/status commands. Uses
  `RawDescriptionHelpFormatter` for proper formatting. (`--help` and `--help
  -h` now bypass argparse for instant response.)
- **Friendly missing `--goal` error**: Before argparse's default "required"
  error, prints a clear message: "ERROR: --goal is required (or use
  --goals-file for batch mode)" with usage hint and pointer to `--help`.

### Changed
- **Readable startup banner**: Replaced the 10-line wall-of-features text with
  a compact feature summary (3 lines, pipe-separated categories under a
  Unicode ═ header). No more version-dependent banner drift.
- Bumped `launch-loop.py` from v14.2.0 to v14.3.0

### Fixed
- **`run.sh --dry-run` with `.env` `--run`**: When `--dry-run` is used but
  `.env` has `INFINITE_LOOP_RUN=true`, the `--run` flag was still forwarded
  making dry-run effectively a no-op. Now `--dry-run` strips `--run` from
  the forwarded args.

### Added
- **Makefile**: Convenience targets — `make run`, `make dry-run`, `make self-test`,
  `make lint`, `make status`, `make stop`/`pause`/`resume`, `make clean`,
  `make archive`, `make log`, `make version`, `make env`, `make help`.
- **CONTRIBUTING.md**: Onboarding guide for new contributors covering setup,
  development workflow, code style, submitting changes, and troubleshooting.
- **Improved `run.sh --help`**: Organized sections (General, Actions, Info,
  Examples) with inline quick reference for ledger, status, sentinel, and
  dashboard commands.
- **`run.sh --self-test` and `--version`**: New CLI passthrough flags.
- **`./run.sh` banner**: Now displays v14.2.0 version and new features.

### Fixed
- **SSE broadcast crash**: Added missing `global _sse_clients` declaration in
  `_broadcast_to_sse_clients()` to prevent `UnboundLocalError` on first call.

### Changed
- Bumped `launch-loop.py` from v14.1.0 to v14.2.0
- Bumped `session-self-loop.py` from v2.11.0 to v2.12.0
- Bumped `run-loop.sh` banner and header to v14.2.0
- Updated README: v14.2.0 changelog table, Makefile & CONTRIBUTING.md in
  header, scripts table, and filesystem tree

---

## [14.1.0] — 2026-06-26

### Added
- **Dashboard XSS Fix**: Replaced `innerHTML` string interpolation with `createElement` + `textContent` in SSE dashboard's `addIterationRow()`. Eliminates DOM-based XSS from spawned session output.
- **Dashboard Error Panel**: Error type count cards (timeout, network, schema, unknown) with color-coded left-border accents. Active mitigations displayed as tags.
- **Dashboard Performance Metrics**: Avg turns, estimated tokens/iter, cost estimate, iters/goal metric cards on SSE dashboard.
- **Dashboard Goals Visualization**: Per-goal status with progress bar, ✓/▶/○ indicators, scrollable list. Populated from `goals_specs` + `goals_completed` via SSE payload.
- **False Convergence Guard**: `_detect_convergence()` skips Jaccard similarity check when summary < 20 chars. Prevents false convergence stops from empty/error summaries.
- **`--quiet` / `-q` mode**: Suppresses ASCII banner and startup info in CI/CD and scripted use.

### Changed
- Bumped `run-loop.sh` from v14.0.0 to v14.1.0 (version header + banner)
- Bumped `session-self-loop.py` from v2.10.0 to v2.11.0

### Fixed
- False convergence stops from empty/error summaries

---

## [14.0.0] — 2026-06-24

### Added
- **Dashboard v3 SSE** (Server-Sent Events): `GET /live` SSE stream, `GET /dashboard` live HTML with auto-refresh
- **Session Self-Healing Heartbeat**: `--heartbeat-timeout N` flag with grace period (`timeout × 2`), kill & retry on hung sessions
- **Preflight Hermes Version Check**: `check_hermes_version()` static method on `PreflightChecker`
- **Auto-start Hermes Worker**: `--worker-url auto` (default) auto-starts embedded worker on random port
- **Function Decomposition Phase 2**: extracted `_execute_iteration()`, `_merge_worker_results()`, `_handle_backoff()` from `run_loop()`. Shrunk `run_loop()` by ~250 lines.
- **Function Decomposition Phase 3**: extracted `_detect_convergence()`, `_compact_summaries()`, `_build_iteration_record()`, `_handle_notifications()`, `_handle_callbacks()`. Shrunk `run_loop()` by another ~220 lines.

### Changed
- `lm-eval-harness` reference doc added to project

---

## [13.1.0] — 2026-06-24

### Added
- **Idempotent Goal Execution**: `--track-goals` and `--reset-goals` flags. Completed goals tracked via hash and automatically skipped on restart.
- **Goal Hash Tracking**: `_goal_hash()` uses `hashlib.md5` of goal text + iteration number
- **Webhook Payload Enrichment**: `_handle_callbacks()` already enriches with state, stats, system, pid
- **Multi-Profile Goals**: Pipe-separated format in `--goals-file` supports per-goal profile/model/provider overrides (`goal|profile|model|provider`)

### Fixed
- Version inconsistencies across all reference files bumped to v13.0.0+

---

## [13.0.0] — 2026-06-24

### Added
- **Self-Test Mode**: `--self-test` flag runs ~40 in-process tests across 8 daemon functions
- **Output Progress Classification**: `_classify_progress()` categorizes iterations as completed/progress/partial/stuck/regression/unknown
- **Startup Banner**: Comprehensive listing of all daemon features
- **Enhanced `--help`**: Full options summaries for all 45+ flags
- **50+ TASK_PATTERNS keywords**: Better task-type auto-detection across all 7 categories

### Changed
- Startup banner now dynamically displays version from VERSION constant
- All 34/34 self-tests pass, all syntax checks clean

---

## [12.0.0] — 2026-06-23

### Added
- **Concurrent Library Mode**: `--use-library` now works with `--workers > 1` via `multiprocessing.Pool`
- **Automatic Error Recovery**: `_adapt_to_error()` with behavioral mitigation based on error type and history
- **In-Process Ledger Archiving**: `--archive-dir`, `--archive-retention`, `--archive-max-size` flags
- **Multi-Profile Goals File**: Pipe-separated format (goal|profile|model|provider)

### Changed
- `ThreadPoolExecutor` replaced with `multiprocessing.Pool` for library mode
- Function Decomposition Phase 1: extracted `_load_goals_file()`, `_log_startup_banner()`, `_cycle_goal()`, `_build_progressive_context()`, `_handle_cooldown()` from `run_loop()`

---

## [11.14.0] — 2026-06-23

### Added
- `--safe-mode` flag: Disables ALL customizations (implied `--ignore-rules` + `--ignore-user-config`)
- `--accept-hooks` flag: Auto-approve shell hooks without TTY
- `--worktree` flag: Run spawned sessions in isolated git worktree
- `--continue` flag: Resume most recent session

### Changed
- All 74 Hermes `chat -q` passthrough flags now fully covered
- Argparse flags: 81+ add_argument calls, all properly threaded

---

## [11.13.0] — 2026-06-23

### Added
- `--yolo` flag: Bypass dangerous command approval prompts
- `--ignore-user-config` flag: Skip `~/.hermes/config.yaml` in spawned sessions
- `--spawn-source` flag: Tag spawned sessions with custom source label (default: `infinite-loop`)

---

## [11.12.0] — 2026-06-23

### Added
- **Session Chaining** (`--resume`): Chain spawned sessions across iterations via `--resume SESSION_ID`
- **Skills Flag** (`--skills`): Preload specific skills in spawned sessions (comma-separated)
- **Ignore Rules Flag** (`--ignore-rules`): Clean-slate mode (no AGENTS.md, memory, or rules)
- **Session ID History**: Rolling list of spawned_session_id values (last 100) stored in ledger

---

## [11.11.0] — 2026-06-22

### Added
- **AIAgent Library Mode** (`--use-library`): Run AIAgent.run_conversation() in-process instead of spawning subprocess. Eliminates subprocess overhead, provides direct token/cost data.
- **Session Tracking** (`--pass-session-id`): Store spawned session ID in ledger
- **Checkpoints Flag** (`--checkpoints`): Enable file checkpoints in spawned sessions (auto-enabled with `--git`)

### Changed
- `run-loop.sh` bumped from v11.10.0 to v11.11.0 with all three new flags forwarded

---

## [11.10.0] — 2026-06-22

### Fixed
- `output_cap` undefined variable in worker URL mode
- HTML dashboard now dynamically displays version from VERSION constant

### Changed
- Updated all DAEMON/startup banners to reflect v11.9.0 features
- Added `{VERSION}` placeholder to dashboard footer and header

---

## [11.9.0] — 2026-06-22

### Added
- **Pushbullet mobile notifications**: `--notify-pushbullet TOKEN` via Pushbullet API v2
- **ntfy push notifications**: `--notify-ntfy TOPIC` via ntfy.sh or self-hosted ntfy server
- **Unified notification dispatcher**: `_send_per_iteration_notifications()` sends to all channels in one call
- **Completion notification** now uses all channels when Pushbullet/ntfy set

### Removed
- Old `_send_completion_notification()` replaced with unified version

---

## [11.8.0] — 2026-06-22

### Added
- `/api/status` endpoint: Returns COMPLETE ledger state dict
- **REST API control endpoints**: POST `/control/stop`, `/control/pause`, `/control/resume`
- **Preflight health checks**: `--preflight` and `--preflight-fail-fast` flags
- **Status dashboard improvements**: Auto-refresh (30s), SVG favicon, system resource cards, ETA column, cooldown indicator, dark/light mode, compact summary-only mode

---

## [11.7.0] — 2026-06-21

### Added
- **Daemon status API**: `GET /api/status` at webhook port returns full iteration state as JSON
- **Desktop notifications**: `--notify-desktop` via `notify-send` (Linux)
- **Config file support**: `--save-config` and `--config` flags
- **Startup delay**: `--startup-delay N` before first iteration
- **Completion notification**: `--notify-on-completion` sends summary when daemon finishes
- **Error classification**: Iteration errors classified as network/timeout/schema/unknown

---

## [11.6.1] — 2026-06-21

### Fixed
- Missing `logging.handlers` import (crash with `--log-file`)
- `os.sysconf_names` KeyError on some Python builds

---

## [11.6.0] — 2026-06-21

### Added
- Feature banner: comprehensive list including Dashboard v3 SSE, heartbeat, version check
- Output schema validation: `--output-schema` and `--output-schema-file`
- Resource tracking: CPU, memory from `/proc` (Linux)
- Convergence detection: Jaccard word-overlap with adaptive threshold
- Git diff storage: `--store-git-diff` (capped at 10KB)
- Adaptive cooldown: auto-calculated from avg iteration duration
- `run-loop.sh`: Fixed version header, added `--version` flag

---

## [11.5.0] — 2026-06-21

### Added
- Structured output validation (stdlib-only JSON Schema subset)
- Adaptive cooldown mode (`--cooldown-mode adaptive`)
- Convergence detection with Jaccard similarity
- Git diff storage in ledger (capped 10KB per iteration)
- Resource tracking from `/proc` (Linux-only)

---

## [11.4.0] — 2026-06-20

### Added
- `--evolve` mode: Task evolution (auto-propose next goal)
- `--git` flag: Capture git diff per iteration
- `--git-commit` flag: Auto-commit per iteration
- `--workers N`: Parallel execution
- `--notify-cmd`: Post-iteration shell command
- `--max-output-chars`: Output capture size limit
- Signal handling (SIGTERM/SIGINT with temp-file + atomic-rename)
- JSON-safe prompt construction
- ISO 8601 parsing improvements
- `--cooldown` and `--goals-file` flags
- `--stop-at-goals-end` flag

---

## [11.3.0] — 2026-06-20

### Added
- Hermes Worker URL mode (`--worker-url`)
- Embedded Hermes Worker Manager
- Multi-worker context merging

---

## [11.2.0] — 2026-06-20

### Added
- **Webhook mode**: `--webhook-port N` starts HTTP server with POST /webhook, GET /health, GET /status
- **File watcher**: `--watch-dir` and `--watch-poll` for stat-based file change detection
- **Daemon log file**: `--log-file` with rotating file handler
- **Status HTML dashboard**: `--status-html` generates self-contained HTML
- **ETA tracking**: Rolling average + remaining estimate
- `inspect-ledger.sh`: Updated with `--watch` and `--summary` modes

---

## [11.1.0] — 2026-06-19

### Added
- `--no-auto-toolsets`: Disable automatic toolset enrichment
- `--no-failure-learning`: Disable past failure context injection
- `--task-type`: Manual task type override
- **Failure learning**: Inject past failure context into spawned sessions
- **Auto-toolsets**: Detect task type from goal and add relevant tools

---

## [11.0.0] — 2026-06-19

This was a complete rewrite. Previous versions (v1–v10) used `-z` oneshot mode
which broke delegation. v11.0.0 introduced the correct architecture:

### Changed
- Switched from `-z` (oneshot) to `chat -q` (multi-turn session)
- Sessions stay alive for `--max-turns N` (default 500)
- `delegate_task()` subagent results now arrive and are collected
- Multi-line JSON parser with brace-counting extraction
- Stderr capture and filtering

### Added
- `-t terminal,file,delegation` — spawned sessions have direct tools + delegation
- `--max-turns N` — configurable session lifetime
- Sentinels: `stop`/`pause`/`resume` via `/tmp/infinite-loop-stop`
- JSON state ledger at `/tmp/infinite-loop-state.json`
- Archive directory at `~/.hermes/infinite-loop-archives/`
- Self-modification support via `need_reload` signal
- Profile, model, provider overrides
- Context propagation across iterations

---

## [10.0.0] — 2026-06-18

### Changed
- Switched from `-z` oneshot to `hermes chat -q` (core fix)
- `chat -q -t terminal,file,delegation -Q --max-turns N` means sessions stay alive for multiple turns
- `delegate_task()` subagent results can actually arrive and be collected
- Multi-line JSON parsing with brace counting
- Stderr capture separate from stdout

---

## [9.0.0] — 2026-06-17

### Added
- `--on-error-cmd`: Shell command on failed iteration
- `--tag`: Label/identifier for runs
- `--prompt-suffix`: Extra text appended to spawned prompts
- `--force-reset`: Clear existing ledger

---

## [8.0.0] — 2026-06-17

### Changed
- Switched from delegation-only toolset to full tools (`terminal,file,delegation`)
- Fixed delegation results never arriving (sessions exited before subagent results)
- Introduced `--max-retries` for failed iterations

---

## [7.0.0] — 2026-06-16

### Changed
- Complete skill restructuring
- Removed cron-based mode (banned)
- Background daemon is now the sole mode
- Command references updated from `hermes -z` to `hermes -z -t delegation`

---

## [6.0.0] — 2026-06-16

### Changed
- Two-component architecture: daemon (launch-loop.py) for ledger + Hermes session calls delegate_task() directly
- Background daemon mode introduced

---

## [5.0.0] — 2026-06-15

### Changed
- Restructured to daemon + companion Hermes session pattern
- v5.0.0 was semi-functional

---

## [4.0.0] — 2026-06-15

### Added
- Self-contained loop with `--command`, `--task-list`, `--script` modes
- `--hermes-delegate` mode with shared file protocol
- Three autonomous modes

---

## [3.0.0] — 2026-06-14

### Changed
- Two-component architecture: launch-loop.py as ledger daemon + stdin.readline() protocol
- Blocking stdin made it hang (no stdio connected in background terminal)

---

## [2.0.0] — 2026-06-14

### Added
- Background daemon pattern
- Bash wrapper (run-loop.sh) for safety

---

## [1.0.0] — 2026-06-13

### Added
- Initial infinite-loop skill for Hermes Agent
- Basic looping with subprocess spawning
- SKILL.md with standalone component description
