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

# Bind to the platform-provided port (Render/Railway set $PORT); default 8501.
exec streamlit run app.py \
  --server.port="${PORT:-8501}" \
  --server.address=0.0.0.0
