#!/usr/bin/env bash
set -euo pipefail

# Deploy the web/API service on a Linux server without requiring Docker Compose.
# The named volume preserves recordings and SQLite data across container updates.
docker build -t meeting-terminal:latest .
docker rm -f meeting-terminal 2>/dev/null || true
docker run -d \
  --name meeting-terminal \
  --restart unless-stopped \
  --publish 8090:8090 \
  --volume meeting_data:/data \
  meeting-terminal:latest
docker ps --filter name=meeting-terminal
