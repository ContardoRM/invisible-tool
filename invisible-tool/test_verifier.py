"""
Pruebas de regresión para verifier.py.

Cubren explícitamente los dos casos pedidos:

  1. Un HTTP 401 / fallo de autenticación de sesión en tools_call debe
     dar INDETERMINADO, nunca BLOQUEO_ESPERADO ni ACCESO_INDEBIDO,
     porque el servidor nunca llegó a evaluar la autorización del
     componente.
  2. "ToolError: Unknown tool" para la identidad restringida cuenta
     como BLOQUEO_ESPERADO únicamente cuando, en la misma tanda, la
     identidad autorizada confirmó que la tool existe y responde con
     el marcador esperado (evidencia cruzada). Sin esa confirmación,
     el mismo error debe ser INDETERMINADO.

Además se agregan pruebas de regresión end-to-end contra los datos
reales ya capturados del laboratorio (3.4.9 vulnerable, 3.4.10
corregida), para fijar el contrato completo de la matriz de
aceptación del punto 2.

Ejecutar con:
    uv run --with pytest -- python3 -m pytest test_verifier.py -v
"""
from __future__ import annotations

import json

import verifier
from verifier import Verdict, evaluate_tools_call, verify_matrix_output


def _verdicts(reports) -> dict:
    return {r.case: r.verdict for r in reports}


# ---------------------------------------------------------------------
# 1. Regresión: 401 / fallo de autenticación -> INDETERMINADO
# ---------------------------------------------------------------------

def test_401_auth_failure_is_indeterminado_even_when_expected_deny():
    tools_call = {
        "ok": False,
        "handler_reached": False,
        "error": "HTTPStatusError: Client error '401 Unauthorized' for url "
                 "'http://127.0.0.1:8900/mcp'",
    }
    report = evaluate_tools_call(
        "3.4.10", "restricted", "deny", tools_call, tool_confirmed_working=True
    )
    assert report.verdict == Verdict.INDETERMINADO.value
    assert report.evidence["reason"] == "auth_failure"


def test_401_auth_failure_is_indeterminado_even_when_expected_allow():
    # Si incluso la identidad autorizada recibe 401 (p. ej. token
    # corrupto), tampoco se puede concluir ACCESO_LEGITIMO ni nada
    # parecido a un bloqueo: es un fallo de canal/sesión.
    tools_call = {
        "ok": False,
        "handler_reached": False,
        "error": "HTTPStatusError: Client error '401 Unauthorized' for url "
                 "'http://127.0.0.1:8900/mcp'",
    }
    report = evaluate_tools_call(
        "3.4.10", "authorized", "allow", tools_call, tool_confirmed_working=False
    )
    assert report.verdict == Verdict.INDETERMINADO.value
    assert report.evidence["reason"] == "auth_failure"


def test_connection_level_401_from_client_matrix_is_indeterminado():
    """Simula la forma real en que client_matrix.py reporta un 401 de
    conexión (ver run_identity): tools_list y tools_call quedan ambos
    con el mismo error de conexión, no un ToolError de aplicación."""
    raw = {
        "fastmcp_version": "3.4.10",
        "cases": [
            {
                "identity": "authorized",
                "tools_list": {"ok": True, "names": ["tagged_tool"]},
                "tools_call": {
                    "ok": True,
                    "returned_text": verifier.MARKER,
                    "handler_reached": True,
                },
            },
            {
                "identity": "restricted",
                "tools_list": {
                    "ok": False,
                    "error": "HTTPStatusError: Client error '401 Unauthorized' "
                             "for url 'http://127.0.0.1:8900/mcp'",
                },
                "tools_call": {
                    "ok": False,
                    "handler_reached": False,
                    "error": "HTTPStatusError: Client error '401 Unauthorized' "
                             "for url 'http://127.0.0.1:8900/mcp'",
                },
            },
        ],
    }
    verdicts = _verdicts(verify_matrix_output(raw))
    assert verdicts["restricted:tools_list"] == Verdict.INDETERMINADO.value
    assert verdicts["restricted:tools_call"] == Verdict.INDETERMINADO.value
    # La identidad autorizada, sin problemas, sigue dando su veredicto normal.
    assert verdicts["authorized:tools_call"] == Verdict.ACCESO_LEGITIMO.value


# ---------------------------------------------------------------------
# 2. Regresión: "Unknown tool" + confirmación cruzada -> BLOQUEO_ESPERADO
# ---------------------------------------------------------------------

def test_unknown_tool_with_cross_confirmation_is_bloqueo_esperado():
    tools_call = {
        "ok": False,
        "handler_reached": False,
        "error": "ToolError: Unknown tool: 'tagged_tool'",
    }
    report = evaluate_tools_call(
        "3.4.10", "restricted", "deny", tools_call, tool_confirmed_working=True
    )
    assert report.verdict == Verdict.BLOQUEO_ESPERADO.value
    assert report.evidence["tool_confirmed_working"] is True


def test_unknown_tool_without_cross_confirmation_is_indeterminado():
    """Sin que la identidad autorizada haya confirmado en la misma
    ejecución que la tool existe y funciona, un 'Unknown tool' no debe
    asumirse como bloqueo de autorización: podría ser que la tool
    nunca se registró."""
    tools_call = {
        "ok": False,
        "handler_reached": False,
        "error": "ToolError: Unknown tool: 'tagged_tool'",
    }
    report = evaluate_tools_call(
        "3.4.10", "restricted", "deny", tools_call, tool_confirmed_working=False
    )
    assert report.verdict == Verdict.INDETERMINADO.value
    assert report.evidence["reason"] == "clean_block_without_cross_confirmation"


def test_full_matrix_3_4_10_end_to_end_is_bloqueo_esperado():
    """Reproduce el flujo completo con datos con forma idéntica a la
    salida real de client_matrix.py en 3.4.10 (ver RESULTS.md): la
    identidad autorizada confirma la tool funcionando, por lo que el
    'Unknown tool' de la identidad restringida sí cuenta como
    BLOQUEO_ESPERADO."""
    raw = {
        "fastmcp_version": "3.4.10",
        "cases": [
            {
                "identity": "authorized",
                "tools_list": {"ok": True, "names": ["tagged_tool"]},
                "tools_call": {
                    "ok": True,
                    "returned_text": "DEMO_REACHED",
                    "handler_reached": True,
                },
            },
            {
                "identity": "restricted",
                "tools_list": {"ok": True, "names": []},
                "tools_call": {
                    "ok": False,
                    "handler_reached": False,
                    "error": "ToolError: Unknown tool: 'tagged_tool'",
                },
            },
        ],
    }
    verdicts = _verdicts(verify_matrix_output(raw))
    assert verdicts["restricted:tools_call"] == Verdict.BLOQUEO_ESPERADO.value


# ---------------------------------------------------------------------
# Regresión end-to-end contra los datos reales ya capturados del
# laboratorio (matriz de aceptación del punto 2).
# ---------------------------------------------------------------------

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

RAW_3_4_9 = {
    "fastmcp_version": "3.4.9",
    "cases": [
        {
            "identity": "authorized",
            "tools_list": {"ok": True, "names": ["tagged_tool"]},
            "tools_call": {"ok": True, "returned_text": "DEMO_REACHED", "handler_reached": True},
        },
        {
            "identity": "restricted",
            "tools_list": {"ok": True, "names": []},
            "tools_call": {"ok": True, "returned_text": "DEMO_REACHED", "handler_reached": True},
        },
    ],
}

RAW_3_4_10 = {
    "fastmcp_version": "3.4.10",
    "cases": [
        {
            "identity": "authorized",
            "tools_list": {"ok": True, "names": ["tagged_tool"]},
            "tools_call": {"ok": True, "returned_text": "DEMO_REACHED", "handler_reached": True},
        },
        {
            "identity": "restricted",
            "tools_list": {"ok": True, "names": []},
            "tools_call": {
                "ok": False,
                "handler_reached": False,
                "error": "ToolError: Unknown tool: 'tagged_tool'",
            },
        },
    ],
}


def test_acceptance_matrix_3_4_9():
    verdicts = _verdicts(verify_matrix_output(RAW_3_4_9))
    for case, expected_verdict in ACCEPTANCE_MATRIX["3.4.9"].items():
        assert verdicts[case] == expected_verdict, f"{case}: {verdicts[case]} != {expected_verdict}"


def test_acceptance_matrix_3_4_10():
    verdicts = _verdicts(verify_matrix_output(RAW_3_4_10))
    for case, expected_verdict in ACCEPTANCE_MATRIX["3.4.10"].items():
        assert verdicts[case] == expected_verdict, f"{case}: {verdicts[case]} != {expected_verdict}"


if __name__ == "__main__":
    import sys

    tests = [
        test_401_auth_failure_is_indeterminado_even_when_expected_deny,
        test_401_auth_failure_is_indeterminado_even_when_expected_allow,
        test_connection_level_401_from_client_matrix_is_indeterminado,
        test_unknown_tool_with_cross_confirmation_is_bloqueo_esperado,
        test_unknown_tool_without_cross_confirmation_is_indeterminado,
        test_full_matrix_3_4_10_end_to_end_is_bloqueo_esperado,
        test_acceptance_matrix_3_4_9,
        test_acceptance_matrix_3_4_10,
    ]
    failures = 0
    for t in tests:
        try:
            t()
            print(f"PASS  {t.__name__}")
        except AssertionError as e:
            failures += 1
            print(f"FAIL  {t.__name__}: {e}")
    print(f"\n{len(tests) - failures}/{len(tests)} pruebas pasaron")
    sys.exit(1 if failures else 0)
