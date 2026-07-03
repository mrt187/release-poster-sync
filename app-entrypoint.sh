#!/bin/sh
set -e

CRON_SCHEDULE="${CRON_SCHEDULE:-0 */6 * * *}"

echo "Führe initialen Sync aus..."
python /app/sync.py

echo "Starte Cron-Zeitplan: ${CRON_SCHEDULE}"
printf '%s cd /app && python sync.py >> /proc/1/fd/1 2>> /proc/1/fd/2\n' "${CRON_SCHEDULE}" > /app/crontab.rendered

exec /usr/local/bin/supercronic -no-reap /app/crontab.rendered
