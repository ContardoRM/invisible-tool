"""
Laboratorio GHSA-7xgj-8392-5q4r (FastMCP: autorización post-transformación
omitida en llamadas directas).

Configuración basada en el PoC oficial del aviso (poc_transform_auth.py,
reproducido contra FastMCP 4.1.0 / commit e2fcc41, ver
https://github.com/jlowin/fastmcp/security/advisories/GHSA-7xgj-8392-5q4r):

  - Una única herramienta "tagged_tool", creada con tag {"public"} y una
    política de autorización restrict_tag("admin", scopes=["admin"]).
  - Un ToolTransform que, al transformarla, le añade el tag {"admin"}.
  - La política evalúa los tags del componente FINAL. Antes del fix,
    tools/call resolvía el componente transformado pero reutilizaba (o
    omitía) el chequeo correspondiente a esa versión final en la ruta de
    invocación directa; tools/list sí aplicaba el chequeo correcto.

Diferencia respecto al PoC original: aquí la herramienta no devuelve un
secreto de texto libre sino un marcador sintético fijo "DEMO_REACHED",
como pide el enunciado, y las dos identidades (autorizada/restringida) se
modelan con fastmcp.server.auth.providers.jwt.StaticTokenVerifier, que es
el verificador de tokens estático que los propios mantenedores documentan
para pruebas (no es parte del PoC del aviso; es una pieza estándar de la
librería usada aquí para poder discriminar identidades sobre un transporte
HTTP loopback real en lugar de invocar server.call_tool() directamente en
proceso).

Transporte: streamable-http en 127.0.0.1 (loopback), mismo cliente MCP
para ambas identidades y ambas versiones.
"""
from __future__ import annotations

import os
import sys

from fastmcp import FastMCP
from fastmcp.server.auth import restrict_tag
from fastmcp.server.auth.providers.jwt import StaticTokenVerifier
from fastmcp.tools.base import Tool

try:
    # Nombre del módulo de transform: confirmado en el aviso para v3.x/v4.1.0.
    from fastmcp.server.transforms.tool_transform import ToolTransform
    from fastmcp.tools.tool_transform import ToolTransformConfig
except ImportError as exc:  # pragma: no cover - diagnóstico explícito
    print(f"IMPORT_ERROR: {exc}", file=sys.stderr)
    raise

MARKER = "DEMO_REACHED"

# Identidades ficticias fijas, iguales en ambas versiones.
AUTHORIZED_TOKEN = "authorized-demo-token"
RESTRICTED_TOKEN = "restricted-demo-token"

auth = StaticTokenVerifier(
    tokens={
        AUTHORIZED_TOKEN: {"client_id": "authorized-demo", "scopes": ["admin"]},
        RESTRICTED_TOKEN: {"client_id": "restricted-demo", "scopes": []},
    }
)


def build_server() -> FastMCP:
    server = FastMCP("invisible-tool-lab", auth=auth)
    server.add_tool(
        Tool.from_function(
            lambda: MARKER,
            name="tagged_tool",
            tags={"public"},
            auth=restrict_tag("admin", scopes=["admin"]),
        )
    )
    server.add_transform(
        ToolTransform({"tagged_tool": ToolTransformConfig(tags={"admin"})})
    )
    return server


if __name__ == "__main__":
    port = int(os.environ.get("LAB_PORT", "8800"))
    build_server().run(transport="streamable-http", host="127.0.0.1", port=port)
