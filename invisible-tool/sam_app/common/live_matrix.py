"""
Ejecuta la misma matriz que invisible-tool/client_matrix.py
(tools/list + tools/call para las identidades "authorized" y
"restricted"), pero contra la fixture FastMCP 3.4.10 embebida en el
propio proceso Lambda (fixture_3410.EmbeddedFixtureServer), en vez de
contra un proceso server_lab.py externo.

La lógica de qué cuenta como "handler alcanzado" y qué forma tiene el
registro por caso es intencionalmente idéntica a client_matrix.py, para
que verifier.py pueda consumir esta salida sin ningún cambio: esta es
la garantía de que "3.4.10 · comprobación en vivo" usa el mismo
verificador y la misma matriz de aceptación que ya pasaron con
DynamoDB Local y con el AWS Emulator.
"""
from __future__ import annotations

import asyncio
import importlib.metadata

from fastmcp import Client
from fastmcp.client.transports import StreamableHttpTransport
from fastmcp.exceptions import ToolError

from .fixture_3410 import AUTHORIZED_TOKEN, MARKER, RESTRICTED_TOKEN, EmbeddedFixtureServer

try:
    FASTMCP_VERSION = importlib.metadata.version("fastmcp")
except importlib.metadata.PackageNotFoundError:  # pragma: no cover
    FASTMCP_VERSION = "unknown"


async def _run_identity(url: str, identity: str, token: str) -> dict:
    transport = StreamableHttpTransport(url, auth=token)
    record: dict = {"identity": identity}

    try:
        async with Client(transport) as client:
            try:
                tools = await client.list_tools()
                names = [t.name for t in tools]
                record["tools_list"] = {"ok": True, "names": names}
            except Exception as exc:  # noqa: BLE001
                record["tools_list"] = {"ok": False, "error": f"{type(exc).__name__}: {exc}"}

            try:
                result = await client.call_tool("tagged_tool", {})
                text = None
                if result.content:
                    first = result.content[0]
                    text = getattr(first, "text", None)
                handler_reached = text == MARKER
                record["tools_call"] = {
                    "ok": True,
                    "returned_text": text,
                    "handler_reached": handler_reached,
                }
            except ToolError as exc:
                record["tools_call"] = {
                    "ok": False,
                    "handler_reached": False,
                    "error": f"ToolError: {exc}",
                }
            except Exception as exc:  # noqa: BLE001
                record["tools_call"] = {
                    "ok": False,
                    "handler_reached": False,
                    "error": f"{type(exc).__name__}: {exc}",
                }
    except Exception as exc:  # noqa: BLE001
        failure = {"ok": False, "error": f"{type(exc).__name__}: {exc}"}
        record.setdefault("tools_list", dict(failure))
        record.setdefault("tools_call", {**failure, "handler_reached": False})

    return record


async def _run_matrix_async() -> dict:
    fixture = EmbeddedFixtureServer()
    fixture.start()

    # Orden fijo y deliberado: restringido primero, autorizado después
    # como control. La pantalla de demo (handler Lambda / CLI) debe
    # respetar este mismo orden al presentar los resultados.
    results = []
    for identity, token in (
        ("restricted", RESTRICTED_TOKEN),
        ("authorized", AUTHORIZED_TOKEN),
    ):
        results.append(await _run_identity(fixture.url, identity, token))

    return {"fastmcp_version": FASTMCP_VERSION, "cases": results}


def run_matrix() -> dict:
    """Punto de entrada síncrono para el handler Lambda. Devuelve el
    mismo formato que client_matrix.py imprime por stdout (un dict con
    "fastmcp_version" y "cases"), listo para pasar a verifier.py."""
    return asyncio.run(_run_matrix_async())
