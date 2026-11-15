"""
Prueba de integración end-to-end:

  1. Ejecuta el laboratorio real (server_lab.py + client_matrix.py) para
     FastMCP 3.4.9 y 3.4.10, usando las funciones ya existentes del
     laboratorio verificado (no reimplementa el cliente MCP aquí).
  2. Pasa la salida cruda de cada versión por verifier.py para obtener
     el informe reducido (versión, caso, veredicto, evidencia mínima).
  3. Antes de tocar DynamoDB, exige DDB_LOCAL_ENDPOINT (ver
     dynamo_store.require_local_endpoint). Si falta, el script se
     detiene con un error claro y SIN haber construido un cliente
     boto3.
  4. Ejecuta CreateTable, luego PutItem para cada informe (3.4.9 y
     3.4.10) bajo el mismo report_id, luego GetItem para cada versión.
  5. Verifica que el informe recuperado por GetItem para cada versión
     coincide con el informe generado para esa versión, y que ambas
     versiones conviven en la tabla (no se pisan entre sí).
  6. Si alguna operación de DynamoDB devuelve error (incluido HTTP 501,
     "Not Implemented", que algunas implementacide emulador usan para
     indicar un método no soportado), se registra la llamada y el
     error, y se reporta explícitamente cuál prueba quedó pendiente.

Este script asume (no vuelve a demostrar) el contraste de autorización
ya documentado en RESULTS.md; lo re-ejecuta en vivo para alimentar la
integración con datos reales, no con datos de ejemplo.
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
import time
from pathlib import Path

import dynamo_store
import verifier
from verifier import Verdict

LAB_DIR = Path(__file__).resolve().parent
REPORT_ID = "ghsa-7xgj-8392-5q4r-lab"

# Matriz de aceptación del punto 2: el veredicto EXACTO que cada caso
# debe tener para cada versión. La integración falla (código distinto
# de cero) si falta un caso, si su veredicto no coincide con esta
# matriz, o si el informe recuperado de DynamoDB difiere del generado.
ACCEPTANCE_MATRIX = {
    "3.4.9": {
        "authorized:tools_list": Verdict.ACCESO_LEGITIMO.value,
        "authorized:tools_call": Verdict.ACCESO_LEGITIMO.value,
        "restricted:tools_list": Verdict.BLOQUEO_ESPERADO.value,
        "restricted:tools_call": Verdict.ACCESO_INDEBIDO.value,
    },
    "3.4.10": {
        "authorized:tools_list": Verdict.ACCESO_LEGITIMO.value,
        "authorized:tools_call": Verdict.ACCESO_LEGITIMO.value,
        "restricted:tools_list": Verdict.BLOQUEO_ESPERADO.value,
        "restricted:tools_call": Verdict.BLOQUEO_ESPERADO.value,
    },
}


def check_security_outcome(report_doc: dict, expected_by_case: dict) -> list[str]:
    """Compara el informe verificado contra la matriz de aceptación.
    Devuelve una lista de problemas (vacía si todo coincide). No
    levanta excepción: el llamador decide qué hacer con la lista."""
    problems: list[str] = []
    version = report_doc.get("target_version", "unknown")
    actual_by_case = {c["case"]: c["verdict"] for c in report_doc.get("cases", [])}

    for case, expected_verdict in expected_by_case.items():
        if case not in actual_by_case:
            problems.append(f"[{version}] caso faltante: '{case}' (se esperaba {expected_verdict})")
            continue
        actual_verdict = actual_by_case[case]
        if actual_verdict != expected_verdict:
            problems.append(
                f"[{version}] veredicto inesperado en '{case}': "
                f"se obtuvo {actual_verdict}, se esperaba {expected_verdict}"
            )

    # Casos presentes que no estaban en la matriz esperada no son un
    # fallo en sí, pero si sobra un caso con verdict ACCESO_INDEBIDO o
    # INDETERMINADO no cubierto por la matriz, se marca para no dejarlo
    # pasar en silencio.
    for case, verdict in actual_by_case.items():
        if case not in expected_by_case and verdict in (Verdict.ACCESO_INDEBIDO.value, Verdict.INDETERMINADO.value):
            problems.append(f"[{version}] caso no esperado '{case}' con veredicto {verdict}")

    return problems


def run_lab_version(version: str, port: int) -> dict:
    """Levanta server_lab.py con la versión de fastmcp dada, corre
    client_matrix.py contra ella, y devuelve el JSON crudo. Reutiliza
    exactamente los mismos scripts del laboratorio verificado."""
    env = dict(os.environ)
    env["LAB_PORT"] = str(port)
    server_proc = subprocess.Popen(
        ["uv", "run", "--with", f"fastmcp=={version}", "--", "python3", "server_lab.py"],
        cwd=LAB_DIR,
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    try:
        # Esperar a que el puerto responda (máx 60s: uv puede tardar en
        # resolver dependencias en frío la primera vez).
        deadline = time.time() + 60
        up = False
        while time.time() < deadline:
            if server_proc.poll() is not None:
                stderr_tail = server_proc.stderr.read().decode(errors="replace")[-2000:]
                raise RuntimeError(
                    f"Servidor FastMCP {version} terminó prematuramente: {stderr_tail}"
                )
            probe = subprocess.run(
                ["curl", "-s", "-o", "/dev/null", "-m", "1", "-w", "%{http_code}",
                 f"http://127.0.0.1:{port}/mcp"],
                capture_output=True, text=True,
            )
            if probe.stdout.strip() not in ("", "000000", "000"):
                up = True
                break
            time.sleep(0.5)
        if not up:
            raise RuntimeError(f"Servidor FastMCP {version} no respondió en el puerto {port}")

        result = subprocess.run(
            ["uv", "run", "--with", f"fastmcp=={version}", "--", "python3",
             "client_matrix.py", str(port)],
            cwd=LAB_DIR,
            env=env,
            capture_output=True,
            text=True,
            timeout=60,
        )
        if result.returncode != 0:
            raise RuntimeError(
                f"client_matrix.py falló para {version}: {result.stderr[-2000:]}"
            )
        return json.loads(result.stdout)
    finally:
        server_proc.terminate()
        try:
            server_proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            server_proc.kill()


def main() -> int:
    call_log: list[dict] = []

    # Paso 1: validar endpoint local ANTES de construir cualquier cliente.
    try:
        dynamo_store.require_local_endpoint()
    except dynamo_store.MissingLocalEndpointError as exc:
        print(f"ABORT: {exc}", file=sys.stderr)
        return 2

    # Paso 2: ejecutar el laboratorio real para ambas versiones.
    print("Ejecutando laboratorio real: fastmcp 3.4.9 ...")
    raw_349 = run_lab_version("3.4.9", 8900)
    print("Ejecutando laboratorio real: fastmcp 3.4.10 ...")
    raw_3410 = run_lab_version("3.4.10", 8901)

    # Paso 3: verificar (reducir a informe sin tokens/cuerpos sensibles).
    report_349 = verifier.build_report_document(raw_349)
    report_3410 = verifier.build_report_document(raw_3410)

    print("\n=== Informe verificado 3.4.9 ===")
    print(json.dumps(report_349, indent=2, ensure_ascii=False))
    print("\n=== Informe verificado 3.4.10 ===")
    print(json.dumps(report_3410, indent=2, ensure_ascii=False))

    # Paso 3b: comprobar el RESULTADO DE SEGURIDAD contra la matriz de
    # aceptación, sobre el informe recién generado (antes de tocar
    # DynamoDB). Si esto falla, se aborta: no tiene sentido persistir
    # ni verificar un informe que ya no cumple la matriz esperada.
    pre_persist_problems = check_security_outcome(
        report_349, ACCEPTANCE_MATRIX["3.4.9"]
    ) + check_security_outcome(report_3410, ACCEPTANCE_MATRIX["3.4.10"])
    if pre_persist_problems:
        print("\n=== FALLA DE RESULTADO DE SEGURIDAD (antes de persistir) ===")
        for p in pre_persist_problems:
            print(f"  - {p}")
        return 3

    # Paso 4: construir cliente DynamoDB local (ya validado el endpoint).
    client, endpoint, store_mode = dynamo_store.build_local_client()
    print(f"\nModo de almacenamiento: {store_mode}")
    print(f"Usando endpoint local: {endpoint}")

    # Paso 5: CreateTable, PutItem (x2), GetItem (x2).
    table_ok = dynamo_store.ensure_table(client, call_log)
    if not table_ok:
        _report_and_exit(call_log, success=False)
        return 1

    put_349_ok = dynamo_store.put_report(client, call_log, REPORT_ID, report_349)
    put_3410_ok = dynamo_store.put_report(client, call_log, REPORT_ID, report_3410)
    if not (put_349_ok and put_3410_ok):
        _report_and_exit(call_log, success=False)
        return 1

    fetched_349 = dynamo_store.get_report(client, call_log, REPORT_ID, "3.4.9")
    fetched_3410 = dynamo_store.get_report(client, call_log, REPORT_ID, "3.4.10")

    # Paso 6: verificar PERSISTENCIA: que ambas versiones se conservan
    # correctamente y que lo recuperado es idéntico a lo generado.
    ok_349 = fetched_349 is not None and fetched_349["target_version"] == "3.4.9"
    ok_3410 = fetched_3410 is not None and fetched_3410["target_version"] == "3.4.10"
    cases_349_match = fetched_349 == report_349 if fetched_349 else False
    cases_3410_match = fetched_3410 == report_3410 if fetched_3410 else False

    print("\n=== Comprobación de persistencia ===")
    print(f"3.4.9 recuperado y coincide con lo generado: {ok_349 and cases_349_match}")
    print(f"3.4.10 recuperado y coincide con lo generado: {ok_3410 and cases_3410_match}")
    print(f"Ambas versiones coexisten bajo report_id='{REPORT_ID}': {ok_349 and ok_3410}")

    persistence_ok = ok_349 and ok_3410 and cases_349_match and cases_3410_match

    # Paso 7: verificar RESULTADO DE SEGURIDAD también sobre lo
    # RECUPERADO de DynamoDB (no solo sobre lo generado en memoria):
    # si el round-trip corrompiera o perdiera un caso, esto debe
    # detectarlo igual que la comprobación del paso 3b.
    post_persist_problems: list[str] = []
    if fetched_349 is not None:
        post_persist_problems += check_security_outcome(fetched_349, ACCEPTANCE_MATRIX["3.4.9"])
    else:
        post_persist_problems.append("[3.4.9] informe no recuperado de DynamoDB")
    if fetched_3410 is not None:
        post_persist_problems += check_security_outcome(fetched_3410, ACCEPTANCE_MATRIX["3.4.10"])
    else:
        post_persist_problems.append("[3.4.10] informe no recuperado de DynamoDB")

    print("\n=== Comprobación de resultado de seguridad (sobre lo recuperado) ===")
    if post_persist_problems:
        for p in post_persist_problems:
            print(f"  FALLA: {p}")
    else:
        print("  Todos los casos coinciden con la matriz de aceptación para ambas versiones.")

    success = persistence_ok and not post_persist_problems
    _report_and_exit(call_log, success=success)
    if not persistence_ok:
        return 1
    if post_persist_problems:
        return 4
    return 0


def _report_and_exit(call_log: list[dict], success: bool) -> None:
    print("\n=== Registro de llamadas DynamoDB ===")
    print(json.dumps(call_log, indent=2, ensure_ascii=False))
    pending = dynamo_store.pending_test_after(call_log)
    print(f"\nPrueba pendiente: {pending if pending else 'ninguna (CreateTable, PutItem y GetItem completados)'}")
    print(f"Resultado de la integración: {'OK' if success else 'FALLÓ'}")


if __name__ == "__main__":
    sys.exit(main())
