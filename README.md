# Invisible Tool

Invisible Tool checks whether a FastMCP server actually enforces its
tool-authorization policy on the `tools/call` path, not just on
`tools/list`. It targets a real, maintainer-accepted advisory —
[GHSA-7xgj-8392-5q4r](https://github.com/advisories/GHSA-7xgj-8392-5q4r)
("Post-transform component authorization is skipped on direct calls")
— and reproduces the exact contrast it describes using two synthetic
identities and one harmless tool.

## What it checks

A FastMCP server can hide a tool from `tools/list` for an unauthorized
caller while still executing it if that caller invokes `tools/call`
directly and already knows (or guesses) the tool's name. The advisory
reports this gap in FastMCP 3.0.0–3.4.9 (reproduced on 3.4.9) and fixed
in 3.4.10.

Invisible Tool sets up one FastMCP server with:

- a single tool, `tagged_tool`, tagged `{"public"}` with an
  authorization policy (`restrict_tag("admin", scopes=["admin"])`),
- a server-side `ToolTransform` that adds the `{"admin"}` tag to the
  final, transformed version of that tool,
- two synthetic token identities: `authorized` (has the `admin`
  scope) and `restricted` (has no scopes).

For both identities, it runs `tools/list` and `tools/call` and
classifies the outcome as one of five verdicts:

| Verdict | Meaning |
|---|---|
| `ACCESO_LEGITIMO` | Authorized identity correctly reached the handler / sees the tool listed. |
| `BLOQUEO_ESPERADO` | Restricted identity was correctly blocked. |
| `ACCESO_INDEBIDO` | Restricted identity reached the handler it should never reach — the vulnerability. |
| `ACCESO_LEGITIMO_FALLIDO` | Authorized identity was unexpectedly blocked (availability failure, not the vulnerability). |
| `INDETERMINADO` | Session or transport failure (e.g. HTTP 401, connection error) — no authorization conclusion can be drawn. |

## The contrast: 3.4.9 vs. 3.4.10

| Case | FastMCP 3.4.9 (affected) | FastMCP 3.4.10 (fixed) |
|---|---|---|
| `authorized:tools_list` | `ACCESO_LEGITIMO` | `ACCESO_LEGITIMO` |
| `authorized:tools_call` | `ACCESO_LEGITIMO` | `ACCESO_LEGITIMO` |
| `restricted:tools_list` | `BLOQUEO_ESPERADO` | `BLOQUEO_ESPERADO` |
| `restricted:tools_call` | **`ACCESO_INDEBIDO`** | **`BLOQUEO_ESPERADO`** |

`tools/list` already hides the tool from the restricted identity in
*both* versions. The only difference is `tools/call`: on 3.4.9 the
restricted identity's direct call still reaches the handler and gets
the tool's output; on 3.4.10 it is blocked with the same
"unknown tool" response the listing already implied.

Full methodology, raw evidence, and every verification phase
(verifier logic, DynamoDB Local, AWS Emulator, SAM deployment) are
documented in [`invisible-tool/RESULTS.md`](invisible-tool/RESULTS.md).

## Architecture

```
Browser (bilingual demo UI, served by the same API Gateway stage)
        │  GET /              GET /ui/app.js, /ui/translations.js
        │  POST /demo/run     GET /demo/report/{run_id}
        ▼
API Gateway (REST API, same origin for UI and API — no CORS needed)
        │
        ├── DemoRunnerFunction (Lambda)
        │     starts an embedded FastMCP 3.4.10 server on a loopback
        │     port inside the Lambda process, runs tools/list +
        │     tools/call for both identities, verifies the result,
        │     and writes a report with its own run_id
        │
        └── ReportReaderFunction (Lambda)
              reads a report back by run_id (DynamoDB Query), and
              also serves the static UI (GET /, /ui/app.js,
              /ui/translations.js) from the same origin as the API
        │
        ▼
DynamoDB table (report_id + target_version composite key)
```

- **API Gateway → Lambda → DynamoDB**, all defined in
  [`invisible-tool/sam_app/template.yaml`](invisible-tool/sam_app/template.yaml).
- The table is created by the template. Each Lambda gets only the
  DynamoDB actions it needs on that table's exact ARN:
  `DemoRunnerFunction` has `PutItem`/`GetItem`; `ReportReaderFunction`
  has `GetItem`/`Query`. Neither has `Scan`, `DeleteItem`, or access to
  any other table. Serving the static UI files requires no additional
  AWS permission.
- The UI is served from the same origin as the API (`ReportReaderFunction`
  is reused for this — it was already lightweight, with no `fastmcp`
  dependency), so the deployed stack has **no CORS configuration**: the
  browser never makes a cross-origin request. `app.js` detects the API
  base URL directly from `window.location` (origin + stage segment),
  so visitors never need to paste a URL. See `invisible-tool/ui/README.md`
  for how to test the UI locally without this API Gateway (where CORS,
  or a direct handler call, is needed instead).
- FastMCP **3.4.9** (the affected version) only runs in the local lab
  (`invisible-tool/run_matrix.sh`, `invisible-tool/server_lab.py`) as
  historical evidence — it is never packaged into Lambda. FastMCP
  **3.4.10** (the fixed version) is what runs live inside
  `DemoRunnerFunction` on every demo click. Why 3.4.9 isn't embedded in
  Lambda, and why an in-process transport cannot separate the two
  identities, is explained in `invisible-tool/RESULTS.md`.

## Repository layout

```
invisible-tool/
├── server_lab.py              # local FastMCP fixture (3.4.9 or 3.4.10, chosen at run time)
├── client_matrix.py           # runs tools/list + tools/call for both identities
├── verifier.py                # classifies raw results into the five verdicts above
├── dynamo_store.py            # persistence against DynamoDB Local / AWS Emulator
├── run_matrix.sh               # repeats the local lab for a given FastMCP version
├── run_integration.sh          # full integration against DynamoDB Local
├── run_integration_aws_emulator.sh  # full integration against the official AWS Emulator
├── test_verifier.py           # regression tests for the verifier
├── RESULTS.md                 # full methodology and observed results, phase by phase
├── sam_app/
│   ├── template.yaml           # API Gateway + Lambda + DynamoDB
│   ├── common/                 # shared code: embedded 3.4.10 fixture, verifier, report store
│   ├── demo_runner/             # Lambda: runs the live check, persists the report
│   ├── report_reader/           # Lambda: recovers a report by run_id
│   └── test_handlers_local.py   # smoke test for both handlers against DynamoDB Local
└── ui/
    ├── index.html               # minimal static demo page
    ├── app.js                    # fetches the API, renders both report tables
    ├── translations.js           # English/Spanish display strings
    └── README.md                 # how the API base URL is detected, and how to test locally
```

## Running the local lab (no AWS account needed)

```bash
cd invisible-tool
./run_matrix.sh 3.4.9    # affected version
./run_matrix.sh 3.4.10   # fixed version
uv run --with pytest -- python3 -m pytest test_verifier.py -v
```

## Running the integration against a local DynamoDB emulator

Two emulators are supported; both are documented end to end in
`RESULTS.md`:

```bash
# DynamoDB Local (amazon/dynamodb-local Docker image)
cd invisible-tool
./run_integration.sh

# Official AWS Emulator (https://docs.aws.amazon.com/emulator/)
./run_integration_aws_emulator.sh
```

## Deploying with AWS SAM

```bash
cd invisible-tool/sam_app
sam validate --lint
sam build

# Manual deployment — replace the placeholders with your own profile,
# region and stack name:
sam deploy \
  --profile <YOUR_AWS_PROFILE> \
  --region <YOUR_REGION> \
  --stack-name invisible-tool-demo \
  --resolve-s3 \
  --capabilities CAPABILITY_IAM \
  --no-confirm-changeset \
  --no-disable-rollback
```

The deployment prints both the API base URL and the UI page URL as
CloudFormation outputs (`ApiUrl`, `UiPageUrl`). Smoke-test the API
directly:

```bash
API_URL="<PASTE_THE_ApiUrl_OUTPUT_HERE>"

# Generate a new report (runs FastMCP 3.4.10 live, both identities)
curl -s -X POST "$API_URL/demo/run"

# Recover it by its run_id
curl -s -X GET "$API_URL/demo/report/<RUN_ID_FROM_THE_PREVIOUS_RESPONSE>"
```

## Using the demo UI

Open the `UiPageUrl` output directly in a browser
(`https://<api-id>.execute-api.<region>.amazonaws.com/<stage>/`) — no
build step, no local server, no URL to paste. The page is served by
the same API Gateway stage and detects its own API base URL from the
address that loaded it:

- **Run live check** — triggers `POST /demo/run`, shows the 3.4.9 lab
  evidence next to a fresh 3.4.10 live result. The restricted
  identity's `tools/call` result is shown first, with the authorized
  identity's result right below it as a control.
- **Recover report by ID** — triggers `GET /demo/report/{run_id}` for
  any previously generated `run_id`.
- The **English / Español** selector in the top right switches all
  display text and persists the choice in the browser's local storage
  across reloads. It never changes verdict codes, JSON field names, or
  API paths — those stay identical in both languages so the existing
  automated tests keep working regardless of which language a user
  picks.

To test the UI locally, without this API Gateway, see
[`invisible-tool/ui/README.md`](invisible-tool/ui/README.md).

## Security notes

- Both synthetic identities (`authorized`, `restricted`) use fixed,
  literal demo tokens defined in the project's own code
  (`server_lab.py` / `sam_app/common/fixture_3410.py`); they authenticate
  only against this project's own `StaticTokenVerifier` instance and
  carry no privilege outside of it.
- DynamoDB Local uses the fake credentials AWS's own documentation
  specifies for local testing (`fakeMyKeyId` / `fakeSecretAccessKey`);
  the AWS Emulator mode never uses fixed credentials — it loads the
  access key, secret key, and CA certificate the emulator itself
  generates on each run, and refuses to build a client if the local
  endpoint is missing or not loopback HTTPS.
- Lambda IAM policies are scoped to the exact table ARN with only the
  actions each function needs — see `invisible-tool/sam_app/template.yaml`.
