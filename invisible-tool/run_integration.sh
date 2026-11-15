#!/usr/bin/env zsh
# Ciclo completo de integración: laboratorio real (3.4.9 y 3.4.10) ->
# verificador -> guardar/recuperar en DynamoDB Local (AWS Emulator).
#
# Referencia: imagen Docker oficial amazon/dynamodb-local, documentada en
# https://docs.aws.amazon.com/amazondynamodb/latest/developerguide/DynamoDBLocal.DownloadingAndRunning.html
# (sección "Run DynamoDB local as Docker image"), publicada en
# https://hub.docker.com/r/amazon/dynamodb-local. En macOS se usa la
# misma imagen bajo Docker Desktop; no hay una ruta nativa separada.
#
# Uso:
#   ./run_integration.sh
#
# Qué hace:
#   1. Arranca un contenedor DynamoDB Local efímero en 127.0.0.1:8000
#      (modo -inMemory, sin persistir datos entre ejecuciones).
#   2. Exporta DDB_LOCAL_ENDPOINT para que integration_test.py lo exija
#      antes de construir cualquier cliente boto3.
#   3. Corre integration_test.py, que a su vez ejecuta server_lab.py +
#      client_matrix.py para fastmcp 3.4.9 y 3.4.10, los pasa por
#      verifier.py, y hace CreateTable/PutItem/GetItem contra el
#      contenedor.
#   4. Apaga y elimina el contenedor al salir (trap), haya pasado o no
#      la prueba.
set -euo pipefail

DIR="$(cd "$(dirname "$0")" && pwd)"
CONTAINER_NAME="ddb-lab-integration"
PORT="${1:-8000}"

cleanup() {
  docker rm -f "$CONTAINER_NAME" >/dev/null 2>&1 || true
}
trap cleanup EXIT

docker rm -f "$CONTAINER_NAME" >/dev/null 2>&1 || true
docker run -d --name "$CONTAINER_NAME" -p "127.0.0.1:${PORT}:8000" \
  amazon/dynamodb-local:latest -jar DynamoDBLocal.jar -sharedDb -inMemory >/dev/null

echo "Esperando DynamoDB Local en 127.0.0.1:${PORT} ..."
for _ in $(seq 1 20); do
  code=$(curl -s -o /dev/null -m 1 -w "%{http_code}" "http://127.0.0.1:${PORT}/" || true)
  if [ -n "$code" ] && [ "$code" != "000" ]; then
    break
  fi
  sleep 0.5
done

export DDB_LOCAL_ENDPOINT="http://127.0.0.1:${PORT}"
echo "DDB_LOCAL_ENDPOINT=${DDB_LOCAL_ENDPOINT}"

uv run --with boto3 --with fastmcp -- python3 "$DIR/integration_test.py"
