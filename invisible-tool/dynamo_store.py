"""
Persistencia de informes del verificador en un emulador local de
DynamoDB. Soporta dos modos EXPLÍCITOS, seleccionados por la variable
de entorno STORE_MODE:

  - STORE_MODE=dynamodb_local (por defecto, retrocompatible): usa
    DynamoDB Local (imagen `amazon/dynamodb-local`), con credenciales
    ficticias FIJAS (documentadas por la guía oficial de AWS:
    "fakeMyKeyId" / "fakeSecretAccessKey") y endpoint HTTP exigido vía
    DDB_LOCAL_ENDPOINT.

  - STORE_MODE=aws_emulator: usa el producto oficial AWS Emulator
    (https://docs.aws.amazon.com/emulator/latest/userguide/), que GENERA
    sus propias credenciales y un certificado CA cada vez que arranca,
    documentado en
    https://docs.aws.amazon.com/emulator/latest/userguide/point-sdk-to-emulator.html:

      "When the emulator starts, it generates a new access key ID and
      secret access key. It writes them, a config file for your SDK,
      and its certificate (ca.pem, ...) to a subdirectory of
      ~/.aws/emulator/ named for its port, for example
      ~/.aws/emulator/9297/."

    Este modo NO usa credenciales fijas: lee
    ~/.aws/emulator/<port>/emulator_credentials y
    ~/.aws/emulator/<port>/ca.pem generados por el propio emulador en
    tiempo de ejecución, y exige el endpoint HTTPS loopback
    correspondiente.

Requisitos de seguridad comunes a ambos modos:
  - El endpoint local es obligatorio. Si falta, el script debe
    detenerse ANTES de construir cualquier cliente boto3, para que
    nunca exista la posibilidad de que un cliente mal configurado
    termine apuntando a un endpoint real de AWS.
  - No se persisten tokens ni cuerpos de respuesta MCP crudos: el ítem
    guardado es el documento ya reducido que produce verifier.py
    (versión, caso, veredicto, evidencia mínima).
  - En modo aws_emulator, el secret access key generado se lee en
    memoria para firmar las peticiones, pero nunca se imprime ni se
    guarda en el log de llamadas (ver _log_call: solo guarda
    nombre/estado/detalle estructurado, no credenciales).
"""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path
from typing import Any

TABLE_NAME = "invisible_tool_reports"

# --- Modo dynamodb_local: credenciales ficticias fijas, documentadas
# por la guía oficial de AWS para DynamoDB Local. ---
FAKE_ACCESS_KEY = "fakeMyKeyId"
FAKE_SECRET_KEY = "fakeSecretAccessKey"
FAKE_REGION = "fakeRegion"


class MissingLocalEndpointError(RuntimeError):
    """Se lanza si falta la configuración de endpoint local requerida
    por el modo activo. Debe lanzarse antes de importar boto3 a nivel
    de uso real o de construir un cliente, para que nunca se intente
    contactar a AWS real."""


def _reject_if_real_aws(endpoint: str) -> None:
    if "amazonaws.com" in endpoint:
        raise MissingLocalEndpointError(
            f"El endpoint '{endpoint}' parece un endpoint real de AWS, no "
            "local. Abortando por seguridad."
        )


def _require_loopback_https(endpoint: str) -> None:
    """El modo aws_emulator exige HTTPS y host loopback explícito,
    como documenta la guía oficial (AWS_ENDPOINT_URL=https://127.0.0.1:PORT)."""
    if not endpoint.startswith("https://127.0.0.1:") and not endpoint.startswith("https://localhost:"):
        raise MissingLocalEndpointError(
            f"AWS_EMULATOR_ENDPOINT='{endpoint}' debe ser HTTPS sobre "
            "loopback explícito, p. ej. https://127.0.0.1:9297. El AWS "
            "Emulator sirve siempre HTTPS con su propio certificado; un "
            "endpoint HTTP o no loopback se rechaza antes de crear el "
            "cliente."
        )


def get_store_mode() -> str:
    mode = os.environ.get("STORE_MODE", "dynamodb_local").strip()
    if mode not in ("dynamodb_local", "aws_emulator"):
        raise MissingLocalEndpointError(
            f"STORE_MODE='{mode}' no es válido. Usa 'dynamodb_local' o "
            "'aws_emulator'."
        )
    return mode


def require_local_endpoint() -> str:
    """Valida la configuración de endpoint local para el modo activo
    (STORE_MODE) y la devuelve. No construye ningún cliente boto3."""
    mode = get_store_mode()
    if mode == "dynamodb_local":
        endpoint = os.environ.get("DDB_LOCAL_ENDPOINT")
        if not endpoint:
            raise MissingLocalEndpointError(
                "DDB_LOCAL_ENDPOINT no está definido. Abortando antes de "
                "crear un cliente DynamoDB: no se intentará contactar un "
                "endpoint real de AWS. Define, por ejemplo, "
                "DDB_LOCAL_ENDPOINT=http://127.0.0.1:8000"
            )
        _reject_if_real_aws(endpoint)
        return endpoint

    # mode == "aws_emulator"
    endpoint = os.environ.get("AWS_EMULATOR_ENDPOINT")
    if not endpoint:
        raise MissingLocalEndpointError(
            "STORE_MODE=aws_emulator pero AWS_EMULATOR_ENDPOINT no está "
            "definido. Abortando antes de crear un cliente DynamoDB: no "
            "se intentará contactar un endpoint real de AWS. Define, por "
            "ejemplo, AWS_EMULATOR_ENDPOINT=https://127.0.0.1:9297"
        )
    _reject_if_real_aws(endpoint)
    _require_loopback_https(endpoint)
    return endpoint


def _load_emulator_credentials(port: str) -> tuple[str, str, str]:
    """Lee las credenciales y el CA GENERADOS por el AWS Emulator en
    ~/.aws/emulator/<port>/, como documenta point-sdk-to-emulator.html.
    No hay credenciales fijas en este modo: si los archivos no existen
    (el emulador no corrió, o corrió con otro puerto), falla con un
    error explícito en vez de usar un valor por defecto."""
    base = Path(os.environ.get("AWS_EMULATOR_HOME_DIR", str(Path.home() / ".aws" / "emulator"))) / port
    creds_file = base / "emulator_credentials"
    ca_file = base / "ca.pem"

    if not creds_file.exists():
        raise MissingLocalEndpointError(
            f"No se encontró '{creds_file}'. El AWS Emulator genera este "
            "archivo al arrancar (ver point-sdk-to-emulator.html); si no "
            "existe, el emulador no está corriendo en este puerto, o "
            "corrió con un HOME distinto. Abortando antes de crear un "
            "cliente boto3."
        )
    if not ca_file.exists():
        raise MissingLocalEndpointError(
            f"No se encontró el certificado CA generado '{ca_file}'. "
            "Sin él no se puede validar la conexión HTTPS del emulador "
            "de forma segura. Abortando antes de crear un cliente boto3."
        )

    access_key = None
    secret_key = None
    for line in creds_file.read_text().splitlines():
        line = line.strip()
        if line.startswith("aws_access_key_id"):
            access_key = line.split("=", 1)[1].strip()
        elif line.startswith("aws_secret_access_key"):
            secret_key = line.split("=", 1)[1].strip()

    if not access_key or not secret_key:
        raise MissingLocalEndpointError(
            f"'{creds_file}' no contiene aws_access_key_id/aws_secret_access_key "
            "legibles. Abortando antes de crear un cliente boto3."
        )

    return access_key, secret_key, str(ca_file)


def build_local_client():
    """Construye el cliente boto3 SOLO después de validar el endpoint
    local del modo activo (STORE_MODE). No debe llamarse sin haber
    pasado require_local_endpoint() primero (ambas rutas igual la
    invocan internamente para no depender del orden de llamada del
    caller)."""
    import boto3  # import diferido: nunca se importa/usa boto3 sin validar

    mode = get_store_mode()
    endpoint = require_local_endpoint()

    if mode == "dynamodb_local":
        client = boto3.client(
            "dynamodb",
            endpoint_url=endpoint,
            region_name=FAKE_REGION,
            aws_access_key_id=FAKE_ACCESS_KEY,
            aws_secret_access_key=FAKE_SECRET_KEY,
        )
        return client, endpoint, mode

    # mode == "aws_emulator": credenciales y CA generados por el
    # emulador, nunca fijos.
    port = endpoint.rsplit(":", 1)[-1]
    access_key, secret_key, ca_file = _load_emulator_credentials(port)
    client = boto3.client(
        "dynamodb",
        endpoint_url=endpoint,
        region_name=os.environ.get("AWS_REGION", "us-east-1"),
        aws_access_key_id=access_key,
        aws_secret_access_key=secret_key,
        verify=ca_file,
    )
    return client, endpoint, mode


def _log_call(log: list[dict], operation: str, ok: bool, detail: Any = None, error: str | None = None) -> None:
    entry: dict[str, Any] = {"operation": operation, "ok": ok}
    if detail is not None:
        entry["detail"] = detail
    if error is not None:
        entry["error"] = error
    log.append(entry)


def _http_status(exc: Exception) -> int | None:
    resp = getattr(exc, "response", None)
    if not resp:
        return None
    return resp.get("ResponseMetadata", {}).get("HTTPStatusCode")


def _error_code(exc: Exception) -> str | None:
    resp = getattr(exc, "response", None)
    if not resp:
        return None
    return resp.get("Error", {}).get("Code")


def wait_for_table_active(client, table_name: str, timeout_s: float = 15.0) -> bool:
    """El AWS Emulator reporta CreateTable con TableStatus=CREATING y
    transiciona a ACTIVE poco después (confirmado en vivo: bajo medio
    segundo). DynamoDB Local, en cambio, reporta ACTIVE de inmediato.
    Esta espera activa es inocua en ambos casos (si ya está ACTIVE,
    describe_table lo confirma en la primera vuelta) y es necesaria
    para que PutItem no falle con ResourceNotFoundException contra el
    AWS Emulator."""
    import time

    deadline = time.time() + timeout_s
    while time.time() < deadline:
        try:
            resp = client.describe_table(TableName=table_name)
            if resp["Table"]["TableStatus"] == "ACTIVE":
                return True
        except Exception:  # noqa: BLE001
            pass
        time.sleep(0.2)
    return False


def ensure_table(client, log: list[dict]) -> bool:
    """CreateTable (idempotente), y espera a que la tabla quede ACTIVE
    antes de reportar éxito (necesario para el AWS Emulator, inocuo
    para DynamoDB Local). Devuelve True si la tabla queda disponible,
    False si la operación falló de forma no recuperable."""
    try:
        client.create_table(
            TableName=TABLE_NAME,
            KeySchema=[
                {"AttributeName": "report_id", "KeyType": "HASH"},
                {"AttributeName": "target_version", "KeyType": "RANGE"},
            ],
            AttributeDefinitions=[
                {"AttributeName": "report_id", "AttributeType": "S"},
                {"AttributeName": "target_version", "AttributeType": "S"},
            ],
            BillingMode="PAY_PER_REQUEST",
        )
        active = wait_for_table_active(client, TABLE_NAME)
        if not active:
            _log_call(log, "CreateTable", False, {"table": TABLE_NAME}, error="timeout esperando TableStatus=ACTIVE")
            return False
        _log_call(log, "CreateTable", True, {"table": TABLE_NAME})
        return True
    except Exception as exc:  # noqa: BLE001
        code = _error_code(exc)
        if code == "ResourceInUseException":
            active = wait_for_table_active(client, TABLE_NAME)
            _log_call(log, "CreateTable", active, {"table": TABLE_NAME, "note": "already_exists"})
            return active
        status = _http_status(exc)
        _log_call(log, "CreateTable", False, {"http_status": status, "error_code": code}, error=f"{type(exc).__name__}: {exc}")
        return False


def put_report(client, log: list[dict], report_id: str, report_doc: dict) -> bool:
    try:
        item = {
            "report_id": {"S": report_id},
            "target_version": {"S": str(report_doc.get("target_version", "unknown"))},
            "generated_at": {"S": str(report_doc.get("generated_at", ""))},
            "report_json": {"S": json.dumps(report_doc, ensure_ascii=False)},
        }
        client.put_item(TableName=TABLE_NAME, Item=item)
        _log_call(log, "PutItem", True, {"report_id": report_id, "target_version": report_doc.get("target_version")})
        return True
    except Exception as exc:  # noqa: BLE001
        status = _http_status(exc)
        code = _error_code(exc)
        _log_call(log, "PutItem", False, {"http_status": status, "error_code": code, "report_id": report_id}, error=f"{type(exc).__name__}: {exc}")
        return False


def get_report(client, log: list[dict], report_id: str, target_version: str) -> dict | None:
    try:
        resp = client.get_item(
            TableName=TABLE_NAME,
            Key={"report_id": {"S": report_id}, "target_version": {"S": target_version}},
        )
        item = resp.get("Item")
        if not item:
            _log_call(log, "GetItem", True, {"report_id": report_id, "target_version": target_version, "found": False})
            return None
        doc = json.loads(item["report_json"]["S"])
        _log_call(log, "GetItem", True, {"report_id": report_id, "target_version": target_version, "found": True})
        return doc
    except Exception as exc:  # noqa: BLE001
        status = _http_status(exc)
        code = _error_code(exc)
        _log_call(log, "GetItem", False, {"http_status": status, "error_code": code, "report_id": report_id}, error=f"{type(exc).__name__}: {exc}")
        return None


def pending_test_after(log: list[dict]) -> str | None:
    """Dada la secuencia de llamadas registradas, indica cuál prueba
    quedó pendiente si alguna falló (CreateTable -> PutItem -> GetItem)."""
    ops_ok = {entry["operation"]: entry["ok"] for entry in log}
    order = ["CreateTable", "PutItem", "GetItem"]
    for i, op in enumerate(order):
        if op not in ops_ok:
            return op  # nunca se intentó
        if not ops_ok[op]:
            # Esta falló: las siguientes en el orden quedan pendientes.
            remaining = order[i + 1:]
            return remaining[0] if remaining else None
    return None  # todas corrieron y pasaron
