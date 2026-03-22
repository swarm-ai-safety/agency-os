#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
SITE_DIR="${ROOT_DIR}/site"
MAX_ATTEMPTS=3
REQUIRED_NODE_MAJOR=22
REQUIRED_PACKAGES=(next vitest jsdom @vitest/coverage-v8)
CHECK_ONLY=false

if [[ "${1:-}" == "--check-only" ]]; then
  CHECK_ONLY=true
fi

cd "${ROOT_DIR}"
unset npm_config_auto_install_peers
unset npm_config_recursive

node_major="$(
  node -p "process.versions.node.split('.')[0]" 2>/dev/null || true
)"
if [[ "${node_major}" != "${REQUIRED_NODE_MAJOR}" ]]; then
  NVM_DIR="${NVM_DIR:-${HOME}/.nvm}"
  if [[ -s "${NVM_DIR}/nvm.sh" ]]; then
    # Allow deterministic Node selection in non-interactive shells (e.g. CI agents).
    # shellcheck disable=SC1090
    . "${NVM_DIR}/nvm.sh"
    nvm use "${REQUIRED_NODE_MAJOR}" >/dev/null 2>&1 || true
    node_major="$(
      node -p "process.versions.node.split('.')[0]" 2>/dev/null || true
    )"
  fi
fi

if [[ "${node_major}" != "${REQUIRED_NODE_MAJOR}" ]]; then
  if command -v node >/dev/null 2>&1; then
    node_version="$(node -v)"
  else
    node_version="not installed"
  fi
  echo "Unsupported Node.js version: ${node_version}."
  echo "Use Node ${REQUIRED_NODE_MAJOR}.x for deterministic frontend installs in this repository."
  echo "Tip: run 'nvm use ${REQUIRED_NODE_MAJOR}' before installing site dependencies."
  exit 1
fi

if [[ "${CHECK_ONLY}" == "true" ]]; then
  echo "Node.js version is compatible: $(node -v)"
  exit 0
fi

deps_are_healthy() {
  (
    cd "${SITE_DIR}"
    npm ls --depth=0 "${REQUIRED_PACKAGES[@]}" >/dev/null 2>&1 \
      && npm exec -- vitest --version >/dev/null 2>&1
  ) && [[ -x "${SITE_DIR}/node_modules/.bin/next" \
    && -f "${SITE_DIR}/node_modules/vitest/vitest.mjs" \
    && -f "${SITE_DIR}/node_modules/jsdom/package.json" \
    && -f "${SITE_DIR}/node_modules/@vitest/coverage-v8/package.json" ]]
}

if deps_are_healthy; then
  echo "Site dependencies already present and healthy."
  exit 0
fi

if [[ -d "${SITE_DIR}/node_modules" ]]; then
  mv "${SITE_DIR}/node_modules" "${SITE_DIR}/node_modules.stale.$(date +%s)"
fi

attempt=1
while [[ ${attempt} -le ${MAX_ATTEMPTS} ]]; do
  echo "Installing site dependencies (attempt ${attempt}/${MAX_ATTEMPTS})"

  if (
    cd "${SITE_DIR}"
    npm ci --include=dev --no-audit --no-fund
  ); then
    if deps_are_healthy; then
      echo "Site dependency install completed with integrity checks."
      exit 0
    fi
    echo "Site dependency integrity check failed; retrying install."
  fi

  if [[ -d "${SITE_DIR}/node_modules" ]]; then
    mv "${SITE_DIR}/node_modules" "${SITE_DIR}/node_modules.failed.$(date +%s).${attempt}" || true
  fi

  attempt=$((attempt + 1))
  sleep 2
done

echo "Site dependency install failed after ${MAX_ATTEMPTS} attempts."
exit 1
