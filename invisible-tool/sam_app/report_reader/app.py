"""
Handler Lambda: ReportReaderFunction.

Invocado vía API Gateway (GET /demo/report/{run_id}). Recupera, con
Query sobre la clave de partición, todos los informes guardados bajo
ese run_id (normalmente uno: la versión objetivo de esa corrida,
"3.4.10 · comprobación en vivo") y los devuelve tal cual quedaron
persistidos, sin reinterpretar los veredictos.
"""
from __future__ import annotations

import json

from common import report_store


def _response(status_code: int, body: dict) -> dict:
    return {
        "statusCode": status_code,
        "headers": {"Content-Type": "application/json"},
        "body": json.dumps(body, ensure_ascii=False),
    }


def handler(event, context):
    path_params = event.get("pathParameters") or {}
    run_id = path_params.get("run_id")

    if not run_id:
        return _response(400, {"error": "Falta run_id en la ruta /demo/report/{run_id}"})

    reports = report_store.get_reports_for_run(run_id)
    if not reports:
        return _response(404, {"error": f"No se encontró ningún informe para run_id='{run_id}'"})

    return _response(200, {"run_id": run_id, "reports": reports})
