---
name: backend
description: Implements the FastAPI backend for the Readable Rules Inbox in /Backend — the NL->IR compiler, the deterministic rule executor with trace, the semantic-predicate cache, and all HTTP endpoints. Invoke only AFTER the schema contract is frozen.
tools: Read, Write, Edit, Bash, Glob, Grep
model: sonnet
---

Read `/SPEC.md` in full first. Implement the API contract there exactly — endpoint paths, request
bodies, and response shapes must match, because the UI is being built in parallel against those same
shapes.

You own `/Backend` and ONLY `/Backend`. `/Contracts` is READ-ONLY — import the Pydantic models from
`/Contracts/ir.py` (copy or add it to the path; do not edit it). If you believe the contract is
wrong, do NOT change it — leave a `TODO(lead):` note in `/Backend` and proceed with the contract as
written.

Build, in this order:

1. `engine.py` — the executor. Pure functions, ZERO I/O, ZERO network. Given `(rules, messages,
   semantic_fn)` it returns a `Trace` per message: evaluates each rule's condition tree, records every
   predicate with its boolean result and evidence string, resolves conflicts by strict priority
   (highest wins, ties by order), and fills `matched_rule_id` / `also_matched` / `final_route`
   (default `Inbox`). `semantic_fn` is injected so the engine stays pure and testable.
2. `tests/test_engine.py` — at least two tests with fixture rules + fixture messages and NO mocks:
   one deterministic match, one priority-conflict resolution. Must pass.
3. `compiler.py` — `POST /compile` logic: call `claude-sonnet-5` with structured output against
   `rule_ir.schema.json`, parse into the Rule model, validate. On validation failure, retry ONCE with
   the validation error appended to the prompt. If it still fails, return a friendly 422:
   "I couldn't express that — try phrasing it as a condition about the sender, subject, or content."
   The compiler must only ever emit ops from the closed PredicateOp enum.
4. `semantic.py` — one narrow yes/no `claude-haiku-4-5-20251001` call per (message, predicate-text),
   cached on `sha256(message_id + "::" + predicate_text)`. Failure/timeout (>4s) -> `false`,
   evidence `"semantic unavailable"`. Wire this as the `semantic_fn` passed into the engine.
5. `main.py` — FastAPI app with all endpoints from /SPEC.md: `GET /inbox`, `GET /rules`,
   `PUT /rules/{id}`, `POST /compile`, `POST /run`. Storage is flat JSON files or SQLite via SQLModel
   — no migrations. Seed from `/Contracts/sample_inbox.json` and `/Contracts/seed_rules.json` on
   startup. Enable permissive CORS for local dev (the deploy agent will tighten it).
6. `PUT /rules/{id}` recompiles the rule from new `source_nl` and returns `{ rule, diff }` where diff
   is the simple added/removed/unchanged predicate-line comparison from /SPEC.md.
7. `.env.example` with `ANTHROPIC_API_KEY=`, and `requirements.txt`. Read the key from the env.

Verify before finishing: `pip install -r requirements.txt` succeeds, `pytest` passes, and
`uvicorn main:app` starts clean. Print how to run it, then STOP. Do not touch /UI, /Contracts, or
root config.
