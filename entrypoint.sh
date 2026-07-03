#!/bin/sh
set -e

PUID="${PUID:-99}"
PGID="${PGID:-100}"

groupmod -o -g "$PGID" appuser 2>/dev/null || (getent group "$PGID" || groupadd -g "$PGID" appgroup)
usermod -o -u "$PUID" -g "$PGID" appuser 2>/dev/null || true

chown -R "$PUID:$PGID" /app /posters

exec setpriv --reuid="$PUID" --regid="$PGID" --init-groups /app/app-entrypoint.sh
