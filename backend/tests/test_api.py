from fastapi.testclient import TestClient


def test_first_start_seeds_the_database(client: TestClient) -> None:
    me = client.get("/me").json()

    assert me == {
        "id": 1,
        "name": "Ahmad Faris",
        "preferred_language": "ms",
        "home_currency": "MYR",
        "per_txn_limit_minor": 500_000,
        "daily_limit_minor": 1_000_000,
        "new_payee_limit_minor": 300_000,
    }


def test_patch_me_changes_the_preferred_language(client: TestClient) -> None:
    response = client.patch("/me", json={"preferred_language": "zh"})

    assert response.status_code == 200
    assert response.json()["preferred_language"] == "zh"
    assert client.get("/me").json()["preferred_language"] == "zh"


def test_patch_me_refuses_an_unknown_language(client: TestClient) -> None:
    response = client.patch("/me", json={"preferred_language": "fr"})

    assert response.status_code == 422
    assert client.get("/me").json()["preferred_language"] == "ms"


def test_accounts_show_balances_equivalents_and_fx_source(client: TestClient) -> None:
    body = client.get("/accounts").json()
    wallets = {wallet["currency"]: wallet for wallet in body["accounts"]}

    assert body["home_currency"] == "MYR"
    assert body["fx_source"] == "offline_snapshot"
    assert [wallet["currency"] for wallet in body["accounts"]] == ["MYR", "CNY", "USD"]
    assert wallets["MYR"]["balance_minor"] == wallets["MYR"]["home_equivalent_minor"] == 985_000
    assert wallets["MYR"]["rate"] is None
    # CNY 3,420.00 / 1.62 = MYR 2,111.11 (rounded down); USD 180.00 / 0.23 = MYR 782.60
    assert (wallets["CNY"]["balance_minor"], wallets["CNY"]["home_equivalent_minor"]) == (342_000, 211_111)
    assert (wallets["USD"]["balance_minor"], wallets["USD"]["home_equivalent_minor"]) == (18_000, 78_260)
    assert wallets["CNY"]["rate"]["base"] == "MYR"
    assert wallets["CNY"]["rate"]["quote"] == "CNY"
    assert wallets["CNY"]["rate"]["mid_rate"] == "1.62"
    assert wallets["CNY"]["rate"]["source"] == "offline_snapshot"
    assert wallets["CNY"]["rate"]["fetched_at"].endswith("Z")


def test_transactions_are_newest_first_and_carry_currency_codes(client: TestClient) -> None:
    transactions = client.get("/transactions").json()
    dates = [transaction["business_date"] for transaction in transactions]

    assert dates == sorted(dates, reverse=True)
    assert dates[0] == "2026-10-15"
    assert all(amount["currency"] in ("MYR", "CNY", "USD") for t in transactions for amount in t["amounts"])
    assert all(len(transaction["amounts"]) == 1 for transaction in transactions)


def test_transactions_filters(client: TestClient) -> None:
    usd = client.get("/transactions", params={"currency": "USD"}).json()
    rent = client.get("/transactions", params={"category": "rent"}).json()
    week = client.get("/transactions", params={"days": 7}).json()
    eight = client.get("/transactions", params={"limit": 8}).json()
    both = client.get("/transactions", params={"currency": "CNY", "category": "eating_out", "days": 30}).json()

    assert {amount["currency"] for t in usd for amount in t["amounts"]} == {"USD"}
    assert [t["category_label"] for t in rent] == ["Rent", "Rent", "Rent"]
    assert week and all(t["business_date"] >= "2026-10-09" for t in week)
    assert len(eight) == 8
    assert len(both) == 10
    assert all(t["category"] == "eating_out" for t in both)


def test_transactions_refuse_bad_filters(client: TestClient) -> None:
    assert client.get("/transactions", params={"currency": "EUR"}).status_code == 422
    assert client.get("/transactions", params={"days": 0}).status_code == 422


def test_spending_insights(client: TestClient) -> None:
    body = client.get("/insights/spending").json()
    by_category = {item["category"]: item for item in body["categories"]}

    assert body["home_currency"] == "MYR"
    assert (body["period_days"], body["period_start"], body["period_end"]) == (30, "2026-09-16", "2026-10-15")
    assert set(by_category) == {"rent", "groceries", "eating_out", "transport", "phone", "subscriptions"}
    assert by_category["rent"]["total_minor"] == 280_000
    assert by_category["rent"]["change_pct"] == 0
    assert by_category["subscriptions"]["currency"] == "USD"
    assert by_category["eating_out"]["change_pct"] > 0
    # Sorted by size in home-currency terms: rent is the largest.
    assert body["categories"][0]["category"] == "rent"
    assert body["insight"] == (
        f"Eating out is up {by_category['eating_out']['change_pct']}% compared with the previous 30 days."
    )


def test_spending_forecast_adds_up(client: TestClient) -> None:
    forecast = client.get("/insights/spending").json()["forecast"]

    assert forecast["currency"] == "CNY"
    assert (forecast["as_of"], forecast["month_end"]) == ("2026-10-15", "2026-10-31")
    assert forecast["balance_minor"] == 342_000
    assert forecast["bills_due_minor"] == 9_800  # only the phone bill is due by 31 Oct
    assert forecast["projected_spending_minor"] > 0
    assert forecast["forecast_minor"] == (
        forecast["balance_minor"] - forecast["bills_due_minor"] - forecast["projected_spending_minor"]
    )


def test_bills_count_days_from_the_demo_date(client: TestClient) -> None:
    bills = client.get("/bills").json()

    assert [(bill["payee_name"], bill["amount_minor"], bill["due_date"], bill["due_in_days"]) for bill in bills] == [
        ("PearlTel Mobile", 9_800, "2026-10-28", 13),
        ("Nanshan Student Residence", 280_000, "2026-11-01", 17),
    ]
    assert {bill["status"] for bill in bills} == {"open"}


def test_payees(client: TestClient) -> None:
    payees = client.get("/payees").json()
    university = payees[0]

    assert len(payees) == 3
    assert university["name"] == "Shenzhen Polytechnic International University"
    assert university["institution_name"] == university["name"]
    assert university["verified_source"] == "institution_registry"
    assert university["first_paid_at"] == "2026-08-16"
    assert university["cooling_off_until"] is None


def test_demo_reset_restores_everything(client: TestClient) -> None:
    client.patch("/me", json={"preferred_language": "en"})
    before = client.get("/transactions").json()

    response = client.post("/demo/reset")

    assert response.status_code == 200
    assert response.json() == {"status": "reset", "demo_today": "2026-10-15", "fx_source": "offline_snapshot"}
    assert client.get("/me").json()["preferred_language"] == "ms"
    assert client.get("/transactions").json() == before
