"""
Verificador de expectativas de autorización para el laboratorio
GHSA-7xgj-8392-5q4r.

Toma la salida cruda de client_matrix.py (un objeto con
"fastmcp_version" y "cases": [{"identity", "tools_list", "tools_call"}])
para una versión dada y la compara contra la matriz de expectativas
declarada abajo, produciendo un veredicto por caso en una de cuatro
categorías:

  - ACCESO_INDEBIDO: la identidad restringida no debía alcanzar el
    handler y lo alcanzó (handler_reached=True con returned_text ==
    MARKER). Esto es la vulnerabilidad del aviso.
  - BLOQUEO_ESPERADO: la identidad restringida fue bloqueada
    (handler_reached=False) tal como exige la política.
  - ACCESO_LEGITIMO: la identidad autorizada alcanzó el handler tal
    como exige la política.
  - INDETERMINADO: no se puede afirmar nada sobre autorización porque
    la llamada falló por una causa de transporte o autenticación (p.
    ej. conexión rechazada, timeout, error HTTP 401/403 reportado como
    fallo de canal en vez de como ToolError de "unknown tool", excepción
    no reconocida). Se distingue explícitamente de un bloqueo de
    autorización correcto.

La categoría INDETERMINADO existe porque un bloqueo de autorización
correcto (versión corregida) y un fallo de transporte se pueden parecer
superficialmente (ambos son "la llamada no tuvo éxito"); el aviso solo
define el contraste en términos de si el handler se ejecutó, así que hay
que clasificar explícitamente qué tipo de "no éxito" se observó.

El informe generado no contiene tokens ni cuerpos de respuesta completos:
solo guarda la versión, el nombre del caso, el veredicto y una evidencia
mínima (nombres de tools listadas, el texto devuelto SOLO si es
exactamente el marcador esperado, y la clase de excepción + un extracto
corto del mensaje de error, sin el token Authorization ni el payload MCP
completo).
"""
from __future__ import annotations

import datetime
import json
import sys
from dataclasses import asdict, dataclass
from enum import Enum

MARKER = "DEMO_REACHED"

# Patrones de mensaje/clase de error que señalan un BLOQUEO DE
# AUTORIZACIÓN LIMPIO: el servidor resolvió la identidad y decidió, a
# nivel de aplicación MCP, que el componente no existe para ella (lo
# oculta en vez de ejecutarlo). Esto es distinto de un fallo de canal:
# aquí sí hubo sesión autenticada y el servidor respondió al protocolo.
# "Unauthorized" y "Forbidden" se removieron de aquí a propósito: son
# ambiguos entre "la app decidió denegar" y "el canal rechazó la
# autenticación" (p. ej. un 401 de sesión), así que un mensaje que solo
# contenga esas palabras cae en AUTH_FAILURE_MARKERS/INDETERMINADO, no
# aquí, a menos que además matchee uno de estos patrones explícitos del
# error de aplicación.
AUTHZ_BLOCK_ERROR_MARKERS = (
    "Unknown tool",
    "ToolError",
    "not found",
    "PermissionError",
)

# Patrones que indican fallo de TRANSPORTE (canal de red: conexión
# rechazada, timeout, protocolo roto). No hubo respuesta de aplicación
# que interpretar.
TRANSPORT_ERROR_TYPES = (
    "ConnectError",
    "ConnectTimeout",
    "ReadTimeout",
    "TimeoutError",
    "ConnectionRefusedError",
    "httpx.ConnectError",
    "httpx.ReadTimeout",
    "RemoteProtocolError",
)

# Patrones que indican fallo de AUTENTICACIÓN DE SESIÓN (el canal
# respondió, pero rechazó las credenciales antes de llegar a cualquier
# decisión de autorización de componente): HTTP 401/403 a nivel de
# transporte HTTP, o errores explícitos de credenciales. Un 401/403 aquí
# significa que la identidad ni siquiera estableció sesión, así que no
# se puede inferir nada sobre la política de autorización del servidor
# para ese componente: es INDETERMINADO, nunca BLOQUEO_ESPERADO.
AUTH_FAILURE_MARKERS = (
    "HTTPStatusError",
    "401",
    "403",
    "Unauthorized",
    "Forbidden",
    "AuthenticationError",
    "InvalidToken",
)


class Verdict(str, Enum):
    ACCESO_INDEBIDO = "ACCESO_INDEBIDO"
    BLOQUEO_ESPERADO = "BLOQUEO_ESPERADO"
    ACCESO_LEGITIMO = "ACCESO_LEGITIMO"
    ACCESO_LEGITIMO_FALLIDO = "ACCESO_LEGITIMO_FALLIDO"
    INDETERMINADO = "INDETERMINADO"


@dataclass
class CaseReport:
    target_version: str
    case: str  # "<identity>:tools_list" o "<identity>:tools_call"
    identity: str
    expected: str  # "allow" | "deny"
    verdict: str
    evidence: dict


def _is_transport_error(error_text: str) -> bool:
    return any(marker in error_text for marker in TRANSPORT_ERROR_TYPES)


def _is_auth_failure(error_text: str) -> bool:
    return any(marker in error_text for marker in AUTH_FAILURE_MARKERS)


def _is_clean_authz_block(error_text: str) -> bool:
    return any(marker in error_text for marker in AUTHZ_BLOCK_ERROR_MARKERS)


def evaluate_tools_list(
    target_version: str, identity: str, expected: str, tools_list: dict
) -> CaseReport:
    if not tools_list.get("ok", False):
        error = str(tools_list.get("error", ""))
        if _is_transport_error(error):
            verdict = Verdict.INDETERMINADO
            evidence = {"reason": "transport_error", "error_class": error.split(":")[0]}
        elif _is_auth_failure(error):
            verdict = Verdict.INDETERMINADO
            evidence = {"reason": "auth_failure", "error_class": error.split(":")[0]}
        else:
            # tools/list no debería fallar por autorización (solo filtra);
            # un fallo aquí que no sea de transporte ni de autenticación
            # es indeterminado por cautela, sin asumir causa.
            verdict = Verdict.INDETERMINADO
            evidence = {"reason": "unexpected_list_failure", "error_class": error.split(":")[0]}
        return CaseReport(target_version, f"{identity}:tools_list", identity, expected, verdict.value, evidence)

    names = tools_list.get("names", [])
    listed = "tagged_tool" in names
    if expected == "allow":
        verdict = Verdict.ACCESO_LEGITIMO if listed else Verdict.ACCESO_LEGITIMO_FALLIDO
    else:
        # expected == "deny": listar la tool para una identidad restringida
        # no es "acceso indebido" en el sentido del aviso (no ejecuta nada),
        # pero sí es una falla de la política de visibilidad. Se marca
        # como ACCESO_INDEBIDO porque filtra la existencia del componente
        # protegido a quien no debería verlo.
        verdict = Verdict.ACCESO_INDEBIDO if listed else Verdict.BLOQUEO_ESPERADO
    evidence = {"listed_tagged_tool": listed, "tool_count": len(names)}
    return CaseReport(target_version, f"{identity}:tools_list", identity, expected, verdict.value, evidence)


def evaluate_tools_call(
    target_version: str,
    identity: str,
    expected: str,
    tools_call: dict,
    tool_confirmed_working: bool = False,
) -> CaseReport:
    """
    tool_confirmed_working: True si, EN LA MISMA EJECUCIÓN, la identidad
    autorizada confirmó que "tagged_tool" existe y responde con el
    marcador esperado. Esto es evidencia cruzada obligatoria para poder
    marcar un "Unknown tool" de la identidad restringida como
    BLOQUEO_ESPERADO: sin ella, un "Unknown tool" podría significar que
    la tool nunca se registró (p. ej. error de configuración del
    servidor) en vez de que la política de autorización la ocultó
    correctamente a esa identidad. Si no hay confirmación cruzada, un
    "Unknown tool" se reporta como INDETERMINADO.
    """
    handler_reached = bool(tools_call.get("handler_reached", False))
    call_ok = bool(tools_call.get("ok", False))
    returned_text = tools_call.get("returned_text")

    if call_ok and handler_reached:
        marker_confirmed = returned_text == MARKER
        if expected == "allow":
            verdict = Verdict.ACCESO_LEGITIMO if marker_confirmed else Verdict.INDETERMINADO
            evidence = {"handler_reached": True, "marker_confirmed": marker_confirmed}
        else:
            verdict = Verdict.ACCESO_INDEBIDO if marker_confirmed else Verdict.INDETERMINADO
            evidence = {"handler_reached": True, "marker_confirmed": marker_confirmed}
        return CaseReport(target_version, f"{identity}:tools_call", identity, expected, verdict.value, evidence)

    # La llamada no alcanzó el handler (o no tuvo éxito). Hay que decidir
    # entre: fallo de transporte, fallo de autenticación de sesión
    # (ambos INDETERMINADO), o bloqueo de autorización limpio de la
    # aplicación (BLOQUEO_ESPERADO / ACCESO_LEGITIMO_FALLIDO).
    error = str(tools_call.get("error", ""))

    if _is_transport_error(error):
        verdict = Verdict.INDETERMINADO
        evidence = {"reason": "transport_error", "error_class": error.split(":")[0]}
    elif _is_auth_failure(error):
        # Un 401/403 o fallo de autenticación de sesión significa que
        # la identidad nunca llegó a que el servidor evaluara la
        # autorización del componente: no se puede concluir nada sobre
        # la política, con independencia de si expected es allow o deny.
        verdict = Verdict.INDETERMINADO
        evidence = {"reason": "auth_failure", "error_class": error.split(":")[0]}
    elif _is_clean_authz_block(error):
        if expected == "deny":
            if tool_confirmed_working:
                verdict = Verdict.BLOQUEO_ESPERADO
                evidence = {
                    "reason": "clean_authz_block",
                    "error_class": error.split(":")[0],
                    "tool_confirmed_working": True,
                }
            else:
                # Sin confirmación cruzada de que la tool existe y
                # funciona para la identidad autorizada en esta misma
                # ejecución, no se puede distinguir "la política ocultó
                # el componente correctamente" de "el componente nunca
                # se registró". Queda indeterminado por cautela.
                verdict = Verdict.INDETERMINADO
                evidence = {
                    "reason": "clean_block_without_cross_confirmation",
                    "error_class": error.split(":")[0],
                    "tool_confirmed_working": False,
                }
        else:
            # Se esperaba acceso legítimo y en cambio hubo un bloqueo:
            # falla de disponibilidad para la identidad autorizada, no es
            # el caso de "acceso indebido" pero tampoco debe pasar
            # silenciosamente como bloqueo esperado.
            verdict = Verdict.ACCESO_LEGITIMO_FALLIDO
            evidence = {"reason": "clean_authz_block", "error_class": error.split(":")[0]}
    else:
        # Error reconocido pero no clasificable con confianza como
        # transporte, autenticación, ni bloqueo de autorización limpio.
        verdict = Verdict.INDETERMINADO
        evidence = {"reason": "unclassified_error", "error_class": error.split(":")[0] if error else "empty"}

    return CaseReport(target_version, f"{identity}:tools_call", identity, expected, verdict.value, evidence)


# Expectativas de la política (idénticas a lo documentado en RESULTS.md):
#   - identidad "authorized" (scope admin): debe poder listar y llamar.
#   - identidad "restricted" (sin scopes): no debe poder listar ni llamar.
EXPECTATIONS = {
    "authorized": "allow",
    "restricted": "deny",
}


def _tool_confirmed_working(cases: list[dict]) -> bool:
    """True si, en esta misma tanda de resultados, la identidad
    'authorized' confirmó que tagged_tool existe y devuelve el marcador
    esperado (tools_call exitoso con texto == MARKER). Se usa como
    evidencia cruzada para distinguir un bloqueo de autorización
    genuino (la tool existe pero se oculta a la identidad restringida)
    de un "Unknown tool" que en realidad significa que el componente
    nunca se registró."""
    for case in cases:
        if case.get("identity") != "authorized":
            continue
        tools_call = case.get("tools_call", {})
        return bool(tools_call.get("ok")) and tools_call.get("returned_text") == MARKER
    return False


def verify_matrix_output(raw: dict) -> list[CaseReport]:
    target_version = raw.get("fastmcp_version", "unknown")
    cases_raw = raw.get("cases", [])
    tool_confirmed_working = _tool_confirmed_working(cases_raw)

    reports: list[CaseReport] = []
    for case in cases_raw:
        identity = case["identity"]
        expected = EXPECTATIONS.get(identity)
        if expected is None:
            reports.append(
                CaseReport(
                    target_version,
                    f"{identity}:unknown_identity",
                    identity,
                    "n/a",
                    Verdict.INDETERMINADO.value,
                    {"reason": "identity_not_in_expectations"},
                )
            )
            continue
        reports.append(evaluate_tools_list(target_version, identity, expected, case.get("tools_list", {})))
        reports.append(
            evaluate_tools_call(
                target_version,
                identity,
                expected,
                case.get("tools_call", {}),
                tool_confirmed_working=tool_confirmed_working,
            )
        )
    return reports


def build_report_document(raw: dict) -> dict:
    """Construye el documento final de informe (lo que se persiste),
    sin tokens ni cuerpos de respuesta: solo versión, caso, veredicto y
    evidencia mínima estructurada."""
    reports = verify_matrix_output(raw)
    return {
        "target_version": raw.get("fastmcp_version", "unknown"),
        "generated_at": datetime.datetime.now(datetime.timezone.utc).isoformat(),
        "cases": [asdict(r) for r in reports],
    }


if __name__ == "__main__":
    raw = json.load(sys.stdin)
    report = build_report_document(raw)
    print(json.dumps(report, indent=2, ensure_ascii=False))
