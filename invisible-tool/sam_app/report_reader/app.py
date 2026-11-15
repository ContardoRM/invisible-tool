"""
Handler Lambda: ReportReaderFunction.

Tiene dos responsabilidades, ambas de solo lectura:

  1. GET /demo/report/{run_id} -> recupera, con Query sobre la clave de
     partición, los informes guardados bajo ese run_id, y los devuelve
     tal cual quedaron persistidos, sin reinterpretar los veredictos.

  2. GET / y GET /ui/{asset} -> sirve la UI bilingüe estática
     (index.html, app.js, translations.js) desde el mismo origen que
     la API. Se reutiliza esta función en vez de crear una tercera
     Lambda porque ya es liviana (sin fastmcp) y el contenido de ui/
     agrega solo unos pocos KB; no requiere ningún permiso de AWS
     adicional.

No hay plantillas de servidor ni reescritura de contenido: los
archivos de ui/ se empaquetan tal cual (ver report_reader/Makefile) y
se devuelven con el Content-Type correcto según su extensión.
"""
from __future__ import annotations

import json
import mimetypes
import os

from common import report_store

# En el paquete desplegado (tras `sam build`), los archivos de ui/ se
# copian a ./static/ junto a este handler (ver report_reader/Makefile).
# Antes de empaquetar — al correr este handler directamente desde el
# código fuente, como hace test_handlers_local.py — ese directorio no
# existe todavía, así que se cae al código fuente real de ui/ en el
# repo, para no requerir un `sam build` previo solo para probar el
# handler en local.
_PACKAGED_STATIC_DIR = os.path.join(os.path.dirname(__file__), "static")
_SOURCE_UI_DIR = os.path.join(os.path.dirname(__file__), "..", "..", "ui")
STATIC_DIR = _PACKAGED_STATIC_DIR if os.path.isdir(_PACKAGED_STATIC_DIR) else _SOURCE_UI_DIR

# Mapeo explícito de rutas servibles a archivos en disco. Cualquier
# ruta no listada aquí (y que no sea /demo/report/{run_id}) responde
# 404, sin intentar leer un path arbitrario del sistema de archivos.
STATIC_ROUTES = {
    "/": "index.html",
    "/ui/app.js": "app.js",
    "/ui/translations.js": "translations.js",
}


def _json_response(status_code: int, body: dict) -> dict:
    return {
        "statusCode": status_code,
        "headers": {"Content-Type": "application/json"},
        "body": json.dumps(body, ensure_ascii=False),
    }


def _static_response(filename: str) -> dict:
    path = os.path.join(STATIC_DIR, filename)
    if not os.path.isfile(path):
        return _json_response(404, {"error": f"Static asset not found: {filename}"})
    content_type, _ = mimetypes.guess_type(filename)
    with open(path, "r", encoding="utf-8") as f:
        content = f.read()
    return {
        "statusCode": 200,
        "headers": {"Content-Type": content_type or "application/octet-stream"},
        "body": content,
    }


def handler(event, context):
    path = event.get("path") or event.get("rawPath") or ""
    # API Gateway (REST API) entrega el path SIN el prefijo del stage
    # (p. ej. "/demo") en el campo "path" del evento de integración
    # Lambda proxy: event["path"] ya es "/", "/ui/app.js",
    # "/demo/report/<run_id>", etc. — el stage es parte de la URL
    # pública pero no del evento que recibe el handler.

    if path in STATIC_ROUTES:
        return _static_response(STATIC_ROUTES[path])

    if path.startswith("/demo/report/"):
        path_params = event.get("pathParameters") or {}
        run_id = path_params.get("run_id")
        if not run_id:
            return _json_response(400, {"error": "Missing run_id in /demo/report/{run_id}"})
        reports = report_store.get_reports_for_run(run_id)
        if not reports:
            return _json_response(404, {"error": f"No report found for run_id='{run_id}'"})
        return _json_response(200, {"run_id": run_id, "reports": reports})

    return _json_response(404, {"error": f"Unknown route: {path}"})
