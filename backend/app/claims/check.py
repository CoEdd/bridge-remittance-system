"""
The claim check, end to end: extract the claims (neural side), then judge them with the
rules against trusted facts (symbolic side), and keep the chain behind every conclusion.
"""

from typing import Any

from sqlalchemy.orm import Session

from app.claims import facts, words
from app.claims.extract import Extraction, extract
from app.claims.schema import Claim
from app.documents.extract import Field
from app.models import User
from app.rules import engine
from app.rules.core_rules import CORE_RULES, SUPPORT_RULES, CoreRule
from app.rules.engine import Derivation, Fact

# A flagged claim has no fact that contradicts it; its evidence is the scam pattern it matches.
_PATTERN_OF = {"deadline_pressure": "deadline_pressure", "secrecy_request": "secrecy_request"}


def _short_names(trusted: list[Fact], grounded: list[Fact]) -> dict[int, str]:
    """Claim position -> the short name of the registered institution it names ("SPIU")."""
    registered = {fact.atom[1] for fact in trusted if fact.atom[0] == "registered_institution"}
    return {
        fact.ref: facts.acronym(fact.atom[1])
        for fact in grounded
        if len(fact.atom) > 1 and fact.atom[1] in registered and fact.atom[0] != "payee_account"
    }


def _reasoning(derivation: Derivation, claims: list[Claim], short: dict[int, str]) -> dict[str, list[str]]:
    """The chain behind one conclusion, in plain words: what was said, what we know, which rule."""
    lines: dict[str, list[str]] = {language: [] for language in words.LANGUAGES}
    for step in engine.chain(derivation):
        sentences = [
            words.says(claims[fact.ref], short.get(fact.ref)) if fact.kind == "claim" else words.from_source(fact)
            for fact in step.used
            if fact.kind != "derived"
        ]
        sentences.append(words.rule_line(step.rule.id, step.rule.text))
        for sentence in sentences:
            for language in words.LANGUAGES:
                if sentence[language] not in lines[language]:
                    lines[language].append(sentence[language])
    return lines


def _evidence(fact: Fact | None) -> dict[str, Any] | None:
    return {"words": words.fact_words(fact), "source": fact.source} if fact else None


def judge(claims: list[Claim], trusted: list[Fact], grounded: list[Fact]) -> dict[str, Any]:
    """Run the rules over the claims and the trusted facts. Deterministic; no LLM."""
    derivations = engine.run([*CORE_RULES, *SUPPORT_RULES], [*trusted, *grounded])
    core = [item for item in derivations if isinstance(item.rule, CoreRule)]
    blocks = [item for item in core if item.rule.severity == "block"]
    short = _short_names(trusted, grounded)

    def used_claims(derivation: Derivation) -> list[int]:
        return [fact.ref for fact in derivation.used if fact.kind == "claim"]

    rows = []
    for position, claim in enumerate(claims):
        against = [item for item in blocks if position in used_claims(item) and item.rule.marks == "contradicted"]
        flagged = claim.type in _PATTERN_OF and any(item.rule.marks == "flagged" for item in blocks)
        support = next((item for item in derivations if not isinstance(item.rule, CoreRule) and position in used_claims(item)), None)
        if against:
            # The rule that says most about this claim alone: the one resting on the fewest claims.
            chosen = min(against, key=lambda item: len(used_claims(item)))
            status = "contradicted"
            evidence = next((fact for fact in reversed(chosen.used) if fact.kind == "trusted"), None)
        elif flagged:
            status = "flagged"
            evidence = next((fact for fact in trusted if fact.atom == ("known_scam_pattern", _PATTERN_OF[claim.type])), None)
        elif support:
            status = "supported"
            evidence = next((fact for fact in reversed(support.used) if fact.kind == "trusted"), None)
        else:
            status, evidence = "unverifiable", None
        rows.append(
            {
                **claim.as_json(),
                "meaning": words.meaning(claim, short.get(position)),
                "status": status,
                "evidence": _evidence(evidence),
                "rules": [item.rule.id for item in core if position in used_claims(item)],
            }
        )

    conclusions = [
        {
            "rule": item.rule.id,
            "severity": item.rule.severity,
            "raises": item.rule.raises,
            "title": item.rule.title,
            "text": item.rule.text,
            "conclusion": list(item.conclusion),
            "claims": used_claims(item),
            "facts": [facts.as_json(fact) for fact in item.used if fact.kind == "trusted"],
            "reasoning": _reasoning(item, claims, short),
        }
        for item in core
    ]
    return {
        "claims": rows,
        "conclusions": conclusions,
        "blocks": sorted({item["raises"] for item in conclusions if item["severity"] == "block"}),
        "warns": sorted({item["raises"] for item in conclusions if item["severity"] == "warn"}),
    }


def run_check(
    session: Session, user: User, visible_text: str, fields: dict[str, Field], *, live: bool, client: Any = None
) -> dict[str, Any]:
    """Everything the claim check found in one document, ready to store with it."""
    extraction: Extraction = extract(visible_text, fields, live=live, client=client)
    result = judge(extraction.claims, facts.collect(session, user), facts.ground(extraction.claims, session))
    return {
        "origin": extraction.origin,
        "model": extraction.model,
        "cached_on": extraction.cached_on,
        "dropped": extraction.dropped,
        **result,
    }
