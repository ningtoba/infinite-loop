# Multi-Profile Goals File Feature Research

## Summary

Research for adding multi-profile/model/provider support to the infinite-loop
daemon's goals file (`--goals-file`). Each goal line can optionally specify a
profile, model, and provider as pipe-separated fields, enabling heterogeneous
spawned sessions from a single run.

## Current Goals File Behavior

- `load_goals()` at lines 3133-3149 reads a text file, one goal per line
- Lines starting with `#` are ignored as comments
- All goals share the same `profile`, `model`, `provider` (daemon defaults)
- Goals cycle via `goals_index % len(goals_list)` (lines 3340-3353)
- When `--workers > 1`, each worker gets the next goal from the list cyclically
  (lines 3389-3391)

## Proposed Format

```
goal text
goal text|profile_name
goal text||model_name
goal text|||provider_name
goal text|profile_name|model_name|provider_name
```

Pipe-separated fields (in order): `goal|profile|model|provider`
- Empty fields fall back to the daemon's CLI args
- Plain lines (no pipes) use daemon defaults (backward compatible)
- All pipes must be present or none? **Design decision**: parse explicit pipes
  only — a line with pipes is split; a line without is kept as-is.

## Implementation Plan

### 1. Modify `load_goals()` parsing (lines 3133-3149)

```python
class GoalSpec:
    """A goal with optional profile/model/provider overrides."""
    def __init__(self, goal: str, profile: str = "", model: str = "",
                 provider: str = ""):
        self.goal = goal
        self.profile = profile
        self.model = model
        self.provider = provider

    def __str__(self):
        return self.goal[:60]

# In run_loop(), replace:
#   goals_list = [goal]
# with:
goals_list: list[GoalSpec] = [GoalSpec(goal)]  # Always include the primary goal

# In load_goals():
if goals_file:
    with open(goals_file) as gf:
        raw_lines = gf.read().strip().split("\n")
    parsed = []
    for ln in raw_lines:
        ln = ln.strip()
        if not ln or ln.startswith("#"):
            continue
        if "|" in ln:
            parts = ln.split("|", 3)
            parsed.append(GoalSpec(
                goal=parts[0].strip(),
                profile=parts[1].strip() if len(parts) > 1 and parts[1].strip() else "",
                model=parts[2].strip() if len(parts) > 2 and parts[2].strip() else "",
                provider=parts[3].strip() if len(parts) > 3 and parts[3].strip() else "",
            ))
        else:
            parsed.append(GoalSpec(ln))
    if parsed:
        goals_list = parsed
```

### 2. Modify per-worker spawn (lines 3386-3428)

Current: every worker uses `profile=profile, model=model, provider=provider`

Replace with per-goal overrides:

```python
for w_id in range(workers):
    worker_goal_spec = spawn_goal
    if len(goals_list) > 1:
        idx = (goals_index + w_id) % len(goals_list)
        worker_goal_spec = goals_list[idx]

    # Merge daemon-level with goal-level overrides
    effective_profile = worker_goal_spec.profile or profile
    effective_model = worker_goal_spec.model or model
    effective_provider = worker_goal_spec.provider or provider

    fut = executor.submit(
        spawn_delegation_session,
        goal=worker_goal_spec.goal,
        ...
        profile=effective_profile,
        model=effective_model,
        provider=effective_provider,
    )
```

### 3. Modify single-execution path (lines 3451-3495)

The single-execution path accesses `spawn_goal` as:
```python
spawn_goal = current_goal if len(goals_list) > 1 else goal
```

Wrap current_goal selection to also extract profile/model/provider overrides:

```python
# After cycle goals
if len(goals_list) > 1:
    current_goal_spec = goals_list[goals_index % len(goals_list)]
    goals_index += 1
else:
    current_goal_spec = goals_list[0]

# In single execution:
result = spawn_delegation_session(
    goal=current_goal_spec.goal,
    ...
    profile=current_goal_spec.profile or profile,
    model=current_goal_spec.model or model,
    provider=current_goal_spec.provider or provider,
    ...
)
```

### 4. Modify the goals cycling logic (lines 3340-3353)

Add warning when profile/model/provider vary across goals:

```python
# After loading goals
unique_profiles = {gs.profile for gs in goals_list if gs.profile}
unique_models = {gs.model for gs in goals_list if gs.model}
if len(unique_profiles) > 1:
    _log(f"[GOALS] {len(unique_profiles)} different profiles across goals: {unique_profiles}")
```

### 5. Update run-loop.sh

No changes needed — the pipe-separated format is a file format feature, not a CLI flag.

### 6. Update SKILL.md

Document the pipe-separated goals file format with examples.

## Edge Cases

1. **Empty pipes**: `goal|||` — all fields empty, use daemon defaults
2. **Trailing pipes**: `goal|work|` — profile=work, model empty (daemon default)
3. **Spaces in pipes**: `goal | work | claude-sonnet-4 |` — strip whitespace
4. **Comment lines**: `# profile=work` — ignored as before
5. **Mixed format**: Some lines with pipes, some without — backward compatible
6. **Validation**: Warn if a profile/model/provider doesn't exist but don't fail
   (Hermes will fail naturally on spawn)

## Files to Modify

| File | Change | Lines |
|------|--------|-------|
| scripts/launch-loop.py | GoalSpec class, parse changes, spawn changes | ~80 |
| SKILL.md | Document pipe-separated format, examples | ~30 |

## Backward Compatibility

- Plain goals files (no pipes) work exactly as before
- No new CLI flags needed — purely a file format extension
- Old runs with existing goals files: no change

## Testing

1. Create a goals file with 3 pipe-separated goals
2. Run with `--dry-run` to verify the parsing
3. Run with `--workers 3` to verify per-worker overrides
4. Run with `--stop-at-goals-end` to verify goal exhaustion still works
