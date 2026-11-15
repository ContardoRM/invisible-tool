/*
 * Translation strings for the Invisible Tool demo UI.
 *
 * IMPORTANT: this file translates DISPLAY TEXT ONLY. It never touches:
 *   - verdict codes returned by the API (ACCESO_LEGITIMO,
 *     BLOQUEO_ESPERADO, ACCESO_INDEBIDO, ACCESO_LEGITIMO_FALLIDO,
 *     INDETERMINADO) — these are looked up as object keys below and
 *     mapped to a translated LABEL, but the underlying code from the
 *     JSON response is never renamed or re-serialized.
 *   - JSON field names (run_id, report, cases, case, identity,
 *     verdict, evidence, target_version, source, ...).
 *   - API paths (/demo/run, /demo/report/{run_id}).
 * Keeping the verdict codes and JSON shape untouched is required so
 * the existing verifier.py / test_verifier.py / integration_test.py
 * assertions keep working against the same API, regardless of which
 * UI language is selected.
 */
const TRANSLATIONS = {
  en: {
    title: "Invisible Tool — FastMCP authorization demo",
    subtitle:
      "GHSA-7xgj-8392-5q4r: post-transform tool authorization skipped on direct calls.",
    langLabel: "Language",
    runButton: "Run live check (FastMCP 3.4.10)",
    runningLabel: "Running live check against the embedded FastMCP 3.4.10 fixture…",
    recoverButton: "Recover report by ID",
    runIdPlaceholder: "Report ID (run_id)",
    recoverPlaceholder: "Paste a run_id to look up",
    historicalTitle: "3.4.9 · lab evidence",
    liveTitle: "3.4.10 · live check",
    historicalExplanation:
      "This table is historical evidence captured locally with the affected " +
      "FastMCP 3.4.9, reproducing GHSA-7xgj-8392-5q4r: the restricted identity " +
      "is hidden from tools/list but its direct tools/call still reaches the " +
      "handler (ACCESO_INDEBIDO, 'improper access').",
    liveExplanation:
      "This table is a live check run just now against the corrected FastMCP " +
      "3.4.10, embedded in the demo Lambda. The restricted identity is blocked " +
      "on both tools/list and tools/call (BLOQUEO_ESPERADO, 'expected block'); " +
      "the authorized identity is shown as a control and keeps working " +
      "normally (ACCESO_LEGITIMO, 'legitimate access').",
    restrictedCallLabel: "Restricted identity — tools/call (handler reached?)",
    restrictedListLabel: "Restricted identity — tools/list",
    authorizedCallLabel: "Authorized identity — tools/call (control)",
    authorizedListLabel: "Authorized identity — tools/list",
    handlerReachedYes: "Handler reached — tool executed",
    handlerReachedNo: "Handler NOT reached — blocked before execution",
    handlerReachedUnknown: "Could not determine if the handler executed",
    toolListedYes: "Tool is listed",
    toolListedNo: "Tool is hidden from the listing",
    runIdLabel: "Run ID",
    sourceLabel: "Source",
    generatedAtLabel: "Generated at",
    errorPrefix: "Error",
    errorNetwork: "Network or server error while calling the API.",
    errorNotFound: "No report found for this run_id.",
    errorMissingRunId: "Enter a run_id to recover a report.",
    errorNoApiDetected:
      "Could not detect the API base URL from this page's address. " +
      "Open this page through the deployed API Gateway URL, or add " +
      "?api=https://your-api-id.execute-api.your-region.amazonaws.com/your-stage " +
      "to the address for local testing.",
    verdictLabels: {
      ACCESO_LEGITIMO: "Legitimate access",
      BLOQUEO_ESPERADO: "Expected block",
      ACCESO_INDEBIDO: "Improper access",
      ACCESO_LEGITIMO_FALLIDO: "Legitimate access failed",
      INDETERMINADO: "Indeterminate (session/transport failure)",
    },
    footerNote:
      "Verdict codes, JSON fields and API routes are never translated: " +
      "they stay stable for the existing automated tests.",
  },
  es: {
    title: "Invisible Tool — demo de autorización en FastMCP",
    subtitle:
      "GHSA-7xgj-8392-5q4r: autorización de herramienta post-transformación omitida en llamadas directas.",
    langLabel: "Idioma",
    runButton: "Ejecutar comprobación en vivo (FastMCP 3.4.10)",
    runningLabel: "Ejecutando la comprobación en vivo contra la fixture FastMCP 3.4.10 embebida…",
    recoverButton: "Recuperar informe por ID",
    runIdPlaceholder: "ID del informe (run_id)",
    recoverPlaceholder: "Pega un run_id para buscarlo",
    historicalTitle: "3.4.9 · evidencia del laboratorio",
    liveTitle: "3.4.10 · comprobación en vivo",
    historicalExplanation:
      "Esta tabla es evidencia histórica capturada localmente con la versión " +
      "afectada FastMCP 3.4.9, reproduciendo GHSA-7xgj-8392-5q4r: la identidad " +
      "restringida se oculta en tools/list pero su tools/call directo igual " +
      "alcanza el handler (ACCESO_INDEBIDO).",
    liveExplanation:
      "Esta tabla es una comprobación en vivo recién ejecutada contra la " +
      "versión corregida FastMCP 3.4.10, embebida en el Lambda de la demo. La " +
      "identidad restringida queda bloqueada tanto en tools/list como en " +
      "tools/call (BLOQUEO_ESPERADO); la identidad autorizada se muestra como " +
      "control y sigue funcionando con normalidad (ACCESO_LEGITIMO).",
    restrictedCallLabel: "Identidad restringida — tools/call (¿se ejecutó el handler?)",
    restrictedListLabel: "Identidad restringida — tools/list",
    authorizedCallLabel: "Identidad autorizada — tools/call (control)",
    authorizedListLabel: "Identidad autorizada — tools/list",
    handlerReachedYes: "Handler ejecutado — la herramienta corrió",
    handlerReachedNo: "Handler NO ejecutado — bloqueado antes de correr",
    handlerReachedUnknown: "No se pudo determinar si el handler se ejecutó",
    toolListedYes: "La herramienta aparece listada",
    toolListedNo: "La herramienta está oculta del listado",
    runIdLabel: "ID de la corrida",
    sourceLabel: "Origen",
    generatedAtLabel: "Generado el",
    errorPrefix: "Error",
    errorNetwork: "Error de red o del servidor al llamar a la API.",
    errorNotFound: "No se encontró ningún informe para este run_id.",
    errorMissingRunId: "Ingresa un run_id para recuperar un informe.",
    errorNoApiDetected:
      "No se pudo detectar la URL base de la API a partir de la dirección " +
      "de esta página. Abre esta página a través de la URL desplegada de " +
      "API Gateway, o agrega " +
      "?api=https://tu-api-id.execute-api.tu-region.amazonaws.com/tu-stage " +
      "a la dirección para pruebas locales.",
    verdictLabels: {
      ACCESO_LEGITIMO: "Acceso legítimo",
      BLOQUEO_ESPERADO: "Bloqueo esperado",
      ACCESO_INDEBIDO: "Acceso indebido",
      ACCESO_LEGITIMO_FALLIDO: "Acceso legítimo fallido",
      INDETERMINADO: "Indeterminado (fallo de sesión/transporte)",
    },
    footerNote:
      "Los códigos de veredicto, los campos JSON y las rutas de la API nunca " +
      "se traducen: se mantienen estables para las pruebas automatizadas existentes.",
  },
};

const DEFAULT_LANG = "en";
const LANG_STORAGE_KEY = "invisible-tool-ui-lang";
