"""
Handler Lambda: DemoRunnerFunction.

Invocado vía API Gateway (POST /demo/run). Cada invocación:

  1. Arranca la fixture FastMCP 3.4.10 embebida (ver
     common/fixture_3410.py) en un hilo de background dentro del
     propio proceso Lambda, bindeada solo a 127.0.0.1.
  2. Ejecuta tools/list + tools/call para la identidad RESTRINGIDA
     primero, y para la AUTORIZADA después como control (mismo orden
     que debe respetar la pantalla de demo).
  3. Pasa la salida cruda por verifier.py (el mismo verificador que ya
     pasó con DynamoDB Local y con el AWS Emulator; sin cambios).
  4. Persiste el informe en la tabla real (report_store.py) bajo un
     run_id propio de esta invocación.
  5. Devuelve el informe completo más el run_id, para que la pantalla
     de demo pueda mostrarlo de inmediato y también recuperarlo más
     tarde con GET /demo/report/{run_id}.

Un fallo de sesión o transporte en live_matrix.py (p. ej. el socket
loopback no abre a tiempo) se propaga tal cual al JSON crudo de
tools_list/tools_call; verifier.py lo clasifica como INDETERMINADO
exactamente igual que en el laboratorio local, sin tratamiento
especial aquí.
"""
from __future__ import annotations

import json
import time
import uuid

from common import live_matrix, report_store, verifier


def _new_run_id() -> str:
    return f"{int(time.time())}-{uuid.uuid4().hex[:8]}"


def _response(status_code: int, body: dict) -> dict:
    return {
        "statusCode": status_code,
        "headers": {"Content-Type": "application/json"},
        "body": json.dumps(body, ensure_ascii=False),
    }


def handler(event, context):
    run_id = _new_run_id()

    try:
        raw = live_matrix.run_matrix()
    except Exception as exc:  # noqa: BLE001
        # Un fallo al arrancar o conectar la fixture en sí (no un
        # fallo de autorización) se reporta como error de la demo, no
        # se inventa un veredicto de seguridad para él.
        return _response(500, {
            "run_id": run_id,
            "error": f"No se pudo ejecutar la fixture FastMCP 3.4.10 embebida: "
                      f"{type(exc).__name__}: {exc}",
        })

    report = verifier.build_report_document(raw)
    report["run_id"] = run_id
    report["source"] = "3.4.10 · comprobación en vivo"

    report_store.put_report(run_id, report)

    return _response(200, {"run_id": run_id, "report": report})
