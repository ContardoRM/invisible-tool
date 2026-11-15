"""
Persistencia de informes en la tabla DynamoDB real desplegada por la
plantilla SAM (template.yaml), reutilizando el mismo formato de ítem
que invisible-tool/dynamo_store.py usa contra DynamoDB Local / AWS
Emulator:

    report_id (HASH) + target_version (RANGE) -> { generated_at,
    report_json }

Diferencia respecto a dynamo_store.py: en Lambda no hay "endpoint
local" que validar ni credenciales ficticias que cargar — boto3 usa el
rol de ejecución del propio Lambda (permisos mínimos, ver
template.yaml: dynamodb:PutItem/GetItem/Query acotados al ARN exacto
de esta tabla). El nombre de la tabla llega por la variable de entorno
REPORTS_TABLE_NAME que SAM inyecta desde el output del recurso.

Cada corrida se identifica con un run_id PROPIO (no reutiliza
report_id="ghsa-7xgj-8392-5q4r-lab" del laboratorio local), generado
por el llamador (demo_runner) como run_id = f"{timestamp}-{uuid4().hex[:8]}",
de forma que cada invocación de la demo en vivo queda como un registro
separado y recuperable por su propio identificador, sin pisar corridas
anteriores.
"""
from __future__ import annotations

import json
import os

import boto3

TABLE_NAME_ENV_VAR = "REPORTS_TABLE_NAME"


class MissingTableConfigurationError(RuntimeError):
    """Se lanza si falta REPORTS_TABLE_NAME. Igual que dynamo_store.py
    en el laboratorio local, esto debe fallar ANTES de construir el
    cliente boto3 real."""


def _require_table_name() -> str:
    table_name = os.environ.get(TABLE_NAME_ENV_VAR)
    if not table_name:
        raise MissingTableConfigurationError(
            f"La variable de entorno {TABLE_NAME_ENV_VAR} no está definida. "
            "SAM la inyecta desde el recurso ReportsTable; sin ella no se "
            "construye ningún cliente DynamoDB."
        )
    return table_name


def _client():
    _require_table_name()  # valida primero, nunca se omite
    # REPORTS_LOCAL_TEST_ENDPOINT es SOLO para pruebas locales de este
    # módulo fuera de Lambda (p. ej. contra DynamoDB Local antes de
    # desplegar). En el Lambda real esta variable no se define, y
    # boto3.client("dynamodb") usa el endpoint real de AWS con las
    # credenciales del rol de ejecución.
    test_endpoint = os.environ.get("REPORTS_LOCAL_TEST_ENDPOINT")
    if test_endpoint:
        return boto3.client(
            "dynamodb",
            endpoint_url=test_endpoint,
            region_name="us-east-1",
            aws_access_key_id="fakeMyKeyId",
            aws_secret_access_key="fakeSecretAccessKey",
        )
    return boto3.client("dynamodb")


def put_report(run_id: str, report_doc: dict) -> None:
    table_name = _require_table_name()
    client = _client()
    item = {
        "report_id": {"S": run_id},
        "target_version": {"S": str(report_doc.get("target_version", "unknown"))},
        "generated_at": {"S": str(report_doc.get("generated_at", ""))},
        "report_json": {"S": json.dumps(report_doc, ensure_ascii=False)},
    }
    client.put_item(TableName=table_name, Item=item)


def get_report(run_id: str, target_version: str) -> dict | None:
    table_name = _require_table_name()
    client = _client()
    resp = client.get_item(
        TableName=table_name,
        Key={"report_id": {"S": run_id}, "target_version": {"S": target_version}},
    )
    item = resp.get("Item")
    if not item:
        return None
    return json.loads(item["report_json"]["S"])


def get_reports_for_run(run_id: str) -> list[dict]:
    """Recupera todos los informes (una o más target_version) guardados
    bajo un run_id, usando Query sobre la clave de partición. Permite a
    la pantalla de demo pedir "el informe de esta corrida" sin conocer
    de antemano qué versión se guardó."""
    table_name = _require_table_name()
    client = _client()
    resp = client.query(
        TableName=table_name,
        KeyConditionExpression="report_id = :rid",
        ExpressionAttributeValues={":rid": {"S": run_id}},
    )
    return [json.loads(item["report_json"]["S"]) for item in resp.get("Items", [])]
