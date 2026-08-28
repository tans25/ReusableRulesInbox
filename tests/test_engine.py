from app.models import Message, Rule, Predicate
from app.engine import run


def msg(**kw):
    base = dict(id="m1", **{"from": "a@acme.com"}, from_domain="acme.com",
                to=["s@us.co"], subject="", body="", has_attachment=False, thread_length=1)
    base.update(kw)
    return Message(**base)


def rule(id, route, priority=10, match="all", preds=None):
    return Rule(id=id, name=id, route_to=route, priority=priority,
                match=match, predicates=preds or [])


def test_deterministic_match():
    m = msg(subject="Your invoice is attached")
    r = rule("r_bill", "Finance", preds=[Predicate(op="subject_matches", value="(?i)invoice")])
    [t] = run([r], [m])
    assert t.final_route == "Finance"
    assert t.matched_rule_id == "r_bill"
    assert t.considered[0].predicates[0].result is True
    assert t.considered[0].predicates[0].evidence.lower() == "invoice"


def test_priority_conflict():
    m = msg(subject="Cancelling — refund for this month?")
    billing = rule("r_bill", "Finance", priority=10,
                   preds=[Predicate(op="subject_matches", value="(?i)refund")])
    retention = rule("r_ret", "Retention", priority=20,
                     preds=[Predicate(op="subject_matches", value="(?i)cancel")])
    [t] = run([billing, retention], [m])
    assert t.final_route == "Retention"          # higher priority wins
    assert t.matched_rule_id == "r_ret"
    assert "r_bill" in t.also_matched             # billing still matched, but lost


def test_negate():
    m = msg(subject="Cancelling — refund for this month?")
    # Finance only if refund AND NOT cancel -> should NOT match here
    r = rule("r_bill", "Finance", match="all", preds=[
        Predicate(op="subject_matches", value="(?i)refund"),
        Predicate(op="subject_matches", value="(?i)cancel", negate=True),
    ])
    [t] = run([r], [m])
    assert t.final_route == "Inbox"
    assert t.matched_rule_id is None


def test_semantic_injection():
    m = msg(subject="hello", body="please help with my order")
    r = rule("r_sem", "Support", preds=[Predicate(op="semantic", value="is this a support request")])
    def sem(_m, _q):
        return True, "keyed on: please help with my order"
    [t] = run([r], [m], semantic_fn=sem)
    assert t.final_route == "Support"
    assert t.considered[0].predicates[0].evidence.startswith("keyed on")


def test_no_match_goes_to_inbox():
    m = msg(subject="random chatter")
    r = rule("r_bill", "Finance", preds=[Predicate(op="subject_matches", value="(?i)invoice")])
    [t] = run([r], [m])
    assert t.final_route == "Inbox"
