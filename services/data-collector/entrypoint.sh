#!/usr/bin/env bash
set -euo pipefail

# Start a tiny health server on 8086 in background
python - <<'PY' &
import http.server, socketserver, json, time
from datetime import datetime, timezone

class Handler(http.server.BaseHTTPRequestHandler):
    def do_GET(self):
        if self.path.startswith('/health') or self.path == '/':
            self.send_response(200)
            self.send_header('Content-type', 'application/json')
            self.end_headers()
            data = {
                "status": "healthy",
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "service": "marketprism-data-collector",
                "mode": "launcher"
            }
            self.wfile.write(json.dumps(data).encode())
        elif self.path == '/ping':
            self.send_response(200)
            self.send_header('Content-type', 'text/plain')
            self.end_headers()
            self.wfile.write(b'pong')
        else:
            self.send_response(404)
            self.end_headers()
    def log_message(self, fmt, *args):
        # silence access logs
        pass

PORT = 8086
with socketserver.TCPServer(("", PORT), Handler) as httpd:
    httpd.serve_forever()
PY

# Resolve config path with clear precedence
CONFIG_CLI="${COLLECTOR_CONFIG_PATH:-}"
ENV_CONFIG="${MARKETPRISM_UNIFIED_DATA_COLLECTION_CONFIG:-}"
DEFAULT_LOCAL="/app/services/data-collector/config/collector/unified_data_collection.yaml"
DEFAULT_GLOBAL="/app/config/collector/unified_data_collection.yaml"

CONFIG_PATH=""
if [ -n "$CONFIG_CLI" ] && [ -f "$CONFIG_CLI" ]; then
  CONFIG_PATH="$CONFIG_CLI"
elif [ -n "$ENV_CONFIG" ] && [ -f "$ENV_CONFIG" ]; then
  CONFIG_PATH="$ENV_CONFIG"
elif [ -f "$DEFAULT_LOCAL" ]; then
  CONFIG_PATH="$DEFAULT_LOCAL"
elif [ -f "$DEFAULT_GLOBAL" ]; then
  CONFIG_PATH="$DEFAULT_GLOBAL"
else
  echo "[entrypoint] ERROR: No valid config file found. Tried: $CONFIG_CLI, $ENV_CONFIG, $DEFAULT_LOCAL, $DEFAULT_GLOBAL" >&2
  exit 1
fi

MODE="${COLLECTOR_MODE:-launcher}"
echo "[entrypoint] Starting data-collector mode=$MODE config=$CONFIG_PATH"

# Exec the collector main process
exec python /app/services/data-collector/unified_collector_main.py \
  --mode "$MODE" \
  --config "$CONFIG_PATH"
