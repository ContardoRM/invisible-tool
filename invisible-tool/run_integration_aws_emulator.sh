#!/usr/bin/env zsh
# Ciclo completo de integración contra el producto oficial AWS Emulator
# (https://docs.aws.amazon.com/emulator/latest/userguide/), siguiendo
# exactamente:
#   - Getting started with Docker:
#     https://docs.aws.amazon.com/emulator/latest/userguide/getting-started-docker.html
#   - Pointing your AWS SDK at AWS Emulator:
#     https://docs.aws.amazon.com/emulator/latest/userguide/point-sdk-to-emulator.html
#
# Build de la imagen (si no existe ya `aws-emulator:latest` local):
#   usa el Dockerfile corto de la guía, con el RPM
#   aws-emulator-aarch64.rpm (Apple Silicon). Para x86_64, cambiar el
#   RPM en build_image().
#
# Arranque del contenedor: publica el puerto SOLO en loopback
# (-p 127.0.0.1:$PORT:$PORT, nunca -p $PORT:$PORT), con límite de
# memoria 2 GiB sin swap, como documenta la guía.
#
# Uso:
#   ./run_integration_aws_emulator.sh [puerto]
#
# Qué hace:
#   1. Construye la imagen `aws-emulator` si no existe localmente.
#   2. Arranca el contenedor en 127.0.0.1:<puerto> (por defecto 9297),
#      compartiendo ~/.aws/emulator con el host para que el SDK lea
#      las credenciales y el CA que el emulador genera al arrancar.
#   3. Exporta STORE_MODE=aws_emulator y AWS_EMULATOR_ENDPOINT para que
#      dynamo_store.py cargue esas credenciales generadas (nunca
#      fijas) y exija HTTPS loopback antes de construir el cliente.
#   4. Corre integration_test.py: ejecuta el laboratorio real
#      (fastmcp 3.4.9 y 3.4.10), verifica, y hace
#      CreateTable/PutItem/GetItem contra el AWS Emulator.
#   5. Detiene el contenedor al salir (haya pasado o no la prueba).
#      El propio emulador borra sus archivos de ~/.aws/emulator/<puerto>/
#      al recibir SIGTERM/Ctrl+C (documentado en la guía).
set -euo pipefail

DIR="$(cd "$(dirname "$0")" && pwd)"
CONTAINER_NAME="aws-emulator-integration"
PORT="${1:-9297}"
IMAGE_NAME="aws-emulator"
RPM_ARCH="aarch64"   # cambiar a x86_64 en hosts Intel/AMD

cleanup() {
  docker rm -f "$CONTAINER_NAME" >/dev/null 2>&1 || true
}
trap cleanup EXIT

build_image_if_missing() {
  if docker image inspect "$IMAGE_NAME" >/dev/null 2>&1; then
    echo "Imagen '${IMAGE_NAME}' ya existe localmente, no se reconstruye."
    return
  fi
  echo "Construyendo imagen '${IMAGE_NAME}' (RPM ${RPM_ARCH})..."
  local build_dir
  build_dir="$(mktemp -d)"
  cat > "${build_dir}/Dockerfile" <<EOF
FROM public.ecr.aws/amazonlinux/amazonlinux:2023-minimal
ADD https://downloads.aws.com/aws-emulator/packages/aws-emulator/LTS/latest/aws-emulator-${RPM_ARCH}.rpm /tmp/aws-emulator.rpm
RUN rpm -i /tmp/aws-emulator.rpm && rm /tmp/aws-emulator.rpm \\
    && mkdir -p /home/emulator && chown 1000 /home/emulator
USER 1000
ENV HOME=/home/emulator
EXPOSE 9297
ENTRYPOINT ["aws-emulator", "-b", "0.0.0.0"]
EOF
  docker build -t "$IMAGE_NAME" "$build_dir"
  rm -rf "$build_dir"
}

build_image_if_missing

docker rm -f "$CONTAINER_NAME" >/dev/null 2>&1 || true

mkdir -p "$HOME/.aws/emulator"
# Borrar el subdirectorio de este puerto para forzar credenciales/CA
# nuevos en cada corrida (evita reutilizar un emulador anterior caído
# a medias).
rm -rf "$HOME/.aws/emulator/${PORT}"

echo "Arrancando AWS Emulator en 127.0.0.1:${PORT} (solo loopback)..."
docker run -d --name "$CONTAINER_NAME" --memory=2g --memory-swap=2g \
  -p "127.0.0.1:${PORT}:${PORT}" \
  -e HOME="$HOME" -v "$HOME/.aws/emulator:$HOME/.aws/emulator" \
  "$IMAGE_NAME" -p "$PORT"

echo "Esperando credenciales generadas en ~/.aws/emulator/${PORT}/ ..."
for _ in $(seq 1 30); do
  if [ -f "$HOME/.aws/emulator/${PORT}/emulator_credentials" ] && [ -f "$HOME/.aws/emulator/${PORT}/ca.pem" ]; then
    break
  fi
  sleep 0.5
done

if [ ! -f "$HOME/.aws/emulator/${PORT}/emulator_credentials" ]; then
  echo "ERROR: el AWS Emulator no generó emulator_credentials a tiempo." >&2
  docker logs "$CONTAINER_NAME" >&2 || true
  exit 1
fi

export STORE_MODE=aws_emulator
export AWS_EMULATOR_ENDPOINT="https://127.0.0.1:${PORT}"
echo "STORE_MODE=${STORE_MODE}"
echo "AWS_EMULATOR_ENDPOINT=${AWS_EMULATOR_ENDPOINT}"

uv run --with boto3 --with fastmcp -- python3 "$DIR/integration_test.py"
