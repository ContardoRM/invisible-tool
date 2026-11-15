# Laboratorio GHSA-7xgj-8392-5q4r — resultados observados

## Fuente

Aviso oficial de FastMCP (maintainer-accepted security advisory):
`GHSA-7xgj-8392-5q4r` — "Post-transform component authorization is skipped
on direct calls", leído directamente de:

- https://github.com/advisories/GHSA-7xgj-8392-5q4r
- https://github.com/jlowin/fastmcp/security/advisories/GHSA-7xgj-8392-5q4r

(ambas URLs devuelven el mismo texto del aviso, incluyendo la evaluación
y el PoC de los mantenedores). No se consultaron fuentes de test suite
internas de PrefectHQ/fastmcp más allá de lo citado en el aviso (los
commits `85df42f` y `8649ba5` y los PRs `#5933`/`#5934` están referenciados
en el aviso pero no se abrieron en este laboratorio).

## Hechos extraídos del aviso (no supuestos)

- **Causa raíz**: el listado (`tools/list`) aplica las transformaciones del
  servidor y luego autoriza el componente ya transformado. La ruta de
  invocación directa (`tools/call`) resolvía igualmente el componente
  transformado, pero sin volver a aplicar el chequeo de autorización
  correspondiente a esa versión final.
- **Versiones afectadas**: líneas estables 3.0.0–3.4.9 y 4.0.0–4.1.1. El
  aviso dice explícitamente que el fallo "fue reproducido en v3.4.9 y
  v4.1.0".
- **Versiones corregidas**: 3.4.10 y 4.1.2.
- **Condición necesaria**: un transform de servidor/proveedor/sesión que
  cambie metadatos (p. ej. tags) usados por una política de autorización
  por componente (`AuthCheck`), y un cliente que conozca o adivine el
  nombre final transformado del componente.
- **PoC oficial** (`poc_transform_auth.py`, reproducido contra 4.1.0):
  una tool `tagged_tool` con tag `{"public"}` y `auth=restrict_tag("admin",
  scopes=["admin"])`, transformada por un `ToolTransform` que le añade el
  tag `{"admin"}`. `tools/list` la oculta correctamente; la llamada directa
  (`server.call_tool`) la ejecuta igualmente y devuelve el contenido
  protegido.
- **Remediación recomendada por el aviso**: autorizar el componente final
  transformado en *toda* ruta de resolución/ejecución directa, reutilizando
  un único resolvedor ordenado para list y para operaciones directas.

## Supuestos explícitos de este laboratorio (no son hechos del aviso)

- El aviso construye las identidades en su PoC llamando a `server.call_tool`
  directamente sobre un servidor sin biblioteca de auth real, sin mostrar
  cómo discriminar explícitamente una identidad autorizada de una
  restringida a nivel de protocolo MCP. Para separar dos identidades
  ficticias sobre un transporte real (requisito de esta tarea), este
  laboratorio añade `fastmcp.server.auth.providers.jwt.StaticTokenVerifier`,
  que es un verificador de tokens estático documentado por los propios
  mantenedores para pruebas y desarrollo. **No forma parte del PoC del
  aviso**; es una pieza estándar de la librería usada aquí para generar dos
  tokens Bearer fijos (uno con `scopes=["admin"]`, otro con `scopes=[]`).
- El marcador de retorno `"DEMO_REACHED"` sustituye al texto `"PROTECTED
  SECRET"` del PoC original, por pedido explícito de la tarea (marcador
  sintético, no un secreto real).
- El transporte usado es `streamable-http` en loopback (`127.0.0.1`), no
  "en proceso" puro, para poder ejercer el protocolo MCP completo
  (incluyendo el header `Authorization`) con el mismo cliente MCP real en
  ambas versiones. Esto es una elección de diseño del laboratorio, no algo
  prescrito por el aviso.

## Configuración del laboratorio

- Carpeta: `invisible-tool/`
- `server_lab.py`: construye el servidor FastMCP con:
  - una tool `tagged_tool` (`tags={"public"}`, `auth=restrict_tag("admin",
    scopes=["admin"])`) que devuelve `"DEMO_REACHED"`;
  - un `ToolTransform({"tagged_tool": ToolTransformConfig(tags={"admin"})})`;
  - `auth=StaticTokenVerifier(...)` con dos tokens fijos:
    - `authorized-demo-token` → `scopes=["admin"]` (identidad autorizada)
    - `restricted-demo-token` → `scopes=[]` (identidad restringida)
  - Exactamente la misma configuración se usa para 3.4.9 y para 3.4.10;
    el único cambio entre ejecuciones es la versión de `fastmcp` instalada
    en el entorno efímero.
- `client_matrix.py`: mismo cliente MCP (`fastmcp.Client` sobre
  `StreamableHttpTransport`) para ambas identidades y ambas versiones.
  Para cada identidad ejecuta por separado:
  1. `tools/list` → registra si `tagged_tool` aparece listada.
  2. `tools/call tagged_tool` → registra la respuesta MCP cruda y si el
     handler llegó a ejecutarse (`handler_reached = texto devuelto ==
     "DEMO_REACHED"`), distinguiendo explícitamente ese resultado de un
     bloqueo por autorización (`ToolError: Unknown tool`, que es cómo
     FastMCP oculta el componente denegado en la ruta corregida).
- `run_matrix.sh <version> [puerto]`: levanta `server_lab.py` en un
  entorno `uv run --with fastmcp==<version>` en background sobre un
  puerto loopback dedicado, espera a que responda, ejecuta
  `client_matrix.py` con la misma versión fijada, y mata el servidor al
  salir (`trap cleanup EXIT`). No se reutiliza estado entre versiones:
  cada invocación crea su propio entorno de dependencias aislado vía `uv`.

## Entornos usados

- Python 3.14.3 (resuelto automáticamente por `uv` dentro del entorno
  efímero; no se fijó manualmente un intérprete distinto).
- `fastmcp==3.4.9` (versión afectada, confirmada en PyPI y en el aviso).
- `fastmcp==3.4.10` (versión corregida, confirmada en PyPI y en el aviso).
- Dependencias resueltas automáticamente por `uv run --with fastmcp==X`
  (incluye `mcp==1.30.0`, `httpx==0.28.1`, `pydantic==2.14.3`, etc., en
  ambos casos con el mismo resolutor para minimizar diferencias no
  relacionadas con el fix).

## Cómo repetir la matriz

```bash
cd invisible-tool
./run_matrix.sh 3.4.9    # versión afectada
./run_matrix.sh 3.4.10   # versión corregida
```

Cada ejecución imprime un JSON con los cuatro casos (2 identidades para
esa versión). Puertos por defecto 8800; puede pasarse un segundo
argumento para evitar colisiones si se ejecutan en paralelo.

## Resultados observados

### FastMCP 3.4.9 (afectada) — 2 ejecuciones, resultado idéntico

| Identidad   | tools/list devuelve "tagged_tool" | tools/call: handler ejecutado | tools/call: texto devuelto |
|-------------|:---:|:---:|---|
| authorized  | sí  | sí  | `DEMO_REACHED` |
| restricted  | **no** | **sí** | `DEMO_REACHED` |

La identidad restringida no ve la tool en el listado, pero la llamada
directa `tools/call` igualmente alcanza el handler y devuelve el
marcador. Esto reproduce exactamente el comportamiento descrito en el
aviso para 3.4.9: el chequeo de autorización del componente final
transformado se omite en la ruta de invocación directa.

### FastMCP 3.4.10 (corregida) — 2 ejecuciones, resultado idéntico

| Identidad   | tools/list devuelve "tagged_tool" | tools/call: handler ejecutado | tools/call: resultado |
|-------------|:---:|:---:|---|
| authorized  | sí  | sí  | `DEMO_REACHED` |
| restricted  | no  | **no** | `ToolError: Unknown tool: 'tagged_tool'` |

En 3.4.10 la identidad restringida queda bloqueada tanto en `tools/list`
como en `tools/call`: el handler no se ejecuta y el servidor responde
como si la tool no existiera (coincide con la recomendación del aviso de
"shadowear" el componente denegado en toda ruta, no solo en el listado).
La identidad autorizada funciona de forma idéntica en ambas versiones.

### Contraste

| Caso                                  | 3.4.9 | 3.4.10 |
|----------------------------------------|-------|--------|
| autorizado, tools/list                 | lista la tool | lista la tool |
| autorizado, tools/call                  | ejecuta, `DEMO_REACHED` | ejecuta, `DEMO_REACHED` |
| restringido, tools/list                 | no lista (ya corregido desde antes del fix) | no lista |
| restringido, tools/call                 | **ejecuta, `DEMO_REACHED`** | **bloqueado, `ToolError`** |

El único cambio de comportamiento entre versiones es la fila
"restringido, tools/call", que es exactamente la vulnerabilidad descrita
en GHSA-7xgj-8392-5q4r: `tools/list` ya ocultaba el componente en ambas
versiones (autorización correcta en la ruta de listado), pero solo
3.4.10 aplica la misma autorización en la ruta de invocación directa.

## Estado (fase 1)

Contraste reproducible obtenido en menos de 30 minutos. Las dos
ejecuciones repetidas por versión dieron resultados idénticos (sin
flakiness observada).

---

# Fase 2: verificador de expectativas e integración con un emulador local

## Verificador (`verifier.py`)

Compara la salida cruda de `client_matrix.py` contra una matriz de
expectativas fija (`authorized` → debe poder listar y llamar;
`restricted` → no debe poder listar ni llamar) y clasifica cada caso
(`<identidad>:tools_list` y `<identidad>:tools_call`) en una de cuatro
categorías:

- **ACCESO_INDEBIDO**: la identidad restringida alcanzó el handler (o
  vio la tool listada) cuando la política lo prohíbe. Es la categoría
  que detecta la vulnerabilidad del aviso.
- **BLOQUEO_ESPERADO**: la identidad restringida fue bloqueada
  correctamente.
- **ACCESO_LEGITIMO**: la identidad autorizada accedió correctamente.
- **ACCESO_LEGITIMO_FALLIDO**: la identidad autorizada no pudo acceder
  (falla de disponibilidad, no es la vulnerabilidad que se busca, pero
  tampoco debe ocultarse).
- **INDETERMINADO**: la llamada no tuvo éxito por un motivo de
  transporte, o por un **fallo de autenticación de sesión** (HTTP
  401/403, token inválido), y por lo tanto no permite afirmar nada sobre
  la política de autorización del servidor para ese componente.

### Corrección aplicada: distinguir 401/autenticación de un bloqueo de autorización limpio

La primera versión del verificador trataba cualquier error no
reconocido como transporte ("Unauthorized"/"Forbidden" incluidos en los
marcadores de "bloqueo limpio"), lo cual mezclaba dos causas muy
distintas: (a) el servidor evaluó la identidad y decidió ocultar el
componente (bloqueo de autorización de la aplicación), y (b) el canal
rechazó la sesión antes de llegar a esa decisión (fallo de
autenticación). Se corrigió así:

- `client_matrix.py`: la conexión MCP completa (`async with Client(...)
  as client:`) ahora está envuelta en un `try/except`. Un 401 real
  ocurre en el *handshake* de conexión, no dentro de una llamada
  individual (se confirmó en vivo: un token no registrado en
  `StaticTokenVerifier` produce `httpx.HTTPStatusError: Client error
  '401 Unauthorized'` al hacer `__aenter__`, antes de poder intentar
  `tools/list` o `tools/call`). Antes de esta corrección esa excepción
  no se capturaba y abortaba todo el script; ahora se registra como
  fallo de ambas observaciones (`tools_list` y `tools_call`) con el
  mensaje de error, sin inventar un resultado.
- `verifier.py`: se separaron los marcadores en tres grupos —
  `TRANSPORT_ERROR_TYPES` (fallo de red/canal), `AUTH_FAILURE_MARKERS`
  (`HTTPStatusError`, `401`, `403`, `Unauthorized`, `Forbidden`,
  `AuthenticationError`, `InvalidToken` → siempre `INDETERMINADO`,
  nunca `BLOQUEO_ESPERADO` ni `ACCESO_INDEBIDO`), y
  `AUTHZ_BLOCK_ERROR_MARKERS` (`Unknown tool`, `ToolError`, `not
  found`, `PermissionError` → posible bloqueo de autorización limpio
  de la aplicación, sujeto a la comprobación cruzada de abajo).
- **Evidencia cruzada obligatoria**: `ToolError: Unknown tool` para la
  identidad restringida solo cuenta como `BLOQUEO_ESPERADO` si, en la
  **misma ejecución**, la identidad `authorized` confirmó que
  `tagged_tool` existe y responde con el marcador esperado
  (`tool_confirmed_working=True`, calculado por
  `_tool_confirmed_working()` a partir del propio lote de resultados).
  Sin esa confirmación, el mismo error queda como `INDETERMINADO`
  (`reason: clean_block_without_cross_confirmation`), porque un
  "Unknown tool" también podría significar que el componente nunca se
  registró en el servidor, no que la política lo ocultó correctamente.

### Pruebas de regresión (`test_verifier.py`)

8 pruebas, ejecutables con `python3 test_verifier.py` o con
`uv run --with pytest -- python3 -m pytest test_verifier.py -v`:

| Prueba | Qué fija |
|---|---|
| `test_401_auth_failure_is_indeterminado_even_when_expected_deny` | 401 con `expected=deny` → `INDETERMINADO` (no `BLOQUEO_ESPERADO`) |
| `test_401_auth_failure_is_indeterminado_even_when_expected_allow` | 401 con `expected=allow` → `INDETERMINADO` (no `ACCESO_LEGITIMO`) |
| `test_connection_level_401_from_client_matrix_is_indeterminado` | 401 de **conexión** (forma real que produce `client_matrix.py`) → `INDETERMINADO` en ambas observaciones |
| `test_unknown_tool_with_cross_confirmation_is_bloqueo_esperado` | `Unknown tool` + `tool_confirmed_working=True` → `BLOQUEO_ESPERADO` |
| `test_unknown_tool_without_cross_confirmation_is_indeterminado` | `Unknown tool` sin confirmación cruzada → `INDETERMINADO` |
| `test_full_matrix_3_4_10_end_to_end_is_bloqueo_esperado` | flujo completo con forma idéntica a la salida real de 3.4.10 |
| `test_acceptance_matrix_3_4_9` | los 4 veredictos de 3.4.9 contra la matriz de aceptación del punto 2 |
| `test_acceptance_matrix_3_4_10` | los 4 veredictos de 3.4.10 contra la matriz de aceptación del punto 2 |

Resultado observado:

```
$ uv run --with pytest -- python3 -m pytest test_verifier.py -v
============================== 8 passed in 0.02s ===============================
```

El informe que produce `build_report_document` sigue guardando
únicamente: versión objetivo, marca de tiempo, y por caso: nombre del
caso, identidad, expectativa, veredicto y evidencia mínima (nombres de
tools listadas, `handler_reached`, `marker_confirmed`,
`tool_confirmed_working`, clase de excepción y un motivo corto). **No
se guardan tokens** (`authorized-demo-token` / `restricted-demo-token`
nunca se serializan) **ni cuerpos de respuesta MCP crudos**.

Resultado del verificador corregido contra los datos reales del
laboratorio (re-ejecutado en esta fase, ver sección de integración más
abajo para la corrida completa):

- **3.4.9**: `restricted:tools_call` → `ACCESO_INDEBIDO` (handler
  alcanzado y marcador confirmado). Resto de casos como se espera.
- **3.4.10**: `restricted:tools_call` → `BLOQUEO_ESPERADO`, con
  `tool_confirmed_working: true` en la evidencia (la identidad
  autorizada confirmó la tool funcionando en la misma corrida). Resto
  de casos `ACCESO_LEGITIMO`/`BLOQUEO_ESPERADO`. Ningún
  `ACCESO_INDEBIDO`.

## Integración verifica también el RESULTADO DE SEGURIDAD, no solo la persistencia

`integration_test.py` incorpora `ACCEPTANCE_MATRIX` (el veredicto exacto
esperado por caso y versión, igual a la tabla del punto 2) y
`check_security_outcome(report, expected)`, que se llama dos veces:

1. **Antes de tocar DynamoDB** (`pre_persist_problems`), sobre el
   informe recién generado por `verifier.build_report_document`. Si no
   coincide con la matriz, la integración se aborta con `exit 3` sin
   llegar a `CreateTable`.
2. **Después de `GetItem`** (`post_persist_problems`), sobre el informe
   *recuperado* de DynamoDB. Si el round-trip perdiera o corrompiera un
   caso, o si el informe recuperado no existe, esto lo detecta con
   `exit 4`, independientemente de que la comprobación de persistencia
   (igualdad byte a byte `fetched == generado`) ya lo hubiera detectado
   como `exit 1`.

`check_security_outcome` señala explícitamente:
- un **caso faltante** (`"caso faltante: '<case>' (se esperaba
  <veredicto>)"`),
- un **veredicto que cambió** (`"veredicto inesperado en '<case>': se
  obtuvo X, se esperaba Y"`),
- un **caso no esperado** con veredicto `ACCESO_INDEBIDO` o
  `INDETERMINADO` que la matriz no cubre (para no dejarlo pasar en
  silencio si el laboratorio cambia de forma).

Se probó manualmente que la función detecta ambos fallos pedidos:

```python
# Veredicto cambiado (restricted:tools_call forzado a ACCESO_INDEBIDO
# en 3.4.10, donde se esperaba BLOQUEO_ESPERADO):
# -> "[3.4.10] veredicto inesperado en 'restricted:tools_call':
#     se obtuvo ACCESO_INDEBIDO, se esperaba BLOQUEO_ESPERADO"

# Caso faltante (restricted:tools_call ausente en 3.4.9):
# -> "[3.4.9] caso faltante: 'restricted:tools_call'
#     (se esperaba ACCESO_INDEBIDO)"
```

Resumen de códigos de salida de `integration_test.py`:

| Exit code | Causa |
|---|---|
| 0 | Todo correcto: persistencia y resultado de seguridad coinciden en ambas versiones |
| 2 | Falta `DDB_LOCAL_ENDPOINT` (abortado antes de crear cliente boto3) |
| 1 | `CreateTable`/`PutItem` fallaron, o lo recuperado no es byte-idéntico a lo generado |
| 3 | El informe generado (antes de persistir) no coincide con `ACCEPTANCE_MATRIX` |
| 4 | El informe recuperado de DynamoDB no coincide con `ACCEPTANCE_MATRIX` |

## Emulador usado para esta corrida verificada: DynamoDB Local

**Fuente**: documentación oficial de AWS, "Deploying DynamoDB locally on
your computer"
(https://docs.aws.amazon.com/amazondynamodb/latest/developerguide/DynamoDBLocal.DownloadingAndRunning.html),
sección "Run DynamoDB local as Docker image". Esa página enlaza
directamente la imagen Docker oficial `amazon/dynamodb-local`
(https://hub.docker.com/r/amazon/dynamodb-local), que es el repositorio
usado en este laboratorio. Se confirmó con `docker pull
amazon/dynamodb-local:latest` (descarga exitosa).

**Ruta Docker en macOS**: no existe una ruta Docker distinta para macOS;
la guía oficial usa la misma imagen bajo Docker Desktop (que es el
runtime Docker usado aquí: Docker Desktop 27.4.0, contexto
`desktop-linux`). No hay un `.dmg` nativo de DynamoDB Local; la
alternativa no-Docker es el JAR ejecutable con JRE 17+, que no se usó en
este laboratorio.

**Endpoint y credenciales**: el proceso de prueba exige la variable
`DDB_LOCAL_ENDPOINT` (por convención de este laboratorio, no un nombre
estándar de AWS) y usa credenciales estáticas falsas documentadas por la
propia guía de AWS para DynamoDB Local (`fakeMyKeyId` /
`fakeSecretAccessKey`, región `fakeRegion`). Nunca se leen credenciales
de `~/.aws` ni de variables `AWS_*` del entorno real.

### Bloqueo explícito si falta el endpoint

`dynamo_store.require_local_endpoint()` se llama **antes** de construir
cualquier cliente boto3. Si `DDB_LOCAL_ENDPOINT` no está definido, o si
contiene `amazonaws.com` (señal de que no es local), la función lanza
`MissingLocalEndpointError` y el programa aborta con exit code 2, sin
haber importado boto3 para uso real ni haber creado un cliente:

```
$ unset DDB_LOCAL_ENDPOINT
$ uv run --with boto3 -- python3 integration_test.py
ABORT: DDB_LOCAL_ENDPOINT no está definido. Abortando antes de crear un
cliente DynamoDB: no se intentará contactar un endpoint real de AWS. ...
$ echo $?
2
```

### CreateTable, PutItem, GetItem: comportamiento observado

Contra `amazon/dynamodb-local:latest` (modo `-inMemory`, sin
persistencia entre contenedores), las tres operaciones se probaron
primero de forma aislada y luego dentro de la integración completa:

| Operación | Resultado observado | Código |
|---|---|---|
| CreateTable | OK, tabla `invisible_tool_reports` queda `ACTIVE` | 200 |
| PutItem (3.4.9) | OK | 200 |
| PutItem (3.4.10) | OK | 200 |
| GetItem (3.4.9) | OK, `found: true` | 200 |
| GetItem (3.4.10) | OK, `found: true` | 200 |

**No se observó ningún 501** en esta imagen/versión del emulador para
estas tres operaciones. `dynamo_store.py` sí contempla ese caso: si
cualquier operación falla, se registra `{"operation", "ok": false,
"detail": {"http_status": ...}, "error": "..."}` en el log de llamadas, y
`pending_test_after(log)` calcula cuál prueba de la secuencia
(`CreateTable → PutItem → GetItem`) quedó pendiente. Esto se validó
forzando un `PutItem` inválido (falta la clave de rango):

```
PutItem ok=false, http_status=400, code=ValidationException
Prueba pendiente: GetItem
```

confirmando que el mecanismo de registro-de-fallo-y-pendiente funciona
antes de depender de que ocurra un 501 real.

## Integración ejecutada con datos reales del laboratorio, bajo DynamoDB Local

**Importante**: esta corrida usó `amazon/dynamodb-local`, no el
producto oficial "AWS Emulator" (`github.com/aws/aws-emulator`). Se
reporta aquí bajo su propio nombre, como exige la tarea. El intento
contra el AWS Emulator oficial, y el motivo por el que queda pendiente,
está en la sección "Fase 3" más abajo.

`integration_test.py`:

1. Exige `DDB_LOCAL_ENDPOINT` (si falta, aborta antes de tocar boto3).
2. Ejecuta `server_lab.py` + `client_matrix.py` **de verdad** para
   `fastmcp==3.4.9` y `fastmcp==3.4.10` (mismo laboratorio de la fase 1,
   no datos de ejemplo).
3. Pasa cada salida cruda por `verifier.build_report_document`.
4. Comprueba el resultado de seguridad del informe generado contra
   `ACCEPTANCE_MATRIX` (aborta con `exit 3` si no coincide, antes de
   tocar DynamoDB).
5. CreateTable (idempotente) → PutItem del informe 3.4.9 → PutItem del
   informe 3.4.10 (mismo `report_id`, distinta `target_version` como
   clave de rango) → GetItem de cada versión.
6. Compara cada informe recuperado con el informe generado en memoria
   (persistencia) y vuelve a comprobar el resultado de seguridad sobre
   lo recuperado (`exit 4` si no coincide).

### Resultado observado de la integración completa (DynamoDB Local)

```
$ docker run -d --name ddb-lab -p 127.0.0.1:8000:8000 \
    amazon/dynamodb-local:latest -jar DynamoDBLocal.jar -sharedDb -inMemory
$ export DDB_LOCAL_ENDPOINT=http://127.0.0.1:8000
$ uv run --with boto3 --with fastmcp -- python3 integration_test.py
...
=== Comprobación de persistencia ===
3.4.9 recuperado y coincide con lo generado: True
3.4.10 recuperado y coincide con lo generado: True
Ambas versiones coexisten bajo report_id='ghsa-7xgj-8392-5q4r-lab': True
=== Comprobación de resultado de seguridad (sobre lo recuperado) ===
  Todos los casos coinciden con la matriz de aceptación para ambas versiones.
Prueba pendiente: ninguna (CreateTable, PutItem y GetItem completados)
Resultado de la integración: OK
$ echo $?
0
```

El ítem recuperado por `GetItem` para `target_version="3.4.9"` conserva
el veredicto `ACCESO_INDEBIDO` en `restricted:tools_call`; el recuperado
para `target_version="3.4.10"` conserva `BLOQUEO_ESPERADO` en el mismo
caso, con `tool_confirmed_working: true` en la evidencia. Ambas
versiones quedan almacenadas simultáneamente sin pisarse (clave
compuesta `report_id` + `target_version`), y la recuperación de una no
afecta ni borra la otra. Esto se verificó tanto por igualdad exacta del
documento (persistencia) como por comparación contra la matriz de
veredictos esperados (resultado de seguridad), en ambos sentidos
(generado y recuperado).

Versión del emulador: `amazon/dynamodb-local:latest` descargado el
2026-11-14/15 (`docker pull amazon/dynamodb-local:latest`, digest
`sha256:6ada631ec7aa5fc83446855eb17233e3dad184fec47477e8140c6c569cfe0c86`).

## Comando para repetir la prueba de integración (DynamoDB Local)

```bash
cd invisible-tool
./run_integration.sh            # usa el puerto 8000 por defecto
./run_integration.sh 8010       # o un puerto alternativo
```

El script levanta un contenedor `amazon/dynamodb-local:latest` efímero
en `127.0.0.1:<puerto>` (modo `-inMemory`), exporta
`DDB_LOCAL_ENDPOINT`, corre `integration_test.py`, y destruye el
contenedor al salir (éxito o fallo), vía `trap cleanup EXIT`.

Requisitos para ejecutarlo: Docker Desktop corriendo, `uv` instalado,
acceso de red saliente para que `uv run --with ...` resuelva `fastmcp` y
`boto3` desde PyPI (no se requiere acceso a AWS real).

## Hook manual de Kiro

Se agregó `.kiro/hooks/invisible-tool-integration.json` (trigger
`UserPromptSubmit` con un `matcher` que solo activa el hook si el mensaje
contiene la frase `ejecutar integración invisible-tool` / `ejecutar
integracion invisible-tool` / `run invisible-tool integration`, para que
no se dispare en cada mensaje normal). Ejecuta exactamente
`cd invisible-tool && ./run_integration.sh`.

## Estado (fase 2)

Verificador corregido (distingue 401/autenticación de bloqueo de
autorización limpio, exige confirmación cruzada) y probado con 8
pruebas de regresión, todas en verde. Integración extendida para
verificar también el resultado de seguridad (no solo persistencia),
antes y después de pasar por DynamoDB, con códigos de salida distintos
por tipo de falla. Ejecutada de punta a punta contra DynamoDB Local
real: CreateTable, PutItem, GetItem y la comparación de seguridad
completa pasaron. **Corrección respecto a una sesión anterior**: esta
fase había investigado el repositorio de código fuente
`github.com/aws/aws-emulator` (un proyecto Rust de 437 crates) y
concluyó que ejecutar el AWS Emulator oficial era inviable por falta de
espacio en disco para compilarlo. Esa conclusión era correcta sobre el
repositorio de código, pero ese repositorio **no es la vía que usa un
usuario final**: existe una guía de usuario pública en
`docs.aws.amazon.com/emulator/latest/userguide/` con un **RPM
precompilado** descargable, que sí permite correr el emulador real sin
compilar nada. Esa guía es la que se siguió en esta sesión (Fase 3,
abajo), y el resultado cambia de PENDIENTE a VALIDADO.

---

# Fase 3: ejecución con el producto oficial AWS Emulator (guía de usuario con RPM precompilado)

## Corrección de rumbo respecto a la sesión anterior

La sesión anterior buscó el AWS Emulator en
`github.com/aws/aws-emulator`, un repositorio de **código fuente** en
Rust (framework "EmulatorCore", 437 crates de servicio, sin binario ni
imagen publicados), y concluyó —correctamente para ese repositorio—
que compilarlo exigía ≥100 GB libres y no era viable en este entorno.

Esta sesión usó en cambio la **guía de usuario oficial** del producto,
publicada en `docs.aws.amazon.com/emulator/latest/userguide/`, que es
un sitio de documentación de AWS distinto del repositorio de código y
que no se había consultado antes. Esa guía documenta una build Docker
de segundos (no de horas) a partir de un **paquete RPM ya compilado**
que AWS publica y descarga el propio `Dockerfile` vía `ADD` en tiempo
de build. Se verificó que ese RPM existe y es descargable antes de
usarlo:

```
$ curl -sI -L "https://downloads.aws.com/aws-emulator/packages/aws-emulator/LTS/latest/aws-emulator-aarch64.rpm"
HTTP/2 200
content-length: 161331057
x-amz-meta-package-version: 1.0.385.1
content-disposition: attachment; filename="aws-emulator-1.0.385-1-aarch64.rpm"
```

**Versión del emulador usada: 1.0.385-1** (según el nombre de archivo y
la metadata del RPM `LTS/latest` para `aarch64`, descargado el
2026-11-15).

## 1. Construcción de la imagen: Dockerfile de la guía, RPM aarch64

Siguiendo exactamente
https://docs.aws.amazon.com/emulator/latest/userguide/getting-started-docker.html,
con el RPM Arm (Apple Silicon, confirmado con `uname -m` → `arm64`):

```dockerfile
FROM public.ecr.aws/amazonlinux/amazonlinux:2023-minimal
ADD https://downloads.aws.com/aws-emulator/packages/aws-emulator/LTS/latest/aws-emulator-aarch64.rpm /tmp/aws-emulator.rpm
RUN rpm -i /tmp/aws-emulator.rpm && rm /tmp/aws-emulator.rpm \
    && mkdir -p /home/emulator && chown 1000 /home/emulator
USER 1000
ENV HOME=/home/emulator
EXPOSE 9297
ENTRYPOINT ["aws-emulator", "-b", "0.0.0.0"]
```

```
$ docker build -t aws-emulator .
...
#8 writing image sha256:f7227ace14bb58e5f855028ef76aef44970b5ec6bdfbf525e71994ba7a4b9a4b
#8 naming to docker.io/library/aws-emulator done
```

Construcción exitosa en segundos (descarga del RPM ~161 MB + `rpm -i`),
sin necesidad de Rust/Cargo ni de clonar el repositorio de código.

## 2. Arranque: puerto publicado solo en loopback

```bash
mkdir -p ~/.aws/emulator
PORT=9297
docker run -d --name aws-emulator-lab --memory=2g --memory-swap=2g \
  -p 127.0.0.1:$PORT:$PORT \
  -e HOME="$HOME" -v "$HOME/.aws/emulator:$HOME/.aws/emulator" \
  aws-emulator -p $PORT
```

Log observado al arrancar (confirma HTTPS, autenticación por firma, y
generación de credenciales/CA):

```
{"message":"aws-emulator emulator starting"}
{"message":"request authentication enabled","credentials_file":".../9297/emulator_credentials"}
{"message":"emulator server information","endpoint_url":"https://127.0.0.1:9297","health_check_url":"https://127.0.0.1:9297/__admin/health","ca_file":".../9297/ca.pem",...}
```

`docker ps` confirma el mapeo `127.0.0.1:9297->9297/tcp` (no
`0.0.0.0:9297`, es decir, el puerto del host solo acepta conexiones
loopback, aunque el proceso dentro del contenedor escucha en `0.0.0.0`
porque así lo requiere Docker para poder reenviar el puerto — el
propio emulador lo advierte en su log y la guía aclara que el `-p
127.0.0.1:...` de `docker run` es lo que efectivamente limita el
acceso al host).

Verificación de salud:
```
$ curl -s --cacert ~/.aws/emulator/9297/ca.pem https://127.0.0.1:9297/__admin/health
ok
```

## 3. Configuración de Boto3: credenciales y CA GENERADOS por el emulador (modo nuevo `aws_emulator`)

Siguiendo
https://docs.aws.amazon.com/emulator/latest/userguide/point-sdk-to-emulator.html,
el emulador escribe en `~/.aws/emulator/9297/`:

```
$ ls ~/.aws/emulator/9297/
ca.pem  config  emulator_credentials  truststore.p12

$ cat ~/.aws/emulator/9297/emulator_credentials
[default]
aws_access_key_id = EMULATOR<generado por el emulador en cada arranque>
aws_secret_access_key = <generado por el emulador en cada arranque>
```

(Valores de ejemplo: el emulador genera un par nuevo en cada arranque,
vive solo en `~/.aws/emulator/<puerto>/` fuera del repo, y expira al
detener el contenedor. Los valores reales observados en esta corrida ya
no son válidos: la instancia que los emitió fue destruida.)

`dynamo_store.py` ahora soporta dos modos explícitos vía `STORE_MODE`:

- `STORE_MODE=dynamodb_local` (por defecto, sin cambios de
  comportamiento): credenciales ficticias **fijas**
  (`fakeMyKeyId`/`fakeSecretAccessKey`), endpoint exigido vía
  `DDB_LOCAL_ENDPOINT`.
- `STORE_MODE=aws_emulator` (nuevo): **nunca** usa credenciales fijas.
  `_load_emulator_credentials(port)` lee
  `~/.aws/emulator/<port>/emulator_credentials` y
  `~/.aws/emulator/<port>/ca.pem` generados por el emulador en esa
  corrida concreta, y falla con `MissingLocalEndpointError` si
  cualquiera de los dos archivos no existe (en vez de usar un valor
  por defecto o seguir sin CA).

### Validaciones de "falla si falta la configuración", probadas una por una

```
$ unset AWS_EMULATOR_ENDPOINT; STORE_MODE=aws_emulator ... require_local_endpoint()
BLOQUEADO: STORE_MODE=aws_emulator pero AWS_EMULATOR_ENDPOINT no está
definido. Abortando antes de crear un cliente DynamoDB...

$ AWS_EMULATOR_ENDPOINT=http://127.0.0.1:9297 ... require_local_endpoint()
BLOQUEADO: AWS_EMULATOR_ENDPOINT='http://127.0.0.1:9297' debe ser HTTPS
sobre loopback explícito...

$ AWS_EMULATOR_ENDPOINT=https://example.com:9297 ... require_local_endpoint()
BLOQUEADO: AWS_EMULATOR_ENDPOINT='https://example.com:9297' debe ser
HTTPS sobre loopback explícito...

$ AWS_EMULATOR_ENDPOINT=https://127.0.0.1:9999 ... build_local_client()
BLOQUEADO: No se encontró '~/.aws/emulator/9999/emulator_credentials'.
El AWS Emulator genera este archivo al arrancar...
```

Los cuatro casos abortan **antes** de construir un cliente boto3
(`require_local_endpoint()` o la carga de credenciales corren primero;
`import boto3` dentro de `build_local_client` es lo último que se
alcanza, y solo si todas las validaciones pasaron).

## 4. CreateTable, PutItem, GetItem — resultado observado

Primera prueba aislada (antes de la integración completa), con las
credenciales reales generadas arriba:

| Operación | Resultado | Detalle |
|---|---|---|
| CreateTable | OK | `TableStatus: CREATING` inicialmente (no `ACTIVE` de inmediato, a diferencia de DynamoDB Local) |
| PutItem inmediato tras CreateTable | **ERROR** | `ResourceNotFoundException: Requested resource not found` — la tabla aún no estaba `ACTIVE` |
| DescribeTable en bucle corto | OK | transicionó a `ACTIVE` en bajo medio segundo |
| PutItem (reintentado tras ACTIVE) | OK | HTTP 200 |
| GetItem | OK | ítem recuperado íntegro |

Esto llevó a agregar `dynamo_store.wait_for_table_active()`: una espera
activa corta (`describe_table` en bucle, timeout 15 s) después de
`CreateTable`, inocua para DynamoDB Local (que ya reporta `ACTIVE` de
inmediato: la primera vuelta del bucle lo confirma sin esperar) y
necesaria para el AWS Emulator real.

Con esa corrección, las tres operaciones en limpio (tabla recién
creada, sin reutilizar una anterior):

```
CreateTable: ok=true, detail={"table": "invisible_tool_reports"}   (sin "already_exists")
PutItem:     ok=true
GetItem:     ok=true, found=true
```

**No se observó ningún 501** en CreateTable, PutItem ni GetItem contra
esta versión del AWS Emulator.

## 5. Integración completa con las salidas reales del laboratorio FastMCP

Comando reproducible (construye la imagen si falta, arranca el
contenedor en loopback, exporta `STORE_MODE`/`AWS_EMULATOR_ENDPOINT`,
corre todo, destruye el contenedor al salir):

```bash
cd invisible-tool
./run_integration_aws_emulator.sh            # puerto 9297 por defecto
./run_integration_aws_emulator.sh 9300       # o un puerto alternativo
```

Resultado observado (corrida en limpio, tabla creada de cero):

```
Ejecutando laboratorio real: fastmcp 3.4.9 ...
Ejecutando laboratorio real: fastmcp 3.4.10 ...
...
Modo de almacenamiento: aws_emulator
Usando endpoint local: https://127.0.0.1:9297

=== Comprobación de persistencia ===
3.4.9 recuperado y coincide con lo generado: True
3.4.10 recuperado y coincide con lo generado: True
Ambas versiones coexisten bajo report_id='ghsa-7xgj-8392-5q4r-lab': True

=== Comprobación de resultado de seguridad (sobre lo recuperado) ===
  Todos los casos coinciden con la matriz de aceptación para ambas versiones.

=== Registro de llamadas DynamoDB ===
[
  {"operation": "CreateTable", "ok": true, "detail": {"table": "invisible_tool_reports"}},
  {"operation": "PutItem", "ok": true, "detail": {"report_id": "ghsa-7xgj-8392-5q4r-lab", "target_version": "3.4.9"}},
  {"operation": "PutItem", "ok": true, "detail": {"report_id": "ghsa-7xgj-8392-5q4r-lab", "target_version": "3.4.10"}},
  {"operation": "GetItem", "ok": true, "detail": {"report_id": "ghsa-7xgj-8392-5q4r-lab", "target_version": "3.4.9", "found": true}},
  {"operation": "GetItem", "ok": true, "detail": {"report_id": "ghsa-7xgj-8392-5q4r-lab", "target_version": "3.4.10", "found": true}}
]

Prueba pendiente: ninguna (CreateTable, PutItem y GetItem completados)
Resultado de la integración: OK
$ echo $?
0
```

El veredicto recuperado para `3.4.9` conserva `restricted:tools_call →
ACCESO_INDEBIDO`; el recuperado para `3.4.10` conserva
`restricted:tools_call → BLOQUEO_ESPERADO` con `tool_confirmed_working:
true`. La matriz de aceptación del punto 2
(`authorized:*→ACCESO_LEGITIMO`, `restricted:tools_list→BLOQUEO_ESPERADO`
en ambas versiones, `restricted:tools_call` distinto entre 3.4.9 y
3.4.10) se comprobó **antes** de persistir (`check_security_outcome`
sobre el informe generado) y **después** de `GetItem`
(`check_security_outcome` sobre el informe recuperado), ambas veces sin
discrepancias. Se repitió la corrida completa dos veces (con la tabla
ya existente y con el emulador reiniciado desde cero) con resultado
idéntico, `exit 0` ambas.

## Primera operación que falló, y qué quedó pendiente (si aplica)

No hubo ninguna operación de DynamoDB que fallara en la corrida final
reportada arriba. La única falla observada durante el desarrollo de
esta fase fue `PutItem` → `ResourceNotFoundException` cuando se
intentó inmediatamente después de `CreateTable`, antes de que la tabla
transicionara de `CREATING` a `ACTIVE`; se corrigió agregando la espera
activa descrita en el punto 4, y no volvió a reproducirse en ninguna
corrida posterior.

## Conclusión del punto 2: validación con AWS Emulator — **VALIDADO**

El punto 2 (verificador corregido + integración que comprueba
persistencia y resultado de seguridad contra la matriz de aceptación
exacta) se ejecutó de punta a punta contra el producto oficial **AWS
Emulator** real (imagen construida con el RPM
`aws-emulator-aarch64.rpm` versión 1.0.385-1, siguiendo la guía oficial
de Docker y de configuración de Boto3), con:

- `CreateTable`, `PutItem`, `GetItem` confirmados exitosos (sin 501, ni
  ningún otro código de error, en la corrida final).
- Credenciales y CA generados por el propio emulador, nunca fijos, en
  un modo (`STORE_MODE=aws_emulator`) separado del modo
  `dynamodb_local` existente (que conserva sus credenciales ficticias
  fijas sin cambios).
- Rechazo explícito y verificado de: falta de endpoint, endpoint no
  HTTPS, endpoint no loopback, y credenciales/CA ausentes — en los
  cuatro casos antes de construir el cliente boto3.
- Ambos informes (FastMCP 3.4.9 vulnerable y 3.4.10 corregida)
  persistidos y recuperados con sus veredictos intactos, verificados
  contra la matriz de aceptación tanto antes como después del
  round-trip por DynamoDB.

El despliegue con AWS SAM queda fuera de esta fase, según lo acordado
(corresponde al punto 3 de la siguiente etapa del trabajo).
