"""
Cliente de la matriz de pruebas. Mismo código para FastMCP 3.4.9 y 3.4.10:
el runner selecciona la versión instalando una u otra en el entorno
efímero de `uv run --with fastmcp==<version>`; este script no cambia.

Para cada identidad (autorizada / restringida) contra el servidor local
(server_lab.py, loopback streamable-http):
  1. tools/list -> ¿aparece "tagged_tool" en el listado?
  2. tools/call "tagged_tool" -> ¿la llamada MCP tiene éxito y devuelve
     DEMO_REACHED (el handler se ejecutó), o falla con un error de
     autorización (el handler NO se ejecutó)?

Se registra la respuesta MCP cruda y una conclusión explícita de si el
handler llegó a ejecutarse, distinguiendo esa observación de la de
tools/list (son preguntas independientes según el aviso: el fix "autoriza
los componentes finales transformados" en todas las rutas, no solo en
listado).
"""
from __future__ import annotations

import asyncio
import importlib.metadata
import json
import sys

from fastmcp import Client
from fastmcp.client.transports import StreamableHttpTransport
from fastmcp.exceptions import ToolError

from server_lab import AUTHORIZED_TOKEN, MARKER, RESTRICTED_TOKEN

try:
    FASTMCP_VERSION = importlib.metadata.version("fastmcp")
except importlib.metadata.PackageNotFoundError:  # pragma: no cover
    FASTMCP_VERSION = "unknown"

URL_TEMPLATE = "http://127.0.0.1:{port}/mcp"


async def run_identity(port: int, identity: str, token: str) -> dict:
    transport = StreamableHttpTransport(URL_TEMPLATE.format(port=port), auth=token)
    record: dict = {"identity": identity}

    # La conexión en sí (handshake MCP, incluida la autenticación de
    # sesión) puede fallar antes de poder intentar tools/list o
    # tools/call — por ejemplo un token inválido produce un 401 en
    # __aenter__, no dentro de una llamada individual. Si eso ocurre,
    # ambas observaciones quedan registradas como fallo de conexión en
    # vez de propagar la excepción y abortar todo el script: el
    # verifier.py las reconocerá como INDETERMINADO (fallo de
    # autenticación de sesión), no como bloqueo de autorización.
    try:
        async with Client(transport) as client:
            # Observación 1: tools/list (independiente de tools/call)
            try:
                tools = await client.list_tools()
                names = [t.name for t in tools]
                record["tools_list"] = {"ok": True, "names": names}
            except Exception as exc:  # noqa: BLE001
                record["tools_list"] = {"ok": False, "error": f"{type(exc).__name__}: {exc}"}

            # Observación 2: tools/call directo
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
        # Fallo de conexión/sesión (p. ej. 401 Unauthorized en el
        # handshake): no se pudo intentar ni tools/list ni tools/call.
        failure = {"ok": False, "error": f"{type(exc).__name__}: {exc}"}
        record.setdefault("tools_list", dict(failure))
        record.setdefault("tools_call", {**failure, "handler_reached": False})

    return record


async def main() -> None:
    port = int(sys.argv[1]) if len(sys.argv) > 1 else 8800
    results = []
    for identity, token in (
        ("authorized", AUTHORIZED_TOKEN),
        ("restricted", RESTRICTED_TOKEN),
    ):
        results.append(await run_identity(port, identity, token))
    payload = {"fastmcp_version": FASTMCP_VERSION, "cases": results}
    print(json.dumps(payload, indent=2))


if __name__ == "__main__":
    asyncio.run(main())
