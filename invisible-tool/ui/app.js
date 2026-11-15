/*
 * Invisible Tool demo UI — minimal static page, no build step.
 *
 * Talks to the existing API (POST /demo/run, GET /demo/report/{run_id})
 * exactly as documented in RESULTS.md and sam_app/template.yaml. This
 * file only renders and translates display text: it never renames a
 * JSON field, never changes a verdict code, and never rewrites an API
 * path.
 */

// ---------------------------------------------------------------------
// 3.4.9 · lab evidence (static). This is the real report produced by
// invisible-tool/run_matrix.sh 3.4.9 + verifier.py, captured once and
// embedded here so the "historical evidence" panel does not depend on
// re-running the local, uv-based lab from inside a browser (which is
// not possible). The live Lambda, in contrast, always runs 3.4.10
// fresh on every click of "Run live check".
// ---------------------------------------------------------------------
const LAB_EVIDENCE_349 = {
  target_version: "3.4.9",
  generated_at: "2026-11-15T01:42:41.405336+00:00",
  cases: [
    {
      target_version: "3.4.9",
      case: "authorized:tools_list",
      identity: "authorized",
      expected: "allow",
      verdict: "ACCESO_LEGITIMO",
      evidence: { listed_tagged_tool: true, tool_count: 1 },
    },
    {
      target_version: "3.4.9",
      case: "authorized:tools_call",
      identity: "authorized",
      expected: "allow",
      verdict: "ACCESO_LEGITIMO",
      evidence: { handler_reached: true, marker_confirmed: true },
    },
    {
      target_version: "3.4.9",
      case: "restricted:tools_list",
      identity: "restricted",
      expected: "deny",
      verdict: "BLOQUEO_ESPERADO",
      evidence: { listed_tagged_tool: false, tool_count: 0 },
    },
    {
      target_version: "3.4.9",
      case: "restricted:tools_call",
      identity: "restricted",
      expected: "deny",
      verdict: "ACCESO_INDEBIDO",
      evidence: { handler_reached: true, marker_confirmed: true },
    },
  ],
};

// Display order: restricted call first (does the handler run?), then
// restricted list, then authorized call/list as the control. This is
// a presentation choice only — it never reorders or mutates the
// "cases" array coming from the API/static evidence.
const DISPLAY_ORDER = [
  "restricted:tools_call",
  "restricted:tools_list",
  "authorized:tools_call",
  "authorized:tools_list",
];

function orderedCases(report) {
  const byCase = {};
  for (const c of report.cases) byCase[c.case] = c;
  return DISPLAY_ORDER.map((name) => byCase[name]).filter(Boolean);
}

// ---------------------------------------------------------------------
// i18n
// ---------------------------------------------------------------------
function currentLang() {
  return localStorage.getItem(LANG_STORAGE_KEY) || DEFAULT_LANG;
}

function setLang(lang) {
  localStorage.setItem(LANG_STORAGE_KEY, lang);
  document.documentElement.lang = lang;
  applyTranslations(lang);
}

function t(lang, key) {
  return TRANSLATIONS[lang][key];
}

function applyTranslations(lang) {
  const dict = TRANSLATIONS[lang];
  document.querySelectorAll("[data-i18n]").forEach((el) => {
    const key = el.getAttribute("data-i18n");
    if (dict[key] !== undefined) el.textContent = dict[key];
  });
  document.querySelectorAll("[data-i18n-placeholder]").forEach((el) => {
    const key = el.getAttribute("data-i18n-placeholder");
    if (dict[key] !== undefined) el.setAttribute("placeholder", dict[key]);
  });
  // Re-render any already-displayed report so its translated labels
  // (verdict labels, explanations) update immediately on language
  // switch, without re-fetching anything from the API.
  if (window.__lastRenderedReports) {
    renderReports(window.__lastRenderedReports);
  }
}

// ---------------------------------------------------------------------
// Rendering
// ---------------------------------------------------------------------
function verdictBadge(lang, verdictCode) {
  const label = TRANSLATIONS[lang].verdictLabels[verdictCode] || verdictCode;
  const span = document.createElement("span");
  span.className = `verdict-badge verdict-${verdictCode}`;
  span.textContent = `${label} (${verdictCode})`;
  return span;
}

function caseRowLabel(lang, caseName) {
  const map = {
    "restricted:tools_call": "restrictedCallLabel",
    "restricted:tools_list": "restrictedListLabel",
    "authorized:tools_call": "authorizedCallLabel",
    "authorized:tools_list": "authorizedListLabel",
  };
  return t(lang, map[caseName]) || caseName;
}

function evidenceLine(lang, c) {
  const dict = TRANSLATIONS[lang];
  if (c.case.endsWith(":tools_call")) {
    // evidence.handler_reached solo está presente cuando tools_call
    // tuvo éxito de transporte/sesión (ver verifier.py:
    // evaluate_tools_call). Un bloqueo de autorización limpio
    // (reason: "clean_authz_block", verdict BLOQUEO_ESPERADO o
    // ACCESO_LEGITIMO_FALLIDO) o un fallo de transporte/autenticación
    // (verdict INDETERMINADO) no incluyen ese campo en absoluto, así
    // que hay que mirar también "reason" antes de caer en "unknown".
    if (c.evidence.handler_reached === true) return dict.handlerReachedYes;
    if (c.evidence.handler_reached === false) return dict.handlerReachedNo;
    if (c.evidence.reason === "clean_authz_block") return dict.handlerReachedNo;
    return dict.handlerReachedUnknown;
  }
  if (c.case.endsWith(":tools_list")) {
    if (c.evidence.listed_tagged_tool === true) return dict.toolListedYes;
    if (c.evidence.listed_tagged_tool === false) return dict.toolListedNo;
  }
  return "";
}

function renderReportTable(lang, titleKey, explanationKey, report) {
  const dict = TRANSLATIONS[lang];
  const section = document.createElement("section");
  section.className = "report";

  const h2 = document.createElement("h2");
  h2.textContent = dict[titleKey];
  section.appendChild(h2);

  const p = document.createElement("p");
  p.className = "explanation";
  p.textContent = dict[explanationKey];
  section.appendChild(p);

  const table = document.createElement("table");
  const tbody = document.createElement("tbody");
  for (const c of orderedCases(report)) {
    const tr = document.createElement("tr");

    const tdCase = document.createElement("td");
    tdCase.textContent = caseRowLabel(lang, c.case);
    tr.appendChild(tdCase);

    const tdVerdict = document.createElement("td");
    tdVerdict.appendChild(verdictBadge(lang, c.verdict));
    tr.appendChild(tdVerdict);

    const tdEvidence = document.createElement("td");
    tdEvidence.textContent = evidenceLine(lang, c);
    tr.appendChild(tdEvidence);

    tbody.appendChild(tr);
  }
  table.appendChild(tbody);
  section.appendChild(table);

  const meta = document.createElement("p");
  meta.className = "meta";
  const metaParts = [];
  if (report.run_id) metaParts.push(`${dict.runIdLabel}: ${report.run_id}`);
  if (report.source) metaParts.push(`${dict.sourceLabel}: ${report.source}`);
  metaParts.push(`${dict.generatedAtLabel}: ${report.generated_at}`);
  meta.textContent = metaParts.join(" · ");
  section.appendChild(meta);

  return section;
}

function renderReports({ lab349, live3410 }) {
  window.__lastRenderedReports = { lab349, live3410 };
  const lang = currentLang();
  const results = document.getElementById("results");
  results.innerHTML = "";

  if (lab349) {
    results.appendChild(
      renderReportTable(lang, "historicalTitle", "historicalExplanation", lab349)
    );
  }
  if (live3410) {
    results.appendChild(
      renderReportTable(lang, "liveTitle", "liveExplanation", live3410)
    );
  }
}

// ---------------------------------------------------------------------
// API calls — paths and JSON shape are untouched regardless of UI
// language: /demo/run (POST), /demo/report/{run_id} (GET).
//
// Base URL detection: when this page is served BY the same API Gateway
// stage (the deployed case), window.location already IS the API's
// origin + stage prefix (e.g. https://<id>.execute-api.<region>.
// amazonaws.com/demo/), because index.html is returned by
// GET /<stage>/ on that very stage. So the API base is simply
// window.location.origin + the first path segment (the stage name),
// with no separate configuration step and no field for the visitor to
// fill in. This works for ANY stage name, not just "demo": the stage
// segment is read from the URL that loaded the page, never hardcoded.
//
// Local/manual testing fallback: if this file is opened directly as a
// local file (file:// or a bare static server with no API behind it),
// there is no stage segment to read from the URL, so apiBaseUrl()
// falls back to an explicit override via a query string parameter,
// documented in ui/README.md: index.html?api=https://.../demo
// ---------------------------------------------------------------------
function detectedStagePrefix() {
  // window.location.pathname when this file is served as GET /<stage>/
  // is "/<stage>/". The first non-empty segment is the stage name.
  const segments = window.location.pathname.split("/").filter(Boolean);
  return segments.length > 0 ? `/${segments[0]}` : "";
}

function apiBaseUrl() {
  const params = new URLSearchParams(window.location.search);
  const override = params.get("api");
  if (override) return override.trim().replace(/\/+$/, "");

  if (window.location.protocol === "file:") {
    // Opened as a local file with no override query param: there is
    // no origin/stage to infer. Returning "" makes the caller show
    // the "missing API configuration" error instead of silently
    // calling a meaningless relative path.
    return "";
  }

  return `${window.location.origin}${detectedStagePrefix()}`;
}

function setStatus(message, isError) {
  const el = document.getElementById("status");
  el.textContent = message;
  el.className = isError ? "status error" : "status";
}

async function runLiveCheck() {
  const lang = currentLang();
  const base = apiBaseUrl();
  if (!base) {
    setStatus(`${t(lang, "errorPrefix")}: ${t(lang, "errorNoApiDetected")}`, true);
    return;
  }
  setStatus(t(lang, "runningLabel"), false);
  try {
    const resp = await fetch(`${base}/demo/run`, { method: "POST" });
    if (!resp.ok) {
      setStatus(`${t(lang, "errorPrefix")}: ${t(lang, "errorNetwork")} (HTTP ${resp.status})`, true);
      return;
    }
    const body = await resp.json();
    setStatus("", false);
    renderReports({ lab349: LAB_EVIDENCE_349, live3410: body.report });
    document.getElementById("recover-run-id").value = body.run_id;
  } catch (err) {
    setStatus(`${t(lang, "errorPrefix")}: ${t(lang, "errorNetwork")} (${err})`, true);
  }
}

async function recoverReport() {
  const lang = currentLang();
  const base = apiBaseUrl();
  const runId = document.getElementById("recover-run-id").value.trim();
  if (!runId) {
    setStatus(`${t(lang, "errorPrefix")}: ${t(lang, "errorMissingRunId")}`, true);
    return;
  }
  if (!base) {
    setStatus(`${t(lang, "errorPrefix")}: ${t(lang, "errorNoApiDetected")}`, true);
    return;
  }
  setStatus(t(lang, "runningLabel"), false);
  try {
    const resp = await fetch(`${base}/demo/report/${encodeURIComponent(runId)}`, { method: "GET" });
    if (resp.status === 404) {
      setStatus(`${t(lang, "errorPrefix")}: ${t(lang, "errorNotFound")}`, true);
      return;
    }
    if (!resp.ok) {
      setStatus(`${t(lang, "errorPrefix")}: ${t(lang, "errorNetwork")} (HTTP ${resp.status})`, true);
      return;
    }
    const body = await resp.json();
    setStatus("", false);
    const recovered = body.reports && body.reports[0];
    renderReports({ lab349: LAB_EVIDENCE_349, live3410: recovered });
  } catch (err) {
    setStatus(`${t(lang, "errorPrefix")}: ${t(lang, "errorNetwork")} (${err})`, true);
  }
}

// ---------------------------------------------------------------------
// Wiring
// ---------------------------------------------------------------------
document.addEventListener("DOMContentLoaded", () => {
  const langSelect = document.getElementById("lang-select");
  langSelect.value = currentLang();
  setLang(currentLang());

  langSelect.addEventListener("change", (e) => setLang(e.target.value));
  document.getElementById("run-button").addEventListener("click", runLiveCheck);
  document.getElementById("recover-button").addEventListener("click", recoverReport);

  // Show the 3.4.9 lab evidence immediately on load, even before any
  // live check has run, so the contrast panel is never empty.
  renderReports({ lab349: LAB_EVIDENCE_349, live3410: null });
});
