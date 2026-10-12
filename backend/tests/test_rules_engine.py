"""The symbolic rule engine: variables, "not", comparisons, chaining and the recorded chain."""

from dataclasses import dataclass

import pytest

from app.rules.engine import Atom, Condition, Differ, Either, Fact, Not, chain, run


@dataclass(frozen=True)
class R:
    id: str
    when: tuple[Condition, ...]
    then: Atom


def trusted(*atom: str) -> Fact:
    return Fact(atom, "trusted", "test data")


def claim(position: int, *atom: str) -> Fact:
    return Fact(atom, "claim", ref=position)


def conclusions(rules: list[R], facts: list[Fact]) -> list[Atom]:
    return [item.conclusion for item in run(rules, facts)]


def test_a_variable_keeps_one_value_across_conditions() -> None:
    rule = R("same", (("says", "?x"), ("knows", "?x")), ("agree", "?x"))
    facts = [claim(0, "says", "a"), claim(1, "says", "b"), trusted("knows", "b"), trusted("knows", "c")]

    assert conclusions([rule], facts) == [("agree", "b")]


def test_constants_and_arity_must_match() -> None:
    rule = R("visa", (("threat", "visa"),), ("visa_threat",))

    assert conclusions([rule], [claim(0, "threat", "arrest")]) == []
    assert conclusions([rule], [claim(0, "threat", "visa", "extra")]) == []
    assert conclusions([rule], [claim(0, "threat", "visa")]) == [("visa_threat",)]


def test_not_holds_when_no_base_fact_matches() -> None:
    rule = R("unknown", (("account", "?a"), Not(("official", "?i", "?a"))), ("not_official", "?a"))

    assert conclusions([rule], [claim(0, "account", "111"), trusted("official", "U", "222")]) == [("not_official", "111")]
    assert conclusions([rule], [claim(0, "account", "111"), trusted("official", "U", "111")]) == []


def test_not_with_a_wildcard_means_nobody_at_all() -> None:
    rule = R("stranger", (("account", "?a"), Not(("paid_before", "_", "?a"))), ("never_paid", "?a"))

    assert conclusions([rule], [claim(0, "account", "111"), trusted("paid_before", "Landlord", "111")]) == []
    assert conclusions([rule], [claim(0, "account", "111"), trusted("paid_before", "Landlord", "999")]) == [("never_paid", "111")]


def test_not_may_only_look_at_base_facts() -> None:
    first = R("a", (("x",),), ("derived",))
    second = R("b", (("y",), Not(("derived",))), ("other",))

    with pytest.raises(ValueError, match="'not' over the derived fact 'derived'"):
        run([first, second], [claim(0, "x"), claim(1, "y")])


def test_differ_compares_two_bound_values() -> None:
    rule = R("changed", (("old", "?a"), ("new", "?b"), Differ("?a", "?b")), ("changed", "?a", "?b"))

    assert conclusions([rule], [trusted("old", "1"), claim(0, "new", "1")]) == []
    assert conclusions([rule], [trusted("old", "1"), claim(0, "new", "2")]) == [("changed", "1", "2")]


def test_either_accepts_any_of_its_patterns() -> None:
    rule = R("speaks", (Either((("is", "?i"), ("acts_for", "?i"))), ("registered", "?i")), ("speaks_for", "?i"))

    assert conclusions([rule], [claim(0, "acts_for", "U"), trusted("registered", "U")]) == [("speaks_for", "U")]
    assert conclusions([rule], [claim(0, "is", "U"), trusted("registered", "U")]) == [("speaks_for", "U")]
    assert conclusions([rule], [claim(0, "mentions", "U"), trusted("registered", "U")]) == []


def test_a_conclusion_feeds_later_rules_whatever_their_order() -> None:
    late = R("late", (("pressure",), ("doubt", "?a")), ("blocked",))
    early = R("early", (("account", "?a"), Not(("official", "_", "?a"))), ("doubt", "?a"))

    derivations = run([late, early], [claim(0, "pressure"), claim(1, "account", "111")])

    assert [item.rule.id for item in derivations] == ["early", "late"]
    assert [step.rule.id for step in chain(derivations[1])] == ["early", "late"]


def test_every_conclusion_records_the_rule_and_the_exact_facts_it_used() -> None:
    said, known = claim(0, "agent_of", "U"), trusted("policy", "U", "no_agents")
    rule = R("R2", (("agent_of", "?i"), ("policy", "?i", "no_agents")), ("agent_contradicted", "?i"))

    (derivation,) = run([rule], [trusted("policy", "V", "no_agents"), said, known])

    assert derivation.rule is rule
    assert derivation.conclusion == ("agent_contradicted", "U")
    assert derivation.used == (said, known)
    assert derivation.used[1].source == "test data"


def test_each_conclusion_is_kept_once_and_the_run_always_ends() -> None:
    loop = R("loop", (("seen", "?x"),), ("seen", "?x"))
    twice = R("twice", (Either((("a",), ("b",))),), ("hit",))

    assert conclusions([loop], [claim(0, "seen", "1")]) == [("seen", "1")]
    assert conclusions([twice], [claim(0, "a"), claim(1, "b")]) == [("hit",)]


def test_the_same_input_always_gives_the_same_output() -> None:
    rules = [R("r1", (("a", "?x"),), ("b", "?x")), R("r2", (("b", "?x"),), ("c", "?x"))]
    facts = [claim(0, "a", "1"), claim(1, "a", "2")]

    assert conclusions(rules, facts) == conclusions(rules, facts) == [("b", "1"), ("b", "2"), ("c", "1"), ("c", "2")]
