"""
The symbolic side of the claim check: a small forward-chaining rule engine.

Plain Python, no LLM, no library. A fact is a tuple such as
("official_account", "SPIU", "4100202600008815"). A condition is the same shape with
variables ("?i") in it. A rule fires when every condition holds; its conclusion becomes
a new fact that later rules can use. Every conclusion keeps the rule and the exact facts
that produced it, so the whole chain can be printed.
"""

from collections.abc import Iterator, Sequence
from dataclasses import dataclass
from typing import Any, Protocol

Atom = tuple[str, ...]
Bindings = dict[str, str]
WILDCARD = "_"


@dataclass(frozen=True)
class Fact:
    atom: Atom
    kind: str  # "claim" (from the document), "trusted" (from our own data) or "derived" (by a rule)
    source: str = ""  # where a trusted fact comes from, in words
    ref: Any = None  # the claim's position in the document, or the Derivation behind a derived fact


@dataclass(frozen=True)
class Either:
    """At least one of these patterns matches."""

    patterns: tuple[Atom, ...]


@dataclass(frozen=True)
class Not:
    """No claim or trusted fact matches this pattern. Unbound variables match anything."""

    pattern: Atom


@dataclass(frozen=True)
class Differ:
    """Two bound values are not the same."""

    left: str
    right: str


Condition = Atom | Either | Not | Differ


class Rule(Protocol):
    id: str
    when: tuple[Condition, ...]
    then: Atom


@dataclass(frozen=True)
class Derivation:
    """One conclusion, with the rule and the exact facts and claims that produced it."""

    rule: Any
    conclusion: Atom
    used: tuple[Fact, ...]


def _is_variable(term: str) -> bool:
    return term.startswith("?")


def _unify(pattern: Atom, atom: Atom, bindings: Bindings) -> Bindings | None:
    """The bindings extended so that `pattern` equals `atom`, or None when they cannot match."""
    if len(pattern) != len(atom) or pattern[0] != atom[0]:
        return None
    extended = dict(bindings)
    for term, value in zip(pattern[1:], atom[1:]):
        if term == WILDCARD:
            continue
        if _is_variable(term):
            if extended.setdefault(term, value) != value:
                return None
        elif term != value:
            return None
    return extended


def _fill(pattern: Atom, bindings: Bindings) -> Atom:
    return tuple(bindings.get(term, term) if _is_variable(term) else term for term in pattern)


def _match(
    conditions: Sequence[Condition], facts: list[Fact], bindings: Bindings, used: tuple[Fact, ...]
) -> Iterator[tuple[Bindings, tuple[Fact, ...]]]:
    """Every way to satisfy the conditions, left to right."""
    if not conditions:
        yield bindings, used
        return
    first, rest = conditions[0], conditions[1:]
    if isinstance(first, Differ):
        if bindings[first.left] != bindings[first.right]:
            yield from _match(rest, facts, bindings, used)
    elif isinstance(first, Not):
        base = (fact for fact in facts if fact.kind != "derived")
        if not any(_unify(first.pattern, fact.atom, bindings) is not None for fact in base):
            yield from _match(rest, facts, bindings, used)
    else:
        for pattern in first.patterns if isinstance(first, Either) else (first,):
            for fact in facts:
                extended = _unify(pattern, fact.atom, bindings)
                if extended is not None:
                    yield from _match(rest, facts, extended, (*used, fact))


def check_rules(rules: Sequence[Rule]) -> None:
    """"Not" may only look at claims and trusted facts, never at something a rule concludes."""
    concluded = {rule.then[0] for rule in rules}
    for rule in rules:
        for condition in rule.when:
            if isinstance(condition, Not) and condition.pattern[0] in concluded:
                raise ValueError(f"Rule {rule.id}: 'not' over the derived fact {condition.pattern[0]!r}.")


def run(rules: Sequence[Rule], facts: Sequence[Fact]) -> list[Derivation]:
    """
    Apply the rules until nothing new follows. Returns the derivations in the order they
    were made, one per rule and conclusion (the first way found).
    """
    check_rules(rules)
    known = list(facts)
    derivations: list[Derivation] = []
    seen: set[tuple[str, Atom]] = set()
    changed = True
    while changed:
        changed = False
        for rule in rules:
            for bindings, used in list(_match(rule.when, known, {}, ())):
                conclusion = _fill(rule.then, bindings)
                if (rule.id, conclusion) in seen:
                    continue
                seen.add((rule.id, conclusion))
                derivation = Derivation(rule, conclusion, used)
                derivations.append(derivation)
                if not any(fact.atom == conclusion for fact in known):
                    known.append(Fact(conclusion, "derived", ref=derivation))
                    changed = True
    return derivations


def chain(derivation: Derivation) -> list[Derivation]:
    """The derivation and every earlier one it rests on, earliest first."""
    steps: list[Derivation] = []
    for fact in derivation.used:
        if fact.kind == "derived":
            steps += [step for step in chain(fact.ref) if step not in steps]
    return [*steps, derivation]
