"""GET /security/policy: what the Security page shows must be what the policy engine does."""

from fastapi.testclient import TestClient

from app.policy import BASE_TIERS
from app.policy.describe import SAFEGUARDS, TIER_RULES
from app.policy.reasons import REASONS


def test_every_tool_is_listed_under_the_tier_the_engine_gives_it(client: TestClient) -> None:
    tiers = client.get("/security/policy").json()["tiers"]

    assert [row["tier"] for row in tiers] == ["T0", "T1", "T2", "T3", "REFUSED"]
    listed = {tool["name"]: row["tier"] for row in tiers for tool in row["tools"]}
    assert listed == BASE_TIERS
    assert [(row["name"], row["rule"]) for row in tiers] == list(TIER_RULES.values())
    assert [tool["label"] for tool in tiers[2]["tools"]] == ["Convert currency", "Pay bill"]


def test_step_ups_and_refusals_come_from_the_reasons_registry(client: TestClient) -> None:
    tiers = {row["tier"]: row for row in client.get("/security/policy").json()["tiers"]}

    assert [reason["code"] for reason in tiers["T3"]["raised_by"]] == ["OVER_TXN_LIMIT", "NEW_PAYEE", "PAYEE_ADDITION"]
    refusals = [reason["code"] for reason in tiers["REFUSED"]["raised_by"]]
    assert refusals == [code for code, reason in REASONS.items() if reason.severity == "block"]
    assert {"UNTRUSTED_DOCUMENT", "MONEY_MULE_PATTERN", "DAILY_LIMIT", "NEW_PAYEE_LIMIT", "ARGUMENT_MISMATCH"} <= set(refusals)
    assert tiers["REFUSED"]["raised_by"][0]["title"] == REASONS[refusals[0]].title["en"]
    assert tiers["T0"]["raised_by"] == tiers["T1"]["raised_by"] == tiers["T2"]["raised_by"] == []


def test_the_limits_are_the_students_own(client: TestClient) -> None:
    me = client.get("/me").json()
    policy = client.get("/security/policy").json()

    assert policy["currency"] == "MYR"
    assert [(item["key"], item["label"], item["amount_minor"], item["seconds"], item["effect"]) for item in policy["limits"]] == [
        ("per_payment", "Per payment", me["per_txn_limit_minor"], None, "One-time code above this"),
        ("daily_outbound", "Daily outbound", me["daily_limit_minor"], None, "Refused above this"),
        ("new_payee", "New payee", me["new_payee_limit_minor"], None, "Refused above this"),
        ("cooling_off", "Cooling-off", None, 60, "Wait before a first payment runs"),
    ]
    assert (me["per_txn_limit_minor"], me["daily_limit_minor"], me["new_payee_limit_minor"]) == (500_000, 1_000_000, 300_000)
    # What happens above a limit follows the engine: a step-up for one, a refusal for the others.
    assert (REASONS["OVER_TXN_LIMIT"].severity, REASONS["DAILY_LIMIT"].severity, REASONS["NEW_PAYEE_LIMIT"].severity) == ("info", "block", "block")


def test_the_seven_safeguards_name_real_reason_codes(client: TestClient) -> None:
    safeguards = client.get("/security/policy").json()["safeguards"]

    assert [item["title"] for item in safeguards] == [
        "Payee verification",
        "Changed-details detection",
        "Scam patterns",
        "Injection detection",
        "Money-mule detection",
        "Re-check at execution",
        "Hash-chained audit log",
    ]
    assert all(code in REASONS for _, _, _, codes in SAFEGUARDS for code in codes)
    assert [reason["code"] for reason in safeguards[2]["reasons"]] == ["THIRD_PARTY_DISCOUNT", "SCAM_PATTERN"]
    assert all(item["text"].endswith(".") and len(item["text"].split()) <= 16 for item in safeguards)


def test_a_payee_shows_its_cooling_off_wait_only_while_a_first_payment_waits(client: TestClient) -> None:
    from tests.helpers import OTP, only, say

    client.post("/demo/documents/mule_message")
    action = only(say(client, "Can I forward this money as asked?"), "approval_required")[0]["actions"][0]
    by_name = lambda: {payee["name"]: payee for payee in client.get("/payees").json()}  # noqa: E731

    assert by_name()["Zhou Min"]["cooling_off_until"] is None
    client.post(f"/actions/{action['id']}/confirm")
    waiting = client.post(f"/actions/{action['id']}/otp", json={"code": OTP}).json()["action"]

    assert waiting["status"] == "cooling_off"
    assert by_name()["Zhou Min"]["cooling_off_until"] == waiting["cooling_off_until"]
    assert by_name()["Shenzhen Polytechnic International University"]["cooling_off_until"] is None
    assert by_name()["Zhou Min"]["verified_source"] is None
    client.post(f"/actions/{action['id']}/cancel")
    assert by_name()["Zhou Min"]["cooling_off_until"] is None
