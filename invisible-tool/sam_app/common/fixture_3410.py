"""
Fixture FastMCP 3.4.10 EMPAQUETADA DENTRO DE LAMBDA, controlada por el
proyecto (no descargada en tiempo de ejecución): usa exactamente la
misma configuración de servidor que invisible-tool/server_lab.py
(mismo tool, mismos tags, mismo ToolTransform, mismas dos identidades
StaticTokenVerifier), fijada a fastmcp==3.4.10 en requirements.txt para
que la demo en vivo sea la versión corregida.

## Por qué corre un servidor HTTP en loopback dentro del propio proceso
Lambda, en vez de usar el transporte in-process `Client(server)`

Se probó primero el transporte in-process
(`fastmcp.client.transports.FastMCPTransport`, que conecta un Client
directo a una instancia FastMCP sin sockets). Ese transporte NO separa
identidades: el token Bearer viaja en el header HTTP `Authorization`,
que un transporte in-process no tiene. Prueba en vivo (sin este
módulo, directo contra server_lab.build_server()):

    Client(server) sin ningún token -> tools_list: [] (todo tratado
    como "sin token", igual para cualquier identidad que se intente
    pasar). No hay forma soportada de inyectar un AccessToken
    sintético en esa ruta: fastmcp.server.dependencies.get_access_token
    lee del scope de la petición HTTP o de un contextvar que puebla el
    middleware de autenticación HTTP, no un parámetro del Client.

Esto es el BLOQUEO concreto documentado en RESULTS.md: la fixture
"más simple" (in-process, sin servidor HTTP) no puede separar
identidades, así que no sirve para esta demo.

La alternativa que SÍ conserva la separación de identidades, y que se
usa aquí, es correr un servidor `streamable-http` real (el mismo
transporte que usa el laboratorio local) en un hilo de background
dentro del propio proceso Lambda, escuchando en 127.0.0.1 en un puerto
efímero elegido en tiempo de ejecución. Nunca se abre un puerto de
escucha hacia la red de Lambda ni hacia internet: el bind es loopback
y el propio proceso es también el cliente. Se verificó en vivo que esto
preserva la separación de identidades (authorized ve y ejecuta
tagged_tool; restricted ni la ve ni puede ejecutarla).

Esto es la "alternativa serverless más pequeña" para esta fase: un
único Lambda que arranca su propio servidor efímero por invocación, en
vez de un servicio FastMCP de larga duración (que no tiene cabida en el
modelo de ejecución de Lambda).
"""
from __future__ import annotations

import os
import socket
import threading
import time

# Desactiva el banner ASCII de inicio de FastMCP: en Lambda esto solo
# ensucia los logs de CloudWatch en cada invocación, no cambia ningún
# comportamiento de autorización ni de transporte.
os.environ.setdefault("FASTMCP_SHOW_SERVER_BANNER", "false")

from fastmcp import FastMCP
from fastmcp.server.auth import restrict_tag
from fastmcp.server.auth.providers.jwt import StaticTokenVerifier
from fastmcp.server.transforms.tool_transform import ToolTransform
from fastmcp.tools.base import Tool
from fastmcp.tools.tool_transform import ToolTransformConfig

MARKER = "DEMO_REACHED"
AUTHORIZED_TOKEN = "authorized-demo-token"
RESTRICTED_TOKEN = "restricted-demo-token"

_auth = StaticTokenVerifier(
    tokens={
        AUTHORIZED_TOKEN: {"client_id": "authorized-demo", "scopes": ["admin"]},
        RESTRICTED_TOKEN: {"client_id": "restricted-demo", "scopes": []},
    }
)


def build_server() -> FastMCP:
    """Idéntico a invisible-tool/server_lab.py::build_server(). Se
    duplica deliberadamente (en vez de importar server_lab) para que
    el paquete Lambda no dependa de archivos fuera de sam_app/ y para
    que el pin de versión (fastmcp==3.4.10 en requirements.txt) sea
    explícito e inequívoco en este componente."""
    server = FastMCP("invisible-tool-lambda-fixture", auth=_auth)
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


def _free_loopback_port() -> int:
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.bind(("127.0.0.1", 0))
    port = s.getsockname()[1]
    s.close()
    return port


class EmbeddedFixtureServer:
    """Arranca el servidor FastMCP 3.4.10 en un hilo de background,
    bindeado SOLO a 127.0.0.1, dentro del propio proceso Lambda. Vive
    mientras dure la invocación; no persiste entre invocaciones (cada
    cold/warm start que lo necesite vuelve a arrancarlo)."""

    def __init__(self) -> None:
        self.port = _free_loopback_port()
        self._server = build_server()
        self._thread = threading.Thread(target=self._run, daemon=True)

    def _run(self) -> None:
        self._server.run(
            transport="streamable-http",
            host="127.0.0.1",
            port=self.port,
            log_level="warning",
        )

    def start(self, ready_timeout_s: float = 5.0) -> None:
        self._thread.start()
        # Espera activa corta a que el socket acepte conexiones, en vez
        # de un sleep fijo: más rápido y más confiable en un entorno
        # Lambda con CPU variable.
        deadline = time.time() + ready_timeout_s
        while time.time() < deadline:
            try:
                with socket.create_connection(("127.0.0.1", self.port), timeout=0.2):
                    return
            except OSError:
                time.sleep(0.05)
        raise RuntimeError(
            f"La fixture FastMCP 3.4.10 embebida no abrió el puerto "
            f"127.0.0.1:{self.port} a tiempo."
        )

    @property
    def url(self) -> str:
        return f"http://127.0.0.1:{self.port}/mcp"
