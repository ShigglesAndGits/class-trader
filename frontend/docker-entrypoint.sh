#!/bin/sh
# Replace the build-time placeholder with the real API URL from the environment.
# This runs once at container startup before nginx takes over.
set -e

PLACEHOLDER="__VITE_API_URL__"
TARGET="${VITE_API_URL:-http://localhost:8000}"

echo "Configuring API URL: ${TARGET}"
find /usr/share/nginx/html -name "*.js" \
  -exec sed -i "s|${PLACEHOLDER}|${TARGET}|g" {} \;

exec "$@"
