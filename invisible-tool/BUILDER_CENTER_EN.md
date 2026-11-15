# Invisible Tool — making a hidden authorization gap visible, then proving the fix

**Video:** [PLACEHOLDER — add the video link here before publishing]

## The problem

MCP servers built with FastMCP can apply an authorization check to a
tool, then transform that tool (renaming it, re-tagging it, changing
its metadata) before exposing it. A real, maintainer-accepted security
advisory —
[GHSA-7xgj-8392-5q4r](https://github.com/advisories/GHSA-7xgj-8392-5q4r)
— reports that FastMCP's `tools/list` correctly re-checked
authorization against the *final, transformed* tool, but the direct
`tools/call` path did not: it resolved the transformed tool and ran it
without re-applying that same check. A caller who already knows (or
guesses) the tool's name could invoke it directly, bypassing the
authorization decision that `tools/list` had already made for them —
even though the tool never showed up in their listing.

Affected: FastMCP 3.0.0–3.4.9 (and 4.0.0–4.1.1). Fixed in FastMCP
3.4.10 (and 4.1.2). This gap is easy to miss because the symptom looks
correct from the outside: the tool is invisible. Only testing the
*execution* path, not just the *listing* path, reveals it.

## The solution: Invisible Tool

Invisible Tool reproduces this exact advisory with two synthetic
identities — `authorized` (has the required scope) and `restricted`
(does not) — against one harmless tool that returns a fixed marker
string instead of any real secret. For each identity, it runs both
`tools/list` and `tools/call` and classifies what happened into one of
five verdicts, distinguishing:

- **expected access** (authorized identity reaches the handler),
- **expected block** (restricted identity is blocked),
- **improper access** (restricted identity reaches the handler
  anyway — the vulnerability),
- and, critically, **indeterminate** — a session or transport failure
  (e.g. an HTTP 401, a dropped connection) is never confused with a
  clean authorization block. Without that distinction, a broken
  connection could be mistaken for a working security control.

### Lab evidence vs. live check — two different kinds of proof

- **FastMCP 3.4.9 · lab evidence**: captured once, locally, running
  the actual affected FastMCP release in an isolated environment. This
  is historical proof that the vulnerability is real and reproducible
  exactly as the advisory describes it — the restricted identity's
  direct call reaches the handler and returns the marker, even though
  the tool was hidden from its listing.
- **FastMCP 3.4.10 · live check**: run fresh, on demand, inside the
  deployed AWS Lambda function, every time someone clicks "Run live
  check" in the demo. This is not a static screenshot — it is the
  fixed FastMCP version actually executing right now, in a real AWS
  account, proving the restricted identity stays blocked under the
  same conditions that broke on 3.4.9.

Keeping these two separate matters: the lab evidence proves the bug
existed; the live check proves the fix holds, today, in production
infrastructure — not just in a local test run captured once and never
re-verified.

## How the services connect

```
Browser (bilingual demo UI)
   │ POST /demo/run   GET /demo/report/{run_id}
   ▼
API Gateway  →  Lambda (runs FastMCP 3.4.10 embedded, both identities)
                   │ writes the verified report with a run_id
                   ▼
              DynamoDB table
                   ▲
Lambda (reads a report back by run_id)  ←───────────┘
```

- **API Gateway** exposes two routes: triggering a fresh live check,
  and recovering any past report by its ID.
- **Lambda** runs the actual FastMCP 3.4.10 server on a loopback port
  inside its own process for the duration of one invocation — no
  long-lived server, no exposed port beyond the function's own
  execution environment.
- **DynamoDB** stores every verified report under its own identifier,
  so a report generated once can be fetched again later by anyone with
  the ID, with its verdicts intact.
- IAM policies are scoped to the single table's exact ARN, with only
  the actions each function needs (write-only for the runner, read-only
  for the reader).

This was validated end to end against DynamoDB Local, against the
official AWS Emulator, and, finally, against a real deployment on AWS
using SAM — generating and recovering a live report in an actual AWS
account, not just in a local emulator.
