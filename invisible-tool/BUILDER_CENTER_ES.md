# Invisible Tool — hacer visible un hueco de autorización oculto, y después demostrar la corrección

**Video:** [MARCADOR — agregar aquí el enlace al video antes de publicar]

## El problema

Los servidores MCP construidos con FastMCP pueden aplicar un chequeo de
autorización a una herramienta, y luego transformar esa herramienta
(renombrarla, cambiarle etiquetas, modificar sus metadatos) antes de
exponerla. Un aviso de seguridad real, aceptado por los mantenedores —
[GHSA-7xgj-8392-5q4r](https://github.com/advisories/GHSA-7xgj-8392-5q4r)
— reporta que `tools/list` de FastMCP sí reevaluaba correctamente la
autorización contra la herramienta *final, ya transformada*, pero la
ruta directa `tools/call` no lo hacía: resolvía la herramienta
transformada y la ejecutaba sin volver a aplicar ese mismo chequeo. Un
llamador que ya conoce (o adivina) el nombre de la herramienta podía
invocarla directamente, evitando la decisión de autorización que
`tools/list` ya había tomado por él, aunque la herramienta nunca
apareciera en su listado.

Afectadas: FastMCP 3.0.0–3.4.9 (y 4.0.0–4.1.1). Corregido en FastMCP
3.4.10 (y 4.1.2). Este hueco es fácil de pasar por alto porque el
síntoma se ve correcto desde afuera: la herramienta es invisible. Solo
probar la ruta de *ejecución*, no solo la de *listado*, lo revela.

## La solución: Invisible Tool

Invisible Tool reproduce exactamente este aviso con dos identidades
sintéticas — `authorized` (tiene el scope requerido) y `restricted`
(no lo tiene) — contra una única herramienta inocua que devuelve un
marcador fijo en vez de cualquier secreto real. Para cada identidad,
ejecuta tanto `tools/list` como `tools/call` y clasifica lo observado
en una de cinco categorías, distinguiendo:

- **acceso esperado** (la identidad autorizada alcanza el handler),
- **bloqueo esperado** (la identidad restringida queda bloqueada),
- **acceso indebido** (la identidad restringida alcanza el handler de
  todas formas — la vulnerabilidad),
- y, de forma crítica, **indeterminado** — un fallo de sesión o de
  transporte (p. ej. un HTTP 401, una conexión caída) nunca se
  confunde con un bloqueo de autorización limpio. Sin esa distinción,
  una conexión rota podría confundirse con un control de seguridad que
  sí está funcionando.

### Evidencia de laboratorio vs. comprobación en vivo — dos tipos de prueba distintos

- **FastMCP 3.4.9 · evidencia del laboratorio**: capturada una vez, en
  local, ejecutando la versión real afectada de FastMCP en un entorno
  aislado. Es prueba histórica de que la vulnerabilidad es real y
  reproducible exactamente como la describe el aviso: la llamada
  directa de la identidad restringida alcanza el handler y devuelve el
  marcador, aunque la herramienta estuviera oculta de su listado.
- **FastMCP 3.4.10 · comprobación en vivo**: se ejecuta de nuevo, a
  demanda, dentro de la función Lambda desplegada en AWS, cada vez que
  alguien hace clic en "ejecutar comprobación en vivo" en la demo. No
  es una captura de pantalla estática: es la versión corregida de
  FastMCP ejecutándose ahora mismo, en una cuenta real de AWS,
  demostrando que la identidad restringida sigue bloqueada bajo las
  mismas condiciones que fallaban en 3.4.9.

Mantener estas dos evidencias separadas importa: el laboratorio
demuestra que el error existió; la comprobación en vivo demuestra que
la corrección se sostiene, hoy, en infraestructura real de producción,
no solo en una corrida de prueba local capturada una vez y nunca
vuelta a verificar.

## Cómo se conectan los servicios

```
Navegador (demo bilingüe)
   │ POST /demo/run   GET /demo/report/{run_id}
   ▼
API Gateway  →  Lambda (ejecuta FastMCP 3.4.10 embebido, ambas identidades)
                   │ escribe el informe verificado con un run_id
                   ▼
              Tabla DynamoDB
                   ▲
Lambda (recupera un informe por run_id)  ←───────────┘
```

- **API Gateway** expone dos rutas: disparar una comprobación en vivo
  nueva, y recuperar cualquier informe pasado por su ID.
- **Lambda** corre el servidor FastMCP 3.4.10 real en un puerto
  loopback dentro de su propio proceso durante la invocación — sin
  servidor de larga duración, sin ningún puerto expuesto más allá del
  entorno de ejecución de la propia función.
- **DynamoDB** guarda cada informe verificado bajo su propio
  identificador, de forma que un informe generado una vez pueda
  recuperarse después por cualquiera que tenga el ID, con sus
  veredictos intactos.
- Las políticas IAM están acotadas al ARN exacto de la tabla única,
  con solo las acciones que cada función necesita (solo escritura para
  el runner, solo lectura para el lector).

Esto se validó de punta a punta contra DynamoDB Local, contra el AWS
Emulator oficial, y, finalmente, contra un despliegue real en AWS
usando SAM — generando y recuperando un informe en vivo en una cuenta
real de AWS, no solo en un emulador local.
