"""Semantic predicate evaluation: one narrow yes/no LLM call per (message, question),
cached so re-runs after a rule edit are effectively instant and only the changed
predicate costs a call.

Uses Mistral. If no MISTRAL_API_KEY is set, or the call fails/times out, the predicate
resolves False with evidence "semantic unavailable" — the deterministic path never
depends on the network.
"""
from __future__ import annotations

import hashlib
import os
from typing import Tuple

from .models import Message

_CACHE: dict[str, Tuple[bool, str]] = {}
_SEMANTIC_MODEL = "ministral-8b-latest"  # cheap + fast for a yes/no


def _key(message_id: str, question: str) -> str:
    return hashlib.sha256(f"{message_id}::{question}".encode()).hexdigest()


def make_semantic_fn():
    """Return a semantic_fn(message, question) -> (bool, evidence) closure."""
    api_key = os.environ.get("MISTRAL_API_KEY")
    client = None
    if api_key:
        try:
            from mistralai.client import Mistral
            client = Mistral(api_key=api_key)
        except Exception:
            client = None

    def semantic_fn(msg: Message, question: str) -> Tuple[bool, str]:
        k = _key(msg.id, question)
        if k in _CACHE:
            return _CACHE[k]
        if client is None:
            return False, "semantic unavailable"
        prompt = (
            "You are a strict yes/no classifier for email triage.\n"
            f'Question: "{question}"\n\n'
            f"Subject: {msg.subject}\nBody: {msg.body}\n\n"
            "Answer with a single word: YES or NO."
        )
        try:
            resp = client.chat.complete(
                model=_SEMANTIC_MODEL,
                messages=[{"role": "user", "content": prompt}],
                temperature=0,
                max_tokens=3,
                timeout_ms=4000,
            )
            answer = (resp.choices[0].message.content or "").strip().lower()
            result = answer.startswith("y")
            evidence = f'"{question}" -> {answer.upper() or "?"}'
            out = (result, evidence)
        except Exception:
            out = (False, "semantic unavailable")
        _CACHE[k] = out
        return out

    return semantic_fn


def clear_cache():
    _CACHE.clear()
