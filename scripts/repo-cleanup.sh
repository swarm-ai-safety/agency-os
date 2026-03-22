#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(git rev-parse --show-toplevel)"
cd "$ROOT_DIR"

targets=(
  "site/coverage"
  ".pytest_cache"
  ".mypy_cache"
  ".ruff_cache"
  "htmlcov"
  ".coverage"
  ".next"
)

removed_any=0
for target in "${targets[@]}"; do
  if [ -e "$target" ]; then
    rm -rf "$target"
    echo "Removed $target"
    removed_any=1
  fi
done

if [ "$removed_any" -eq 0 ]; then
  echo "No cleanup targets found."
fi
