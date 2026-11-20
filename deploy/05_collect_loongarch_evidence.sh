#!/usr/bin/env bash
# Collect reproducible LoongArch/Kylin deployment and 8-hour stability evidence.
set -euo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT="$(dirname "$HERE")"
ARCH="$(uname -m)"
DURATION_SECONDS="${DURATION_SECONDS:-28800}"
INTERVAL_SECONDS="${INTERVAL_SECONDS:-60}"
HEALTH_URL="${HEALTH_URL:-http://127.0.0.1:8000/api/health}"
STAMP="$(date -u +%Y%m%dT%H%M%SZ)"
OUT="${EVIDENCE_OUTPUT_DIR:-$ROOT/evidence/loongarch/run-$STAMP}"

case "$ARCH" in
  loongarch64|loong64) ;;
  *)
    if [[ "${ALLOW_NON_LOONGARCH:-0}" != "1" ]]; then
      echo "refusing to create LoongArch evidence on architecture: $ARCH" >&2
      echo "set ALLOW_NON_LOONGARCH=1 only for script rehearsal; do not use it as competition evidence" >&2
      exit 2
    fi
    ;;
esac

mkdir -p "$OUT"
exec > >(tee "$OUT/collector.log") 2>&1

echo "Collecting evidence in $OUT"
date -u +%FT%TZ > "$OUT/started_at.txt"
uname -a > "$OUT/uname.txt"
printf '%s\n' "$ARCH" > "$OUT/architecture.txt"
cp /etc/os-release "$OUT/os-release.txt"
lscpu > "$OUT/lscpu.txt" 2>&1 || true
free -h > "$OUT/memory.txt" 2>&1 || true
df -h > "$OUT/filesystems.txt" 2>&1 || true

systemctl status device-repair-backend --no-pager > "$OUT/backend-service.txt" 2>&1 || true
systemctl status nginx --no-pager > "$OUT/nginx-service.txt" 2>&1 || true
journalctl -u device-repair-backend -n 300 --no-pager > "$OUT/backend-journal-start.txt" 2>&1 || true
nginx -T > "$OUT/nginx-config.txt" 2>&1 || true

PYTHON="$ROOT/backend/.venv/bin/python"
[[ -x "$PYTHON" ]] || PYTHON="$(command -v python3)"
"$PYTHON" --version > "$OUT/python-version.txt" 2>&1
"$PYTHON" -m pip freeze --all > "$OUT/python-freeze.txt" 2>&1
"$PYTHON" -m pip check > "$OUT/python-pip-check.txt" 2>&1
"$PYTHON" "$HERE/generate_sbom.py" --output "$OUT/sbom.cdx.json"

{
  find "$ROOT/backend" "$ROOT/deploy" -maxdepth 2 -type f \
    \( -name 'requirements*.txt' -o -name '*.py' -o -name '*.sh' -o -name '*.sql' \) -print0
  find "$ROOT/frontend/dist" -type f -print0 2>/dev/null || true
  find "$ROOT/release" -type f -print0 2>/dev/null || true
} | sort -z | xargs -0 -r sha256sum > "$OUT/artifacts.sha256"

printf 'timestamp_utc,http_status,latency_seconds,result\n' > "$OUT/health.csv"
deadline=$(( $(date +%s) + DURATION_SECONDS ))
checks=0
failures=0
while (( $(date +%s) < deadline )); do
  now="$(date -u +%FT%TZ)"
  metrics="$(curl -sS -o "$OUT/health-last.json" -w '%{http_code},%{time_total}' \
    --max-time 15 "$HEALTH_URL" 2>"$OUT/health-last-error.txt" || true)"
  status="${metrics%%,*}"
  latency="${metrics#*,}"
  result="ok"
  if [[ "$status" != "200" ]] || ! grep -q '"status"[[:space:]]*:[[:space:]]*"ok"' "$OUT/health-last.json"; then
    result="failed"
    failures=$((failures + 1))
  fi
  printf '%s,%s,%s,%s\n' "$now" "${status:-000}" "${latency:-0}" "$result" >> "$OUT/health.csv"
  checks=$((checks + 1))
  sleep "$INTERVAL_SECONDS"
done

curl -fsS http://127.0.0.1:8000/metrics > "$OUT/prometheus-final.txt" 2>&1 || true
journalctl -u device-repair-backend --since "$(cat "$OUT/started_at.txt")" --no-pager \
  > "$OUT/backend-journal-full.txt" 2>&1 || true
date -u +%FT%TZ > "$OUT/finished_at.txt"

cat > "$OUT/summary.json" <<JSON
{
  "architecture": "$ARCH",
  "duration_seconds": $DURATION_SECONDS,
  "interval_seconds": $INTERVAL_SECONDS,
  "health_checks": $checks,
  "health_failures": $failures,
  "passed": $([[ $failures -eq 0 ]] && echo true || echo false)
}
JSON

echo "Health checks: $checks; failures: $failures"
[[ $failures -eq 0 ]]
