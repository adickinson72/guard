#!/bin/bash

echo "Running pre-commit checks on all changed files..."

# Get all modified/staged files
CHANGED_FILES=$(git diff --name-only HEAD; git diff --cached --name-only)

if [ -z "$CHANGED_FILES" ]; then
    echo "No files changed, skipping pre-commit checks"
    exit 0
fi

# Run pre-commit on all changed files
echo "$CHANGED_FILES" | xargs pre-commit run --files

if [ $? -ne 0 ]; then
    echo ""
    echo "❌ Pre-commit checks failed!"
    echo "Claude has finished its work, but there are issues to fix."
    echo "You can ask Claude to fix these pre-commit failures."
    exit 1
else
    echo "✅ All pre-commit checks passed!"
    exit 0
fi