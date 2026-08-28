"""Loads the sample inbox and seed rules from JSON and holds rules in memory.

Deliberately simple: no database, no migrations. Rules live in a dict for the session;
editing recompiles in place. Restarting resets to the seed rules.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Dict, List

from .models import Message, Rule

_DATA = Path(__file__).resolve().parent.parent / "data"


class Store:
    def __init__(self) -> None:
        self.messages: List[Message] = self._load_messages()
        self.rules: Dict[str, Rule] = self._load_rules()

    def _load_messages(self) -> List[Message]:
        raw = json.loads((_DATA / "sample_inbox.json").read_text())
        return [Message(**m) for m in raw]

    def _load_rules(self) -> Dict[str, Rule]:
        raw = json.loads((_DATA / "seed_rules.json").read_text())
        return {r["id"]: Rule(**r) for r in raw}

    def list_rules(self) -> List[Rule]:
        return sorted(self.rules.values(), key=lambda r: (-r.priority, r.id))

    def get_rule(self, rule_id: str) -> Rule | None:
        return self.rules.get(rule_id)

    def upsert_rule(self, rule: Rule) -> None:
        self.rules[rule.id] = rule

    def next_id(self) -> str:
        n = 1
        while f"r_new_{n}" in self.rules:
            n += 1
        return f"r_new_{n}"


store = Store()
