"""The deterministic rule executor.

Pure functions only: no file I/O, no network. Semantic predicate evaluation is passed
in as `semantic_fn(message, question) -> (bool, evidence)` so the engine stays fully
testable with a stub and no mocks.
"""
from __future__ import annotations

import re
from typing import Callable, List, Tuple

from .models import (
    Message, Rule, Predicate,
    PredicateResult, RuleConsideration, RuleDiff, Trace,
)

# Injected semantic evaluator: (message, question) -> (result, evidence)
SemanticFn = Callable[[Message, str], Tuple[bool, str]]


def _no_semantic(_msg: Message, _q: str) -> Tuple[bool, str]:
    """Default when no LLM is wired: semantic predicates resolve False, safely."""
    return False, "semantic unavailable"


def parse_value(op: str, value: str):
    """Interpret the string `value` according to the operator."""
    v = (value or "").strip()
    if op == "sender_domain_in":
        return [d.strip().lower() for d in v.split(",") if d.strip()]
    if op in ("recipient_count_gte", "thread_length_gte"):
        try:
            return int(v)
        except ValueError:
            return 0
    if op == "has_attachment":
        return v.lower() in ("true", "1", "yes")
    return v


def _eval_raw(pred: Predicate, msg: Message, semantic_fn: SemanticFn) -> Tuple[bool, str]:
    """Evaluate a predicate BEFORE applying negate. Returns (result, evidence)."""
    op = pred.op
    val = parse_value(op, pred.value)

    if op == "sender_domain_in":
        hit = msg.from_domain.lower() in val
        return hit, msg.from_domain if hit else f"sender domain {msg.from_domain} not in list"

    if op == "sender_is":
        hit = msg.from_.lower() == str(val).lower()
        return hit, msg.from_ if hit else f"sender is {msg.from_}"

    if op == "subject_matches":
        m = re.search(val, msg.subject) if val else None
        return (bool(m), m.group(0) if m else "no subject match")

    if op == "body_matches":
        m = re.search(val, msg.body) if val else None
        return (bool(m), m.group(0) if m else "no body match")

    if op == "has_attachment":
        hit = msg.has_attachment == bool(val)
        return hit, f"has_attachment={msg.has_attachment}"

    if op == "recipient_count_gte":
        hit = len(msg.to) >= int(val)
        return hit, f"{len(msg.to)} recipients"

    if op == "thread_length_gte":
        hit = msg.thread_length >= int(val)
        return hit, f"thread length {msg.thread_length}"

    if op == "semantic":
        return semantic_fn(msg, val)

    return False, f"unknown op {op}"


def eval_predicate(pred: Predicate, msg: Message, semantic_fn: SemanticFn) -> PredicateResult:
    raw, evidence = _eval_raw(pred, msg, semantic_fn)
    result = (not raw) if pred.negate else raw
    return PredicateResult(
        op=pred.op, value=pred.value, negate=pred.negate,
        result=result, evidence=evidence,
    )


def eval_rule(rule: Rule, msg: Message, semantic_fn: SemanticFn) -> RuleConsideration:
    results = [eval_predicate(p, msg, semantic_fn) for p in rule.predicates]
    if not results:
        matched = False
    elif rule.match == "all":
        matched = all(r.result for r in results)
    else:
        matched = any(r.result for r in results)
    return RuleConsideration(
        rule_id=rule.id, rule_name=rule.name, priority=rule.priority,
        match=rule.match, route_to=rule.route_to,
        predicates=results, matched=matched,
    )


def run(rules: List[Rule], messages: List[Message], semantic_fn: SemanticFn = _no_semantic) -> List[Trace]:
    """Route every message. Conflict resolution is strict priority: highest priority
    matching rule wins; ties broken by rule order. Others that matched are listed in
    `also_matched`. No match -> Inbox."""
    traces: List[Trace] = []
    for msg in messages:
        # Consider rules highest-priority first; stable sort preserves order on ties.
        ordered = sorted(enumerate(rules), key=lambda p: (-p[1].priority, p[0]))
        considered = [eval_rule(r, msg, semantic_fn) for _, r in ordered]

        winners = [c for c in considered if c.matched]
        if winners:
            winner = winners[0]
            trace = Trace(
                message_id=msg.id,
                final_route=winner.route_to,
                matched_rule_id=winner.rule_id,
                also_matched=[c.rule_id for c in winners[1:]],
                considered=considered,
            )
        else:
            trace = Trace(
                message_id=msg.id, final_route="Inbox",
                matched_rule_id=None, also_matched=[], considered=considered,
            )
        traces.append(trace)
    return traces


def predicate_line(pred: Predicate) -> str:
    """Human-readable one-line rendering of a predicate (used by the diff)."""
    op_text = {
        "sender_domain_in": "sender domain in",
        "sender_is": "sender is",
        "subject_matches": "subject matches",
        "body_matches": "body matches",
        "has_attachment": "has attachment",
        "recipient_count_gte": "recipients >=",
        "thread_length_gte": "thread length >=",
        "semantic": "message",
    }.get(pred.op, pred.op)
    prefix = "NOT " if pred.negate else ""
    return f"{prefix}{op_text} {pred.value}".strip()


def diff_rules(old: Rule, new: Rule) -> "RuleDiff":
    from .models import RuleDiff
    old_lines = [predicate_line(p) for p in old.predicates]
    new_lines = [predicate_line(p) for p in new.predicates]
    old_set, new_set = set(old_lines), set(new_lines)
    return RuleDiff(
        added=[l for l in new_lines if l not in old_set],
        removed=[l for l in old_lines if l not in new_set],
        unchanged=[l for l in new_lines if l in old_set],
    )
