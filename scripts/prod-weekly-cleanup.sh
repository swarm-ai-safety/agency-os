#!/usr/bin/env bash
set -euo pipefail

LOG_DIR="${LOG_DIR:-/home/deploy/agency-os/logs}"
LOG_RETENTION_DAYS="${LOG_RETENTION_DAYS:-84}"
mkdir -p "${LOG_DIR}"

ts="$(date -u +%Y%m%d-%H%M%S)"
log_file="${LOG_DIR}/prod-cleanup-${ts}.log"

exec > >(tee -a "${log_file}") 2>&1

echo "[$(date -u +%FT%TZ)] Starting weekly cleanup"
echo "Host: $(hostname)"
echo

echo "Disk usage before:"
df -h /
echo

echo "Removing stale buildx builders..."
while read -r builder_name; do
  if [[ -n "${builder_name}" ]]; then
    echo " - removing ${builder_name}"
    docker buildx rm -f "${builder_name}" || true
  fi
done < <(docker buildx ls | awk 'NR > 1 {print $1}' | sed 's/*//g' | grep '^builder-' || true)
echo

echo "Pruning unused Docker artifacts..."
docker system prune -af --volumes || true
echo

echo "Pruning CI and package caches..."
rm -rf \
  /home/deploy/.cache/trivy \
  /home/deploy/.npm/_cacache \
  /home/deploy/actions-runner/_work/* \
  /home/deploy/actions-runner-2/_work/* \
  /home/deploy/actions-runner-3/_work/* 2>/dev/null || true
echo

echo "Vacuuming journald logs to 7 days..."
sudo journalctl --vacuum-time=7d >/dev/null 2>&1 || true
echo

echo "Pruning cleanup logs older than ${LOG_RETENTION_DAYS} days..."
find "${LOG_DIR}" -maxdepth 1 -type f -name 'prod-cleanup-*.log' -mtime +"${LOG_RETENTION_DAYS}" -delete || true
echo

echo "Disk usage after:"
df -h /
echo

echo "Docker usage after:"
docker system df || true
echo

echo "[$(date -u +%FT%TZ)] Cleanup complete"
echo "Log: ${log_file}"
