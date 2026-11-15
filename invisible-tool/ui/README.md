# Invisible Tool demo UI

Minimal static page (`index.html`, `app.js`, `translations.js`), no
build step. In the deployed stack it is served by the same API
Gateway stage as the demo API (`GET /`, `GET /ui/app.js`,
`GET /ui/translations.js`, handled by `ReportReaderFunction`; see
`sam_app/template.yaml` and `sam_app/report_reader/app.py`).

## English / Español

The language selector defaults to English, translates all display
text (buttons, loading/error states, verdict labels, the 3.4.9-vs-3.4.10
explanation), and persists the choice in the browser's `localStorage`
across reloads. It never changes verdict codes, JSON field names, or
API paths — see the top of `translations.js` for why that separation
matters for the existing automated tests.

## How the API base URL is detected

When this page is opened through the deployed API Gateway URL (e.g.
`https://<api-id>.execute-api.<region>.amazonaws.com/demo/`), the page
itself was served by that same stage, so `app.js` reads the API base
URL directly from `window.location`: origin + first path segment
(the stage name, read from the URL — never hardcoded to `demo` or any
other literal). No field to paste a URL into, no extra step for the
visitor.

## Testing locally, without a deployed API Gateway

There is no stage prefix to read from `window.location` when this page
is opened as a bare local file or from a plain static file server, so
`app.js` falls back to an explicit override via a query string
parameter:

```
# Open directly as a file (works in most browsers for a page with no
# other local resources besides its own JS, since app.js/translations.js
# are same-folder relative script tags):
open ui/index.html

# Or serve the folder with any static file server, e.g.:
cd invisible-tool/ui
python3 -m http.server 8080
# then open http://127.0.0.1:8080/
```

Either way, point the page at a running API by adding `?api=...` to
the address, for example:

```
http://127.0.0.1:8080/index.html?api=https://your-api-id.execute-api.your-region.amazonaws.com/your-stage
```

or, when testing against the local handlers directly (see
`sam_app/test_handlers_local.py` for how to run them against DynamoDB
Local), point `?api=` at whatever local HTTP wrapper you use to expose
them, as long as it serves the same two routes
(`POST /demo/run`, `GET /demo/report/{run_id}`) with the same JSON
shape.

If the page cannot detect an API base URL (no stage segment in the
current address, and no `?api=` override), it shows an explicit error
message in the selected language instead of silently calling a
meaningless relative path.

## Note on CORS

The deployed stack does **not** enable CORS on API Gateway: the UI is
served by the same origin it calls, so no cross-origin request is
ever made in the deployed flow. If you test the UI locally via a
separate static file server (as shown above) against an API deployed
with CORS disabled, cross-origin `fetch()` calls from that local
server to the deployed API will be blocked by the browser. For that
specific local-testing scenario, either reuse `sam_app/test_handlers_local.py`
to call the handlers directly (no HTTP, no CORS involved), or
temporarily re-add a `Cors` block to `DemoApi` in `template.yaml` for a
throwaway local deployment — never for the published demo stack.
