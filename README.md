# Rusable Rules Inbox

Automated triage is usually a black box, so people stop trusting it. This makes it a
**glass box**: write triage rules in plain English, see them compiled into logic you can
read and edit, run them over a sample inbox, and inspect *why* every message landed where
it did. Fix a misroute by editing one English sentence and re-running.

One process serves both the API and the UI — no separate frontend build, no CORS.

## Stack
- **Backend + server:** FastAPI (serves the API and the static UI on one origin)
- **Executor:** a pure, deterministic engine (`app/engine.py`) with full evaluation traces
- **LLM (rule compiling + semantic predicates):** Mistral
- **Deploy:** single container → Google Cloud Run

## Run locally

```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt

# The app's runtime LLM key — needed only to COMPILE new rules / semantic predicates.
# The seeded demo (including the misroute) runs fine without it.
cp .env.example .env        # then paste your key into .env:
# MISTRAL_API_KEY=...

uvicorn app.main:app --reload --port 8080
# open http://localhost:8080
```

Run the engine tests:
```bash
pip install pytest && python -m pytest -q
```

## The demo (2 minutes)

1. Click message **m_017** ("Cancelling — refund for this month?"). Its trace shows the
   billing rule matched on `refund` → routed to **Finance**. The mistake is legible.
2. In the right panel, in **Add a rule**, type:
   *"If someone wants to cancel or churn, send it to Retention."* → **Compile rule**.
   The compiled logic appears as readable pseudocode.
3. The inbox re-runs automatically: **m_017 moves to Retention**, along with the other
   genuine cancellation messages — and the ~37 other messages stay exactly where they were.
4. (Alt) Instead of adding a rule, edit the **billing rule's** English to exclude
   cancellations and hit **Recompile & show diff** — the diff shows the one predicate that
   changed, nothing else.

If `MISTRAL_API_KEY` isn't set, steps 2/4 return a friendly error but everything else —
inbox, traces, priority resolution, the misroute — still works.

## Deploy to Google Cloud Run

```bash
gcloud auth login
gcloud config set project YOUR_PROJECT_ID

# store the key as a Cloud Run secret (don't bake it into the image)
echo -n "YOUR_MISTRAL_KEY" | gcloud secrets create mistral-key --data-file=- || \
echo -n "YOUR_MISTRAL_KEY" | gcloud secrets versions add mistral-key --data-file=-

gcloud run deploy readable-rules-inbox \
  --source . \
  --region us-central1 \
  --allow-unauthenticated \
  --set-secrets MISTRAL_API_KEY=mistral-key:latest
```

Cloud Run builds the Dockerfile, injects `PORT`, and returns one public URL. Scales to zero,
so your credit mostly covers build + demo traffic.

## Layout
```
app/models.py     rule IR, message, trace types
app/engine.py     pure executor + trace + strict-priority conflict resolution
app/compiler.py   English -> IR via Mistral structured output
app/semantic.py   cached yes/no semantic predicates
app/store.py      loads sample inbox + seed rules (in-memory)
app/main.py       FastAPI endpoints + serves the UI
static/index.html self-contained three-pane frontend
data/             sample_inbox.json (40 msgs incl. m_017), seed_rules.json
tests/            engine unit tests
```

## The IR (flat, on purpose)
A rule is a list of predicates combined with `all`/`any`, each optionally negated — not a
nested boolean tree. That's more reliable for LLM structured output and reads better on
screen, which is the whole point. Conflicts resolve by strict priority (highest wins, ties
by order); the winner and any also-matched rules are shown in every trace.
