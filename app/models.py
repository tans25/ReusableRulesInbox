"""The data contract for the whole app.

The Rule IR is deliberately FLAT: a rule is a list of predicates combined with
`all`/`any`, each predicate optionally negated. This is far more reliable for LLM
structured output than a nested boolean tree, and it reads better on screen — which
is the entire point of the project (visible, inspectable logic).

`Predicate.value` is always a string at the schema level (easy for the compiler to
emit) and is interpreted per-op by the engine. See engine.parse_value.
"""
from __future__ import annotations

from typing import List, Literal, Optional
from pydantic import BaseModel, Field

# Closed set of predicate operators. The compiler may emit NOTHING outside this list.
PredicateOp = Literal[
    "sender_domain_in",     # value: comma-separated domains, e.g. "acme.com, globex.com"
    "sender_is",            # value: exact email
    "subject_matches",      # value: Python regex (may include (?i))
    "body_matches",         # value: Python regex
    "has_attachment",       # value: "true" / "false"
    "recipient_count_gte",  # value: integer as string
    "thread_length_gte",    # value: integer as string
    "semantic",             # value: a yes/no question about the message
]

Folder = Literal["Finance", "Retention", "Support", "Sales", "Spam", "Inbox"]


class Predicate(BaseModel):
    op: PredicateOp
    value: str = ""
    negate: bool = False


class CompiledRule(BaseModel):
    """The shape the LLM fills in. We wrap it into a full Rule ourselves."""
    name: str = Field(description="Short human name, e.g. 'Billing questions to Finance'")
    match: Literal["all", "any"] = "all"
    predicates: List[Predicate]
    route_to: Folder
    labels: List[str] = []


class Rule(CompiledRule):
    id: str
    source_nl: str = ""       # the original English, kept for the editable view
    priority: int = 10        # higher wins on conflict


class Message(BaseModel):
    id: str
    from_: str = Field(alias="from")
    from_domain: str
    to: List[str] = []
    subject: str = ""
    body: str = ""
    has_attachment: bool = False
    thread_length: int = 1

    model_config = {"populate_by_name": True}


# ---- Trace objects (the trust story) ----

class PredicateResult(BaseModel):
    op: PredicateOp
    value: str
    negate: bool
    result: bool          # final boolean AFTER applying negate
    evidence: str = ""    # matched substring, or why it was true/false


class RuleConsideration(BaseModel):
    rule_id: str
    rule_name: str
    priority: int
    match: Literal["all", "any"]
    route_to: Folder
    predicates: List[PredicateResult]
    matched: bool


class Trace(BaseModel):
    message_id: str
    final_route: Folder
    matched_rule_id: Optional[str] = None
    also_matched: List[str] = []
    considered: List[RuleConsideration] = []


class CompileRequest(BaseModel):
    source_nl: str


class RuleDiff(BaseModel):
    added: List[str] = []
    removed: List[str] = []
    unchanged: List[str] = []
