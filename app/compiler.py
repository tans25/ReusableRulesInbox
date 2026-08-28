"""Compile a plain-English rule into the Rule IR at authoring time (not per message).

Uses Mistral's structured output (`chat.parse` with a Pydantic response_format), which
enforces our schema natively, so the model can only emit the closed set of predicate
operators. On failure we raise CompileError with a friendly message.
"""
from __future__ import annotations

import os
from .models import CompiledRule, Rule

_COMPILER_MODEL = "mistral-large-latest"

_SYSTEM = """You compile plain-English email triage rules into a strict JSON structure.

A rule has:
- name: short label
- match: "all" (every predicate must hold) or "any" (at least one)
- predicates: a list; each has op, value (a string), and negate (bool)
- route_to: exactly one of Finance, Retention, Support, Sales, Spam, Inbox
- labels: optional list of short tags

Allowed predicate ops and how to fill `value` (always a string):
- sender_domain_in       value: comma-separated domains, e.g. "acme.com, globex.com"
- sender_is              value: an exact email address
- subject_matches        value: a Python regex (you may prefix (?i) for case-insensitive)
- body_matches           value: a Python regex
- has_attachment         value: "true" or "false"
- recipient_count_gte    value: an integer as a string
- thread_length_gte      value: an integer as a string
- semantic               value: a yes/no question about the message, e.g. "asks for a refund"

Prefer deterministic ops (regex on subject/body, sender domain) over `semantic` when the
intent can be captured that way. Use `negate: true` for "unless"/"except" conditions.
Keep regexes simple and readable. Choose the single most appropriate route_to.
"""


class CompileError(Exception):
    pass


def compile_rule(source_nl: str, rule_id: str, priority: int = 10) -> Rule:
    api_key = os.environ.get("MISTRAL_API_KEY")
    if not api_key:
        raise CompileError("No MISTRAL_API_KEY set — can't compile new rules. "
                           "Set it in your environment and restart.")
    try:
        from mistralai.client import Mistral
        client = Mistral(api_key=api_key)
        resp = client.chat.parse(
            model=_COMPILER_MODEL,
            messages=[
                {"role": "system", "content": _SYSTEM},
                {"role": "user", "content": f'Compile this rule:\n"{source_nl}"'},
            ],
            response_format=CompiledRule,
            temperature=0,
        )
        compiled: CompiledRule = resp.choices[0].message.parsed
    except CompileError:
        raise
    except Exception as e:
        print(e)
        raise CompileError(
            "I couldn't express that as a rule — try phrasing it as a condition about "
            "the sender, the subject, or the message content."
        ) from e

    if not compiled.predicates:
        raise CompileError(
            "That didn't produce any conditions — try naming what to match on "
            "(sender, subject words, or content) and where it should go."
        )

    return Rule(
        id=rule_id,
        source_nl=source_nl,
        priority=priority,
        **compiled.model_dump(),
    )
