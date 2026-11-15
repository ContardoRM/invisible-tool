#!/usr/bin/env zsh
# Repite la matriz tools/list + tools/call para una versión de FastMCP.
#
# Uso:
#   ./run_matrix.sh 3.4.9
#   ./run_matrix.sh 3.4.10
#
# Cada invocación:
#   1. Lanza server_lab.py en background con esa versión exacta de
#      fastmcp (entorno efímero vía `uv run --with fastmcp==<version>`),
#      en un puerto loopback dedicado.
#   2. Espera a que el puerto responda.
#   3. Ejecuta client_matrix.py (misma identidad de cliente y misma
#      configuración de servidor) con la misma versión de fastmcp.
#   4. Mata el servidor y reporta el código de salida.
set -euo pipefail

VERSION="${1:?Uso: run_matrix.sh <version-fastmcp, p.ej. 3.4.9 o 3.4.10>}"
PORT="${2:-8800}"
DIR="$(cd "$(dirname "$0")" && pwd)"

echo "=== FastMCP ${VERSION} (puerto ${PORT}) ==="

LAB_PORT="$PORT" uv run --with "fastmcp==${VERSION}" -- python3 "$DIR/server_lab.py" \
  > "/tmp/invisible-tool-server-${VERSION}.log" 2>&1 &
SERVER_PID=$!

cleanup() {
  kill "$SERVER_PID" 2>/dev/null || true
  wait "$SERVER_PID" 2>/dev/null || true
}
trap cleanup EXIT

# Esperar a que el servidor loopback responda (máx 15s).
for _ in $(seq 1 30); do
  if curl -s -o /dev/null -m 1 "http://127.0.0.1:${PORT}/mcp"; then
    break
  fi
  sleep 0.5
done

uv run --with "fastmcp==${VERSION}" -- python3 "$DIR/client_matrix.py" "$PORT"
