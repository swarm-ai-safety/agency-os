#!/usr/bin/env bash
set -euo pipefail

API_URL="${API_URL:-https://api.zero-human-labs.com}"
EMAIL="${EMAIL:-test@example.com}"
TIMEOUT="${TIMEOUT:-10}"
COMPOSE_FILE="/home/deploy/agency-os/deploy/compose/docker-compose.prod.yml"

need_cmd() {
  command -v "$1" >/dev/null 2>&1 || {
    echo "Missing required command: $1" >&2
    exit 1
  }
}

need_cmd curl

# --- Local checks via Docker compose exec ---
if [[ -f "${COMPOSE_FILE}" ]] && command -v docker >/dev/null 2>&1; then
  echo "Checking API health via Docker compose exec..."
  if ! docker compose -f "${COMPOSE_FILE}" exec -T api curl -sf --max-time "${TIMEOUT}" http://localhost:8000/health; then
    echo "API container health check failed" >&2
    echo "Container status:"
    docker compose -f "${COMPOSE_FILE}" ps api 2>&1 || true
    echo "Recent API logs:"
    docker compose -f "${COMPOSE_FILE}" logs --tail=20 api 2>&1 || true
    exit 1
  fi
  echo "Local health (in-container): OK"

  if ! docker compose -f "${COMPOSE_FILE}" exec -T api curl -sf --max-time "${TIMEOUT}" \
    -X POST -H "Content-Type: application/json" \
    -d "{\"email\":\"${EMAIL}\"}" http://localhost:8000/api/v1/waitlist; then
    echo "Local waitlist endpoint failed inside container" >&2
    exit 1
  fi
  echo ""
  echo "Local waitlist (in-container): OK"
else
  echo "Docker compose not available, skipping local container checks" >&2
fi

# --- Public endpoint checks ---
echo "Checking public endpoint via Caddy (${API_URL})"

body_file="$(mktemp)"
trap 'rm -f "${body_file}"' EXIT

set +e
http_code="$(curl -sS --max-time "${TIMEOUT}" -o "${body_file}" -w "%{http_code}" "${API_URL}/health")"
curl_exit=$?
set -e

if [[ ${curl_exit} -ne 0 ]]; then
  echo "Public health check failed (curl exit ${curl_exit}): ${API_URL}/health" >&2
  rm -f "${body_file}"
  exit 1
fi

echo "Public health HTTP ${http_code}: ${API_URL}/health"
cat "${body_file}"
echo

if [[ "${http_code}" != "200" ]]; then
  echo "Public health returned non-200 status" >&2
  exit 1
fi

set +e
http_code="$(curl -sS --max-time "${TIMEOUT}" -X POST \
  -H "Content-Type: application/json" \
  -d "{\"email\":\"${EMAIL}\"}" \
  -o "${body_file}" \
  -w "%{http_code}" \
  "${API_URL}/api/v1/waitlist")"
curl_exit=$?
set -e

if [[ ${curl_exit} -ne 0 ]]; then
  echo "Public waitlist POST failed (curl exit ${curl_exit})" >&2
  exit 1
fi

echo "Public waitlist HTTP ${http_code}: ${API_URL}/api/v1/waitlist"
cat "${body_file}"
echo

if [[ "${http_code}" != "200" ]]; then
  echo "Public waitlist returned non-200 status" >&2
  exit 1
fi

echo "Verification passed."
