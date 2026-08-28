# SPEC.md — Readable Rules Inbox

**Every agent reads this file before doing anything. It is the single source of truth. Do not contradict it; if something here is ambiguous, leave a `TODO(lead):` note rather than guessing.**

## The thesis (why this exists)

Automated triage is a black box, so people stop trusting it and go back to reading everything.
This app makes triage a **glass box**: the user writes routing rules in plain English, the app
compiles them into visible, editable logic, runs them over a sample inbox, and shows *why* each
message landed where it did. The whole product is trust: see the mistake → understand it → fix it
in plain English → re-run.

The demo is won or lost on one moment: a misrouted message, a one-sentence English edit, a re-run
where **only that message moves** and everything else stays put. Build toward that moment.

---

## Architecture (the core bet)

The LLM compiles rules **at authoring time, not at classification time.** Calling a model per
message would just rebuild the black box with latency.

```
NL rule --> [LLM compiler] --> Rule IR (JSON) --> [deterministic executor] --> routed inbox + trace
                                     ^
                              rendered as readable
                              pseudocode, editable
```

The **Rule IR** is the product. It is what the user inspects, what the executor runs, and what the
diff shows on edit.

---

## Rule IR (canonical schema)

`/Contracts` owns the authoritative version of this in three forms: Pydantic (`ir.py`), JSON Schema
(`rule_ir.schema.json`), and TypeScript (`ir.ts`). All three MUST stay in sync. This block is the
reference they implement.

```jsonc
// A Rule
{
  "id": "r_billing",
  "name": "Billing questions -> Finance",
  "source_nl": "Messages from clients about invoices or charges go to Finance.", // original English, kept for the editable view
  "priority": 10,                 // higher wins on conflict
  "when": <Condition>,            // a condition tree, see below
  "then": [ <Action>, ... ]
}
```

### Condition (recursive tree)

A `Condition` is exactly one of:

```jsonc
{ "all": [ <Condition>, ... ] }   // AND
{ "any": [ <Condition>, ... ] }   // OR
{ "not": <Condition> }            // NOT
{ "op": <PredicateOp>, "value": <any> }   // leaf predicate
```

### PredicateOp (CLOSED enum — the compiler may emit nothing outside this list)

Deterministic (free, instant, fully auditable):
- `sender_domain_in`   value: `string[]`   — sender's email domain is in the list
- `sender_is`          value: `string`     — exact sender email match
- `subject_matches`    value: `string`     — regex against subject (Python `re`, `(?i)` allowed)
- `body_matches`       value: `string`     — regex against body
- `has_attachment`     value: `boolean`
- `recipient_count_gte` value: `int`
- `thread_length_gte`  value: `int`

Semantic (best-effort, ONE narrow yes/no LLM call, cached):
- `semantic`           value: `string`     — natural-language yes/no question about the message,
                                             e.g. "asks about a refund or payment"

### Action (closed enum)

```jsonc
{ "action": "route",    "to": "<folder>" }   // exactly one route action expected per rule
{ "action": "label",    "value": "<label>" }
{ "action": "priority", "value": <int> }     // optional, overrides rule.priority for the match
```

Folders in the demo: `Finance`, `Retention`, `Support`, `Sales`, `Spam`, `Inbox` (default when no rule matches).

---

## Trace object (this is the trust story — do not skimp)

`/run` returns, per message, a full evaluation trace. The UI renders it as a collapsible tree with
green/red predicate nodes.

```jsonc
{
  "message_id": "m_017",
  "final_route": "Finance",
  "matched_rule_id": "r_billing",     // null if nothing matched -> Inbox
  "also_matched": ["r_support"],      // other rules that matched but lost on priority
  "considered": [
    {
      "rule_id": "r_billing",
      "rule_name": "Billing questions -> Finance",
      "priority": 10,
      "matched": true,
      "predicates": [
        {
          "op": "subject_matches",
          "value": "(?i)invoice|refund|charge",
          "result": true,
          "evidence": "refund"        // matched substring, or the sentence the semantic call keyed on
        }
      ]
    }
    // ...every rule considered, in priority order
  ]
}
```

Conflict resolution: **strict priority.** Highest `priority` wins; ties broken by rule order.
Winner shown as `matched_rule_id`, losers listed in `also_matched`. Nothing cleverer than this.

---

## Semantic predicate execution + cache

- One narrow yes/no Anthropic call per `(message, semantic-predicate-text)` pair.
- Cache the result keyed on `sha256(message_id + "::" + predicate_text)`. On re-run after a rule
  edit, only the changed predicate is re-evaluated; everything else is a cache hit and effectively
  instant. **This is what makes "re-run only moves one message" true — implement the cache.**
- If the LLM call fails or times out (>4s), the predicate resolves `false` with
  `evidence: "semantic unavailable"`. The deterministic path must never depend on it.

---

## API contract (backend implements, UI consumes — do not deviate from these shapes)

Base URL comes from `VITE_API_BASE` on the UI side.

- `GET  /inbox` -> `Message[]`
- `GET  /rules` -> `Rule[]`
- `PUT  /rules/{id}` body `{ source_nl: string }` -> recompiles that rule, returns `{ rule: Rule, diff: RuleDiff }`
- `POST /compile` body `{ source_nl: string }` -> `{ rule: Rule }` (compile a new rule; validate against schema, retry ONCE on validation failure with the error appended to the prompt)
- `POST /run` body `{ rules?: Rule[] }` (omit to use stored rules) -> `{ results: Trace[] }`

`Message` shape:
```jsonc
{ "id": "m_001", "from": "amir@acme.com", "from_domain": "acme.com",
  "to": ["support@us.co"], "subject": "...", "body": "...",
  "has_attachment": false, "thread_length": 1 }
```

`RuleDiff` (for the edit view — the payoff moment):
```jsonc
{ "added": ["not: subject_matches (?i)cancel|churn"], "removed": [], "unchanged": [ ... ] }
```
Keep the diff a simple list of human-readable predicate lines added/removed/unchanged. It does not
need to be a real AST diff — a flattened predicate comparison is enough and reads better on stage.

---

## Sample data (`/Contracts` produces this)

`sample_inbox.json`: **40 messages**, realistic, across all folders. Include obvious cases and a few
genuinely ambiguous ones. MUST include the planted misroute (see demo).

`seed_rules.json`: **3 hand-written rules** as IR (with `source_nl`), covering Finance, Support, and
Sales, so the app has content before the user writes anything. One of them is the flawed billing
rule from the demo.

---

## The planted demo (build the data so this works)

1. Message `m_017`: from a client, subject "Cancelling — refund for this month?", body asks to
   cancel the subscription and get a refund.
2. `seed_rules.json` billing rule routes anything matching `(?i)invoice|refund|charge` to **Finance**.
   So `m_017` misroutes to Finance. It should go to **Retention**.
3. Demo flow:
   - Click `m_017`. Trace tree shows `subject_matches: refund -> TRUE` in red context. The failure is
     legible, not mysterious.
   - Edit the rule's English: "...unless the message also mentions cancelling or churning, in which
     case route to Retention."
   - Recompile. Show the IR diff — one added `not`/branch, nothing else moved.
   - Re-run. `m_017` hops to Retention. The other 39 messages stay exactly where they were, and the
     presenter says so out loud.

---

## Tech stack

- **/Contracts**: Pydantic v2 (`ir.py`), JSON Schema, TypeScript types (`ir.ts`), sample data JSON.
- **/Backend**: FastAPI + Pydantic v2, `anthropic` Python SDK for `/compile` and semantic predicates,
  storage = flat JSON files or SQLite via SQLModel (no migrations, no Docker Compose). Pure-function
  executor in `engine.py` with zero I/O and zero network so it is unit-testable with a fixture rule +
  fixture message and no mocks.
- **/UI**: React + Vite + TypeScript, Tailwind, shadcn/ui. Three panes: inbox list (grouped by
  destination folder) / selected message + trace tree / rules panel (English on the left, rendered
  pseudocode on the right, edit + recompile + diff).
- **Deploy** (root): single container — FastAPI serves the built static UI bundle. Render or Fly.io.
  One URL, one deploy.

Model for LLM calls in the backend: use `claude-sonnet-5` for the compiler (structured output),
`claude-haiku-4-5-20251001` for semantic yes/no predicates (cheap, narrow). Read the key from
`ANTHROPIC_API_KEY`.

---

## Directory ownership (HARD RULE — prevents agents colliding)

- `/Contracts` — schema agent only. **Frozen after Gate 1.** Everyone else treats it READ-ONLY.
- `/Backend`   — backend agent only.
- `/UI`        — UI agent only.
- root config (Dockerfile, render.yaml / fly.toml, CI, .dockerignore) — deploy agent only.

No agent edits another agent's directory or `/Contracts`. If you need a change in a directory you
don't own, write a `TODO(lead):` note in your own area and stop.

---

## Definition of done (per area)

**Contracts**: `ir.py`, `rule_ir.schema.json`, `ir.ts` all in sync; `sample_inbox.json` (40 msgs incl.
m_017); `seed_rules.json` (3 rules incl. flawed billing rule). A one-paragraph `README.md` in
`/Contracts` describing the IR.

**Backend**: all 5 endpoints live; `engine.py` is pure and has at least 2 passing unit tests
(deterministic match + priority conflict); `/compile` validates against the schema and retries once;
semantic cache implemented; `uvicorn` starts clean; a `.env.example` with `ANTHROPIC_API_KEY=`.

**UI**: three panes render against a running backend; trace tree with green/red nodes; rule edit ->
recompile -> visible diff -> re-run works; reads `VITE_API_BASE`.

**Deploy**: single command / single container builds and serves UI + API on one URL; env var wired;
`README.md` at root with run-local and deploy steps.
