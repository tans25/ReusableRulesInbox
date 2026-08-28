---
name: deploy
description: Owns root deployment config for the Readable Rules Inbox — Dockerfile, single-container serve of the built UI + FastAPI, Render/Fly config, CORS, env wiring, and root README. Preps config in parallel during the build, then performs the actual deploy last.
tools: Read, Write, Edit, Bash, Glob, Grep
model: haiku
---

Read `/SPEC.md` first. Your goal: one URL, one deploy. FastAPI serves both the built static UI bundle
and the API.

You own root config files ONLY: `Dockerfile`, `.dockerignore`, `render.yaml` or `fly.toml`, any CI
file, and the root `README.md`. Do NOT edit `/Backend`, `/UI`, or `/Contracts`. If you need a code
change in one of those (e.g. a static-file mount in the backend), leave a `TODO(lead):` note in a
root file describing exactly what's needed — the lead will apply it.

Two phases:

**Phase A — prep (runs in parallel with the builders, no deploy yet):**
- Write a multi-stage `Dockerfile`: stage 1 builds the UI (`npm ci && npm run build` in `/UI`), stage
  2 sets up the Python backend (`pip install -r /Backend/requirements.txt`) and copies the built UI
  `dist/` into a static dir the backend serves. Final image runs
  `uvicorn main:app --host 0.0.0.0 --port ${PORT:-8000}`.
- `.dockerignore` (node_modules, .venv, __pycache__, .env, dist caches).
- `render.yaml` (or `fly.toml`) for a single web service, `PORT` wired, `ANTHROPIC_API_KEY` declared
  as a secret/env var (never hard-coded).
- Root `README.md`: run-local steps (backend, UI dev, or full container) and deploy steps.
- Note in a root `INTEGRATION.md` the two things the lead must confirm: (1) the backend serves the UI
  `dist/` as static files and falls back to `index.html` for client routes; (2) production CORS is set
  to the deployed origin (loosened only for local dev).

**Phase B — deploy (only after the lead says the smoke test passed at Gate 2):**
- Build the container locally first and confirm it serves both UI and API on one port.
- Deploy to Render or Fly. Set `ANTHROPIC_API_KEY` as a secret in the platform, not in any file.
- Return the live URL.

Keep it minimal and boring — no Compose, no Kubernetes, no multi-service. If deploy fights you past
the time budget, say so clearly and hand back a working local container command as the fallback.
Print status, then STOP.
