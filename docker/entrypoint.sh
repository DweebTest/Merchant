#!/bin/sh
# Bring the database schema up to date, load default lists, then start the app.
set -e

tries=0
until flask db upgrade; do
  tries=$((tries + 1))
  if [ "$tries" -ge 30 ]; then
    echo "Database still unreachable after $tries attempts; giving up." >&2
    exit 1
  fi
  echo "Waiting for the database ($tries)..."
  sleep 2
done

flask seed
exec "$@"
