#!/usr/bin/env bash
set -euo pipefail

APP_DIR="${APP_DIR:-/opt/agency-os}"
ENV_FILE="${ENV_FILE:-/etc/agency-os/api.env}"
SERVICE_NAME="${SERVICE_NAME:-agency-os-api}"

echo "Deploying API from ${APP_DIR}"
cd "${APP_DIR}"

if [[ ! -f "${ENV_FILE}" ]]; then
  echo "Missing env file: ${ENV_FILE}"
  echo "Copy deploy/systemd/api.env.example and set real secrets."
  exit 1
fi

python3 -m venv .venv
./.venv/bin/pip install --upgrade pip
./.venv/bin/pip install -e ".[api,llm,metering]"

sudo install -m 644 deploy/systemd/agency-os-api.service /etc/systemd/system/${SERVICE_NAME}.service
sudo systemctl daemon-reload
sudo systemctl enable --now ${SERVICE_NAME}
sudo systemctl restart ${SERVICE_NAME}

echo "Waiting for local health check..."
for _ in {1..30}; do
  if curl -fsS http://127.0.0.1:8000/health >/dev/null; then
    break
  fi
  sleep 1
done

curl -fsS http://127.0.0.1:8000/health
echo
curl -fsS -X POST http://127.0.0.1:8000/api/v1/waitlist \
  -H "Content-Type: application/json" \
  -d '{"email":"test@example.com"}'
echo

echo "If Caddy is host-installed, validate and reload:"
echo "  sudo caddy validate --config /etc/caddy/Caddyfile"
echo "  sudo systemctl reload caddy"
