# Pre-Commit Hook Setup Guide

This guide explains how to set up and use the pre-commit hooks for GUARD.

---

## Overview

GUARD has **two pre-commit hook options**:

1. **Pre-commit Framework** (Recommended) - Uses `.pre-commit-config.yaml`
2. **Simple Git Hook** (Backup) - Direct git hook in `.git/hooks/pre-commit`

Both use **Poetry** to run ruff, ensuring reliable linting without global install issues.

---

## Option 1: Pre-commit Framework (Recommended)

### Installation

```bash
# Install pre-commit hooks
poetry run pre-commit install

# Verify installation
poetry run pre-commit --version
```

### Usage

**Automatic:** Hooks run automatically on `git commit`

**Manual run on all files:**
```bash
poetry run pre-commit run --all-files
```

**Manual run on specific files:**
```bash
poetry run pre-commit run --files src/guard/cli/main.py
```

**Update hook versions:**
```bash
poetry run pre-commit autoupdate
```

**Skip hooks (emergency only):**
```bash
git commit --no-verify -m "message"
```

### What Gets Checked

1. **Ruff Linting** - Fast Python linter (auto-fixes issues)
2. **Ruff Formatting** - Code formatter (auto-formats)
3. **MyPy Type Checking** - Static type analysis (src/ only)
4. **YAML/JSON/TOML Validation** - Syntax checks
5. **Trailing Whitespace** - Auto-removed
6. **End of File Fixer** - Ensures newline at EOF
7. **No Commits to Main** - Prevents direct commits to main/master
8. **Large Files Check** - Prevents >1MB files
9. **Merge Conflict Check** - Detects conflict markers
10. **Private Key Detection** - Security check
11. **Secrets Detection** - Scans for API keys, tokens, etc.

---

## Option 2: Simple Git Hook (Already Active)

The simple git hook is **already installed and active** at `.git/hooks/pre-commit`.

### What It Does

- Runs `poetry run ruff check --fix` (auto-fixes issues)
- Runs `poetry run ruff format` (auto-formats code)
- Runs `poetry run mypy` on src/ files only
- Shows colored output with clear pass/fail
- Warns about TODO comments (doesn't fail)

### Usage

**Automatic:** Runs on every `git commit`

**Skip (emergency only):**
```bash
git commit --no-verify -m "message"
```

### Manual Commands

If pre-commit fails, run these to fix issues:

```bash
# Fix linting issues
poetry run ruff check . --fix

# Format code
poetry run ruff format .

# Type check
poetry run mypy src/

# Run all checks
poetry run ruff check . --fix && poetry run ruff format . && poetry run mypy src/
```

---

## Troubleshooting

### Issue: "Command not found: ruff"

**Cause:** Ruff not installed in Poetry environment

**Fix:**
```bash
poetry install
```

### Issue: "poetry: command not found"

**Cause:** Poetry not installed or not in PATH

**Fix:**
```bash
# Install Poetry (official method)
curl -sSL https://install.python-poetry.org | python3 -

# Or via Homebrew (macOS)
brew install poetry
```

### Issue: Pre-commit hook fails with "No module named 'guard'"

**Cause:** Poetry environment not activated or corrupted

**Fix:**
```bash
# Reinstall dependencies
poetry install

# Verify environment
poetry run python -c "import guard; print('OK')"
```

### Issue: Hook takes too long

**Solution 1:** Run checks on staged files only (already default)

**Solution 2:** Skip type checking on large commits:
```bash
SKIP=mypy git commit -m "message"
```

**Solution 3:** Use simple git hook instead of pre-commit framework

### Issue: MyPy fails with import errors

**Cause:** Type stubs not installed

**Fix:**
```bash
poetry install --with dev
```

### Issue: Hook conflicts with gcmwm command

The `.git/hooks/pre-commit` hook runs **before** `gcmwm` formatting.

**Workflow:**
```bash
# 1. Stage your changes
git add .

# 2. Pre-commit hook runs automatically and fixes issues
# 3. gcmwm will commit with proper message format
gcmwm "your commit message"
```

If pre-commit fails:
```bash
# Fix the issues
poetry run ruff check . --fix
poetry run ruff format .

# Re-add fixed files
git add .

# Try commit again
gcmwm "your commit message"
```

---

## Configuration

### Ruff Configuration

Edit `pyproject.toml` section `[tool.ruff]`:

```toml
[tool.ruff]
target-version = "py311"
line-length = 100  # Adjust line length

[tool.ruff.lint]
select = ["E", "W", "F", "I", "B", "C4", "UP", "ARG", "SIM", "TCH", "PTH", "RUF"]
ignore = ["E501"]  # Add rules to ignore
```

### MyPy Configuration

Edit `pyproject.toml` section `[tool.mypy]`:

```toml
[tool.mypy]
disallow_untyped_defs = true  # Require type hints
warn_unused_ignores = true    # Warn on unnecessary ignores
```

### Pre-commit Configuration

Edit `.pre-commit-config.yaml`:

```yaml
repos:
  - repo: https://github.com/astral-sh/ruff-pre-commit
    rev: v0.2.2  # Update version
    hooks:
      - id: ruff
        args: [--fix, --exit-non-zero-on-fix]  # Customize args
```

---

## Best Practices

### 1. Run Checks Before Staging

```bash
# Check files before staging
poetry run ruff check src/

# Format before staging
poetry run ruff format src/

# Then stage
git add src/
```

### 2. Fix Issues Incrementally

Don't stage all files at once. Stage and commit by feature/fix:

```bash
git add src/guard/cli/main.py
git commit -m "fix: update CLI help text"

git add tests/unit/test_cli.py
git commit -m "test: add CLI help text tests"
```

### 3. Use Ruff's Auto-Fix

Most issues can be auto-fixed:

```bash
# Fix everything
poetry run ruff check . --fix

# Preview changes
poetry run ruff check . --diff
```

### 4. Skip Hooks Sparingly

Only skip hooks for:
- Emergency hotfixes
- Work-in-progress commits (local branches)
- Generated code

**Never skip on:**
- Main/master branch
- Pull request commits
- Release commits

### 5. Keep Pre-commit Updated

```bash
# Update quarterly
poetry run pre-commit autoupdate

# Test after update
poetry run pre-commit run --all-files
```

---

## CI/CD Integration

The same checks should run in CI/CD:

```yaml
# .gitlab-ci.yml example
lint:
  stage: test
  script:
    - poetry install
    - poetry run ruff check .
    - poetry run ruff format --check .
    - poetry run mypy src/
```

---

## Disabling Hooks

### Temporarily Disable (One Commit)

```bash
git commit --no-verify -m "WIP: work in progress"
```

### Disable Simple Git Hook

```bash
rm .git/hooks/pre-commit
```

### Disable Pre-commit Framework

```bash
poetry run pre-commit uninstall
```

### Re-enable

```bash
poetry run pre-commit install
```

---

## Performance Tips

### 1. Use Ruff Instead of Multiple Tools

Ruff replaces:
- flake8
- isort
- pyupgrade
- autopep8
- And 50+ other tools

**Much faster!**

### 2. Exclude Generated Files

Edit `.pre-commit-config.yaml`:

```yaml
exclude: |
  (?x)^(
    htmlcov/.*|
    build/.*|
    dist/.*
  )$
```

### 3. Cache Pre-commit

Pre-commit caches hook environments. To clear:

```bash
poetry run pre-commit clean
poetry run pre-commit gc
```

---

## Quick Reference

### Commands

| Command | Description |
|---------|-------------|
| `poetry run ruff check .` | Lint all files |
| `poetry run ruff check . --fix` | Lint and auto-fix |
| `poetry run ruff format .` | Format all files |
| `poetry run mypy src/` | Type check source |
| `poetry run pre-commit run --all-files` | Run all hooks |
| `git commit --no-verify` | Skip hooks |

### Ruff Rules

| Code | Description |
|------|-------------|
| E | pycodestyle errors |
| W | pycodestyle warnings |
| F | pyflakes |
| I | isort (import sorting) |
| B | flake8-bugbear |
| UP | pyupgrade |
| ARG | unused arguments |
| SIM | simplify |
| RUF | ruff-specific |

### Exit Codes

| Code | Meaning |
|------|---------|
| 0 | All checks passed |
| 1 | Some checks failed |

---

## Getting Help

**Ruff:**
```bash
poetry run ruff --help
poetry run ruff check --help
poetry run ruff format --help
```

**Pre-commit:**
```bash
poetry run pre-commit --help
poetry run pre-commit run --help
```

**Project-specific:**
- See: `CLAUDE.md` for development commands
- See: `README.md` for general info
- See: `docs/contributing.md` for contribution guidelines

---

## Summary

✅ **Pre-commit hooks are set up and ready!**

**Two options available:**
1. Pre-commit framework (`.pre-commit-config.yaml`) - More features
2. Simple git hook (`.git/hooks/pre-commit`) - Already active

**Both use:** `poetry run` commands to avoid global install issues

**Auto-fixes:** Most linting and formatting issues

**Manual fixes:** Run `poetry run ruff check . --fix` and `poetry run ruff format .`

**Skip hooks:** `git commit --no-verify` (use sparingly)

---

**Next Steps:**

1. Test the hooks:
   ```bash
   # Make a small change
   echo "# Test" >> README.md

   # Stage and commit
   git add README.md
   git commit -m "test: verify pre-commit hooks"

   # Hooks should run automatically
   ```

2. If hooks don't run, install pre-commit framework:
   ```bash
   poetry run pre-commit install
   ```

3. Run checks on all files:
   ```bash
   poetry run pre-commit run --all-files
   ```

**You're all set!** 🎉
