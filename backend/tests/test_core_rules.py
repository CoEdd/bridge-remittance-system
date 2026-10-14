"""The eight rules of the claim check, each with fixture claims and facts. No LLM anywhere."""

from datetime import datetime, timezone
from typing import Any

import pytest

from app.claims import facts as trusted_facts
from app.claims.check import judge
from app.claims.schema import CLAIM_TYPES, Claim
from app.rules.core_rules import CORE_RULES, RULES_BY_ID
from app.rules.engine import Fact, check_rules
from app.sources.vocabulary import Citation

SPIU = "Shenzhen Polytechnic International University"
OFFICIAL, OTHER = "4100202600008815", "6217998820415530"
LANDLORD, RENT_ACCOUNT = "Lingnan Student Housing", "3300118820260042"

POLICY = Citation("SPIU payment policy", "spiu.example", None, "seed", datetime(2026, 9, 15, 4, tzinfo=timezone.utc))
FACTS = [
    Fact(("registered_institution", SPIU), "trusted", "Institution registry"),
    Fact(("official_account", SPIU, OFFICIAL), "trusted", "Institution registry"),
    Fact(("paid_before", SPIU, OFFICIAL), "trusted", "Your payment history"),
    Fact(("paid_before", LANDLORD, RENT_ACCOUNT), "trusted", "Your payment history"),
    Fact(("policy", SPIU, "no_payment_agents"), "trusted", "SPIU payment policy", ref=(POLICY,)),
    Fact(("policy", SPIU, "no_third_party_discounts"), "trusted", "SPIU payment policy"),
    Fact(("policy", SPIU, "never_threatens_visa"), "trusted", "SPIU payment policy"),
    Fact(("known_scam_pattern", "third_party_fee_discount"), "trusted", "Scam advisory"),
    Fact(("known_scam_pattern", "deadline_pressure"), "trusted", "Scam advisory"),
    Fact(("known_scam_pattern", "secrecy_request"), "trusted", "Scam advisory"),
]


def claims_of(*items: tuple[str, ...]) -> list[Claim]:
    """("payee_account", "6217...") -> a claim whose quote is its first argument."""
    return [Claim(kind, dict(zip(CLAIM_TYPES[kind], values)), source=values[0] if values else kind) for kind, *values in items]


# Claim types the rules match with their first argument (see facts.ground).
WITH_ARGUMENT = ("represents_institution", "agent_of_institution", "payee_name", "payee_account", "payee_bank", "threat")


def check(*items: tuple[str, ...]) -> dict[str, Any]:
    """Judge fixture claims against the fixture facts. Names are already the registered ones."""
    claims = claims_of(*items)
    grounded = []
    for position, claim in enumerate(claims):
        first = next(iter(claim.args.values()), "")
        atom = (claim.type, trusted_facts.digits(first) if claim.type == "payee_account" else first)
        grounded.append(Fact(atom if claim.type in WITH_ARGUMENT else (claim.type,), "claim", ref=position))
    return judge(claims, FACTS, grounded)


def fired(result: dict[str, Any]) -> list[str]:
    return [item["rule"] for item in result["conclusions"]]


def test_there_are_eight_rules_readable_as_data() -> None:
    check_rules(CORE_RULES)
    assert [rule.id for rule in CORE_RULES] == ["R1", "R2", "R3", "R4", "R5", "R6", "R7", "R8"]
    assert [rule.severity for rule in CORE_RULES] == ["block"] * 7 + ["warn"]
    for rule in CORE_RULES:
        assert set(rule.title) == set(rule.text) == {"en", "ms", "zh"}
        assert all(rule.title.values()) and all(rule.text.values())


def test_r1_a_registered_institutions_name_with_another_account() -> None:
    wrong = check(("represents_institution", SPIU), ("payee_account", OTHER))
    right = check(("represents_institution", SPIU), ("payee_account", OFFICIAL))
    agent = check(("agent_of_institution", SPIU), ("payee_account", OTHER))

    assert "R1" in fired(wrong) and "R1" in fired(agent) and "R1" not in fired(right)
    assert wrong["blocks"] == ["PAYEE_NOT_OFFICIAL"] and right["blocks"] == []


def test_r2_an_agent_claim_against_a_no_agents_policy() -> None:
    result = check(("agent_of_institution", SPIU))

    assert fired(result) == ["R2"] and result["blocks"] == ["THIRD_PARTY_DISCOUNT"]
    assert fired(check(("agent_of_institution", "Northbridge College"))) == []  # no policy on record
    assert "R2" not in fired(check(("represents_institution", SPIU)))


def test_r3_a_discount_in_the_institutions_name() -> None:
    assert "R3" in fired(check(("fee_discount", "15% off"), ("agent_of_institution", SPIU)))
    assert "R3" in fired(check(("fee_discount", "15% off"), ("represents_institution", SPIU)))
    assert "R3" not in fired(check(("fee_discount", "15% off"), ("represents_institution", "Northbridge College")))
    assert "R3" not in fired(check(("represents_institution", SPIU)))


def test_r4_a_discount_for_paying_a_third_party_whatever_the_institution() -> None:
    result = check(("fee_discount", "save 20%"), ("pays_via_third_party",), ("agent_of_institution", "Northbridge College"))

    assert fired(result) == ["R4"] and result["blocks"] == ["THIRD_PARTY_DISCOUNT"]
    assert "R4" not in fired(check(("fee_discount", "save 20%")))
    assert "R4" not in fired(check(("pays_via_third_party",)))


def test_r5_a_payee_paid_before_now_with_another_account() -> None:
    changed = check(("payee_name", LANDLORD), ("payee_account", "3300118820269999"))
    same = check(("payee_name", LANDLORD), ("payee_account", RENT_ACCOUNT))
    stranger = check(("payee_name", "Chen Li"), ("payee_account", "3300118820269999"))

    assert "R5" in fired(changed) and changed["blocks"] == ["BANK_DETAILS_CHANGED"]
    assert "R5" not in fired(same) and "R5" not in fired(stranger)


def test_r6_a_visa_threat_in_the_institutions_name() -> None:
    assert "R6" in fired(check(("threat", "visa"), ("represents_institution", SPIU)))
    assert "R6" not in fired(check(("threat", "arrest"), ("represents_institution", SPIU)))
    assert "R6" not in fired(check(("threat", "visa"), ("represents_institution", "Northbridge College")))


def test_r7_pressure_or_secrecy_counts_only_with_a_doubt_about_the_payee() -> None:
    doubt = (("represents_institution", SPIU), ("payee_account", OTHER))

    assert "R7" in fired(check(("deadline_pressure", "today only"), *doubt))
    assert "R7" in fired(check(("secrecy_request",), *doubt))
    # The same pressure with the official account is not a block.
    assert fired(check(("deadline_pressure", "today only"), ("represents_institution", SPIU), ("payee_account", OFFICIAL))) == []
    # A warning about the payee (R8) is doubt enough.
    assert fired(check(("deadline_pressure", "within 2 hours"), ("payee_name", "Chen Li"), ("payee_account", OTHER))) == ["R8", "R7"]


def test_r8_an_unknown_account_with_no_registered_institution_only_warns() -> None:
    result = check(("payee_name", "Chen Li"), ("payee_account", OTHER))

    assert fired(result) == ["R8"]
    assert (result["blocks"], result["warns"]) == ([], ["NEW_PAYEE"])
    assert fired(check(("payee_name", LANDLORD), ("payee_account", RENT_ACCOUNT))) == []
    assert fired(check(("represents_institution", "Northbridge College"), ("payee_account", OTHER))) == ["R8"]


def test_every_claim_gets_a_status_and_its_evidence() -> None:
    result = check(
        ("agent_of_institution", SPIU),
        ("payee_account", OTHER),
        ("fee_discount", "15% off"),
        ("deadline_pressure", "today only"),
        ("secrecy_request",),
        ("amount", "10200.00", "CNY"),
    )

    status = {item["type"]: item["status"] for item in result["claims"]}
    assert status == {
        "agent_of_institution": "contradicted",
        "payee_account": "contradicted",
        "fee_discount": "contradicted",
        "deadline_pressure": "flagged",
        "secrecy_request": "flagged",
        "amount": "unverifiable",
    }
    evidence = {item["type"]: item["evidence"] for item in result["claims"]}
    assert evidence["agent_of_institution"] == {
        "words": {
            "en": "SPIU's policy says it does not use payment agents",
            "ms": "Dasar SPIU menyatakan ia tidak menggunakan ejen pembayaran",
            "zh": "SPIU的政策规定其不使用缴费代理",
        },
        "source": "SPIU payment policy",
    }
    assert evidence["payee_account"]["words"]["en"] == "SPIU's registered account ends in 8815"
    assert evidence["payee_account"]["source"] == "Institution registry"
    assert evidence["deadline_pressure"]["source"] == "Scam advisory"
    assert evidence["amount"] is None


def test_a_claim_that_matches_a_trusted_fact_is_supported() -> None:
    result = check(("represents_institution", SPIU), ("payee_name", SPIU), ("payee_account", OFFICIAL), ("payee_bank", "Any Bank"))

    assert [(item["type"], item["status"]) for item in result["claims"]] == [
        ("represents_institution", "supported"),
        ("payee_name", "supported"),
        ("payee_account", "supported"),
        ("payee_bank", "unverifiable"),
    ]
    assert result["conclusions"] == [] and result["claims"][2]["evidence"]["source"] == "Institution registry"


def test_the_reasoning_chain_reads_in_plain_words() -> None:
    result = check(("agent_of_institution", SPIU))

    lines = result["conclusions"][0]["reasoning"]
    assert [line["text"]["en"] for line in lines] == [
        f"The message says: Says it acts for SPIU (“{SPIU}”).",
        "SPIU's policy says it does not use payment agents.",
        "Rule R2: An agent claim contradicted by the institution's own policy blocks the payment.",
    ]
    # Only the fact line has a source; the claim quotes the message, the rule is ours.
    assert [[cite["text"]["en"] for cite in line["cites"]] for line in lines] == [
        [],
        ["Source: SPIU payment policy (spiu.example), approved by seed on 15 Sep 2026"],
        [],
    ]
    assert lines[1]["cites"][0]["text"]["zh"] == "来源：SPIU payment policy (spiu.example)，由 seed 于 15 Sep 2026 批准"
    assert lines[2]["text"]["ms"].startswith("Peraturan R2: ")
    assert lines[2]["text"]["zh"].startswith("规则 R2：")


def test_a_chained_conclusion_shows_the_step_it_rests_on() -> None:
    result = check(("deadline_pressure", "today only"), ("represents_institution", SPIU), ("payee_account", OTHER))

    r7 = next(item for item in result["conclusions"] if item["rule"] == "R7")
    lines = [line["text"]["en"] for line in r7["reasoning"]]
    assert [line.split(":")[0] for line in lines if line.startswith("Rule")] == ["Rule R1", "Rule R7"]
    assert lines[-1] == f"Rule R7: {RULES_BY_ID['R7'].text['en']}"
    assert any("Pressure to pay fast" in line for line in lines)


@pytest.mark.parametrize("rule", CORE_RULES, ids=[rule.id for rule in CORE_RULES])
def test_every_rule_raises_a_reason_the_policy_engine_knows(rule: Any) -> None:
    from app.policy.reasons import REASONS

    assert rule.raises in REASONS
    # A block must refuse and a warning must step up: never the other way round.
    assert (REASONS[rule.raises].severity == "block") is (rule.severity == "block")
