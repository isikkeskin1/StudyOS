#!/bin/sh
set -eu

echo '{"event":"startup","phase":"migrations"}'
alembic upgrade head
echo '{"event":"startup","phase":"api"}'

exec uvicorn app.main:app \
  --host 0.0.0.0 \
  --port "${PORT:-8000}" \
  --proxy-headers \
  --forwarded-allow-ips="${STUDYOS_FORWARDED_ALLOW_IPS:-*}" \
  --no-access-log
