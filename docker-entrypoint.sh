#!/bin/sh
# Seed the (possibly disk-backed) /app/data with the image's read-only reference
# data. `cp -af .../.` refreshes reference files from the latest deploy; mutable
# runtime files that already live on a mounted persistent disk are NOT part of
# the seed, so they survive redeploys instead of resetting every time.
set -e

if [ -d /app/data_seed ]; then
  mkdir -p /app/data
  cp -af /app/data_seed/. /app/data/ 2>/dev/null || true
fi

# Daily backup loop (ops_backup.py): local rotating snapshot on the persistent
# disk + optional offsite S3 upload when BACKUP_S3_BUCKET is set. Runs in the
# app container because Render disks mount to exactly one service (a separate
# cron service could not see this disk). BACKUP_EVERY_SECONDS=0 disables.
BACKUP_EVERY_SECONDS="${BACKUP_EVERY_SECONDS:-86400}"
if [ "$BACKUP_EVERY_SECONDS" -gt 0 ] 2>/dev/null; then
  (
    while true; do
      python3 ops_backup.py || echo "ops_backup failed (continuing)" >&2
      sleep "$BACKUP_EVERY_SECONDS"
    done
  ) &
fi

# Bind to the platform-provided port (Render/Railway set $PORT); default 8501.
exec streamlit run app.py \
  --server.port="${PORT:-8501}" \
  --server.address=0.0.0.0
