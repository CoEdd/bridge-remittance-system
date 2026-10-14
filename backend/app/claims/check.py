"""
The claim check, end to end: extract the claims (neural side), then judge them with the
rules against trusted facts (symbolic side), and keep the chain behind every conclusion.
"""

from datetime import datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app import audit
from app.claims import facts, words
from app.claims.extract import Extraction, extract
from app.claims.schema import Claim
from app.documents.extract import Field
from app.models import Document, User
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


def _reasoning(derivation: Derivation, claims: list[Claim], short: dict[int, str]) -> list[dict[str, Any]]:
    """
    The chain behind one conclusion, in plain words: what was said, what we know, which rule.
    Every line that states a trusted fact carries the sources behind it.
    """
    lines: list[dict[str, Any]] = []
    for step in engine.chain(derivation):
        entries = [
            {"text": words.says(claims[fact.ref], short.get(fact.ref)), "cites": []}
            if fact.kind == "claim"
            else {"text": words.from_source(fact), "cites": [words.cite_json(cite) for cite in facts.cites(fact)]}
            for fact in step.used
            if fact.kind != "derived"
        ]
        entries.append({"text": words.rule_line(step.rule.id, step.rule.text), "cites": []})
        for entry in entries:
            if all(entry["text"]["en"] != line["text"]["en"] for line in lines):
                lines.append(entry)
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
    session: Session,
    user: User,
    visible_text: str,
    fields: dict[str, Field],
    *,
    live: bool,
    client: Any = None,
    hints: str = "",
) -> dict[str, Any]:
    """Everything the claim check found in one document, ready to store with it."""
    extraction: Extraction = extract(visible_text, fields, live=live, client=client, hints=hints)
    result = judge(extraction.claims, facts.collect(session, user), facts.ground(extraction.claims, session))
    return {
        "origin": extraction.origin,
        "model": extraction.model,
        "cached_on": extraction.cached_on,
        "dropped": extraction.dropped,
        **result,
    }


def rejudge(session: Session, now: datetime) -> None:
    """
    Judge every stored document again with today's trusted facts, after a rule-source item
    was approved, rejected or edited. Symbolic side only: the claims stay as extracted. A
    document whose conclusions change gets a new claims.checked audit entry.
    """
    documents = session.scalars(select(Document).order_by(Document.id))
    for document in documents:
        check = document.claim_check or {}
        if "claims" not in check:
            continue
        user = session.get_one(User, document.user_id)
        claims = [Claim(row["type"], dict(row["args"]), row["source"], row["start"], row["end"]) for row in check["claims"]]
        result = judge(claims, facts.collect(session, user), facts.ground(claims, session))
        before = [(item["rule"], item["raises"]) for item in check.get("conclusions") or []]
        document.claim_check = {**check, **result}
        after = [(item["rule"], item["raises"]) for item in result["conclusions"]]
        if after != before:
            audit.append(
                session,
                "claims.checked",
                "system",
                {
                    "document_id": document.id,
                    "origin": check.get("origin"),
                    "model": check.get("model"),
                    "claims": len(claims),
                    "dropped": check.get("dropped", 0),
                    "conclusions": [
                        {"rule": item["rule"], "severity": item["severity"], "raises": item["raises"]}
                        for item in result["conclusions"]
                    ],
                    "rechecked": True,
                },
                now=now,
            )
