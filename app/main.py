"""FastAPI app. Serves the API and the self-contained UI on a single origin, so there
is no CORS and no separate frontend build to deploy."""
from __future__ import annotations

from pathlib import Path

from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from .compiler import CompileError, compile_rule
from .engine import diff_rules, run
from .models import CompileRequest, Rule, Trace
from .semantic import make_semantic_fn
from .store import store

load_dotenv()

app = FastAPI(title="Readable Rules Inbox")
_STATIC = Path(__file__).resolve().parent.parent / "static"
_semantic_fn = make_semantic_fn()


class RunRequest(BaseModel):
    rules: list[Rule] | None = None


class EditRequest(BaseModel):
    source_nl: str


@app.get("/api/inbox")
def get_inbox():
    return store.messages


@app.get("/api/rules")
def get_rules():
    return store.list_rules()


@app.post("/api/compile")
def compile_new(req: CompileRequest):
    try:
        rule = compile_rule(req.source_nl, rule_id=store.next_id(), priority=15)
    except CompileError as e:
        raise HTTPException(status_code=422, detail=str(e))
    store.upsert_rule(rule)
    return {"rule": rule}


@app.put("/api/rules/{rule_id}")
def edit_rule(rule_id: str, req: EditRequest):
    old = store.get_rule(rule_id)
    if old is None:
        raise HTTPException(status_code=404, detail=f"No rule {rule_id}")
    try:
        new = compile_rule(req.source_nl, rule_id=rule_id, priority=old.priority)
    except CompileError as e:
        raise HTTPException(status_code=422, detail=str(e))
    store.upsert_rule(new)
    return {"rule": new, "diff": diff_rules(old, new)}


@app.post("/api/run")
def run_rules(req: RunRequest):
    rules = req.rules if req.rules is not None else store.list_rules()
    traces: list[Trace] = run(rules, store.messages, _semantic_fn)
    return {"results": traces}


# ---- serve the UI (mounted last so /api/* wins) ----
if _STATIC.exists():
    app.mount("/static", StaticFiles(directory=_STATIC), name="static")


@app.get("/")
def index():
    return FileResponse(_STATIC / "index.html")
