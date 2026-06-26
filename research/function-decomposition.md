# v12.0.0 Structural Refactoring: run_loop() and main() Decomposition

## Problem

The two largest functions in launch-loop.py are:

| Function | Lines | % of file |
|----------|-------|-----------|
| `run_loop()` | 888 | 18.6% |
| `main()` | 821 | 17.2% |
| **Total** | **1709** | **35.7%** |

These two functions alone account for over a third of the entire file. This makes
the code hard to understand, test, and modify. Each new feature requires threading
yet another parameter through these massive functions.

## Proposed Refactoring

### Extracted Functions from `run_loop()` (888 → ~400 lines)

```python
def run_loop(...) -> None:
```

#### Sub-function 1: `_setup_worker(worker_url) -> tuple[WorkerManager, str]`
- Lines 3080-3088: Auto-start worker manager
- Returns: (worker_manager, effective_worker_url)

#### Sub-function 2: `_init_failure_learning(state, failure_learning) -> str`
- Lines 3110-3128: Build failure context from past errors
- Returns: failure_context string

#### Sub-function 3: `_load_goals_file(goals_file) -> list[GoalSpec]`
- Lines 3130-3149: Parse goals file with pipe-separated format support
- Returns: list of (goal, profile_override, model_override, provider_override)

#### Sub-function 4: `_log_startup_banner(...)`
- Lines 3153-3187: Log all daemon configuration
- 35 lines, purely cosmetic

#### Sub-function 5: `_cycle_goal(goals_list, goals_index, stop_at_goals_end) -> tuple[str, bool]`
- Lines 3340-3353: Cycle to next goal, check exhaustion
- Returns: (next_goal, should_stop)

#### Sub-function 6: `_build_progressive_context(context, summaries) -> str`
- Lines 3356-3359: Build progressive context from past summaries
- Returns: context string

#### Sub-function 7: `_execute_iteration(...) -> list[dict]`
- Lines 3380-3497: Execute single or multi-worker iteration
- Returns: all_results

#### Sub-function 8: `_merge_worker_results(all_results) -> tuple`
- Lines 3500-3530: Merge and combine worker results
- Returns: (combined_summary, total_duration, combined_error, next_context, next_goal, combined_output)

#### Sub-function 9: `_detect_convergence(summaries, ...) -> bool`
- Lines 3573-3606: Check convergence criteria
- Returns: True if should stop

#### Sub-function 10: `_compact_summaries(summaries, compact_every, iteration_count) -> list[str]`
- Lines 3612-3631: Compact historical summaries
- Returns: compressed summary list

#### Sub-function 11: `_handle_cooldown(cooldown, cooldown_mode, eta_tracker, task_type)`
- Lines 3852-3872: Adaptive or fixed cooldown with shutdown checks

#### Sub-function 12: `_handle_backoff(combined_error, consecutive_errors, retry_delay, state) -> bool`
- Lines 3874-3888: Exponential backoff on errors
- Returns: True if should stop (on KeyboardInterrupt)

### Extracted Functions from `main()` (821 → ~350 lines)

#### Sub-function 1: `_validate_args(args) -> bool`
- Lines 4426-4447: Validate argument combinations
- Returns: True if valid

#### Sub-function 2: `_run_preflight(args) -> bool`
- Lines 4464-4486: Run preflight checks
- Returns: True if all passed

#### Sub-function 3: `_log_startup_banner(args)`
- Lines 4488-4576: Log all startup configuration
- ~90 lines of print statements

#### Sub-function 4: `_build_state(args, resolved_context) -> dict`
- Lines 4606-4636: Build state dict from args
- Returns: state dict

## Implementation Strategy

Not all at once — implement in phases:

1. **Phase 1** (v12.0.0): Move the most self-contained blocks:
   - `_load_goals_file()` (simplest: pure data transformation)
   - `_log_startup_banner()` (cosmetic only)
   - `_cycle_goal()` (has return value)
   - `_build_progressive_context()` (2 lines of logic)
   - `_handle_cooldown()` (isolated, no return)

2. **Phase 2** (v12.1.0): Move the decision-heavy blocks:
   - `_execute_iteration()` (central spawn logic)
   - `_merge_worker_results()` (data transformation)
   - `_handle_backoff()` (state mutation)

3. **Phase 3** (v12.2.0): Move the rest:
   - `_detect_convergence()`
   - `_compact_summaries()`
   - Remaining chunks

## Expected Benefits

- `run_loop()` shrinks from 888 to ~400 lines (55% reduction)
- `main()` shrinks from 821 to ~350 lines (57% reduction)
- Each sub-function has a single responsibility
- Unit-testable: each function can be tested in isolation
- New features: thread fewer params through run_loop(), add them to the relevant sub-function
- Code review: diffs in sub-functions are smaller and clearer

## Risk Assessment

- **Low risk** for Phase 1 (pure extractions, no logic change)
- **Medium risk** for Phase 2 (the spawn loop is the heart of the daemon)
- **Mitigation**: Add integration tests before refactoring (--dry-run + mock)
- **Rollback**: Each phase is a separate PR — revert is simple
