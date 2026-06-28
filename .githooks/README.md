# Git Hooks

This directory contains project-local git hooks used for the infinite-loop daemon.

## Installing

```bash
# Option A: Use the Makefile target (recommended)
make install-hooks

# Option B: Git's core.hooksPath (avoids copying — hooks stay version-controlled)
git config core.hooksPath .githooks

# Option C: Manually copy
cp .githooks/* .git/hooks/
find .githooks -type f -exec chmod +x {} \;
```

## Available Hooks

| Hook | Trigger | What it does |
|------|---------|-------------|
| `pre-commit` | `git commit` | Regenerates `scripts/completion/{bash,zsh}` from the live argparse parser. Stages changed files automatically. |

## Why `.githooks/` Instead of `.git/hooks/`?

Files committed to `.githooks/` are version-controlled and shared with all
contributors. `.git/hooks/` is local-only and not tracked by git.

Using `git config core.hooksPath .githooks` avoids the cp/rsync step — git
runs hooks directly from the version-controlled directory.
