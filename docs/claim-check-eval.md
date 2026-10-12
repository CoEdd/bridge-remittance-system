# Neuro-symbolic claim check: evaluation

The LLM turns a message into a fixed set of claims; fixed rules judge them against facts we trust.
This file is written by `make eval-claims` and holds its real results.

- Split: **test** (25 items: 13 scams, 12 legitimate). Never used for tuning.
- Model: `claude-sonnet-5-5` · Date: 2026-10-12 · LLM calls: 25
- Claims extracted live for 25 of 25 items.
- Read with care: a small set, written by the same author as the rules and not yet reviewed by a person.
- How the set was made: `backend/eval/claims/DATA_CARD.md`.

**Result.** Adding the claim check catches 5 more of the 13 scams than the keyword rules alone, with no extra legitimate message blocked.

## Overall

| | Scams caught | Legitimate blocked by mistake |
|---|---|---|
| A. Keyword rules only | 8 / 13 (62%) | 1 / 12 (8%) |
| B. Claim check only | 13 / 13 (100%) | 0 / 12 (0%) |
| C. Both combined (what Bridge uses) | 13 / 13 (100%) | 1 / 12 (8%) |

## English

| | Scams caught | Legitimate blocked by mistake |
|---|---|---|
| A. Keyword rules only | 2 / 5 (40%) | 1 / 5 (20%) |
| B. Claim check only | 5 / 5 (100%) | 0 / 5 (0%) |
| C. Both combined (what Bridge uses) | 5 / 5 (100%) | 1 / 5 (20%) |

## Malay

| | Scams caught | Legitimate blocked by mistake |
|---|---|---|
| A. Keyword rules only | 3 / 4 (75%) | 0 / 4 (0%) |
| B. Claim check only | 4 / 4 (100%) | 0 / 4 (0%) |
| C. Both combined (what Bridge uses) | 4 / 4 (100%) | 0 / 4 (0%) |

## Chinese

| | Scams caught | Legitimate blocked by mistake |
|---|---|---|
| A. Keyword rules only | 3 / 4 (75%) | 0 / 3 (0%) |
| B. Claim check only | 4 / 4 (100%) | 0 / 3 (0%) |
| C. Both combined (what Bridge uses) | 4 / 4 (100%) | 0 / 3 (0%) |

## Every miss of A (Keyword rules only): 6

**T01** (English, fake_agent_discount). Scam not caught. Claims to be SPIU's fee partner with 8% off, to a company account. Found: R1, R2, R3, R4, R8.

> Official SPIU fee partner here. International students who pay via our service this week receive an 8% reduction on tuition. Your amount: CNY 11,040.00.
> Account name: Golden Bridge Education Services
> Account number: 6230 1188 4402 7765
> Bank: Shenzhen Bay Commercial Bank

**T04** (English, unregistered_discount). Scam not caught. Rebate for wiring an unregistered university's deposit to a representative, with secrecy. Found: R4, R7, R8.

> Pacific Coast University admissions desk: secure your place now. Students who wire the deposit to our regional representative get a 20% early-bird rebate. Deposit after rebate: USD 800.00.
> Name: Kevin Zhao
> Account number: 6217 4402 9981 3357
> Please don't mention this rebate to the main campus office.

**T05** (English, reworded). Scam not caught. Sorts out SPIU tuition for less through a personal account, without the usual scam words. Found: R1, R2, R3, R4, R8.

> Ahmad, quick one. A few of us sort out SPIU tuition for Malaysian students each term. Pass me CNY 10,500.00 and your CNY 12,000.00 bill shows as settled by Friday.
> Name: Farid Hamzah
> Account number: 6225 7719 3048 1126

**T09** (Malay, reworded). Scam not caught. A senior with 'someone inside' settles SPIU fees for less, in casual Malay. Found: R1, R2, R3, R4, R8.

> Ahmad, abang senior di SPIU ni. Saya ada orang dalam bahagian bendahari. Bagi saya CNY 9,800.00 je, yuran CNY 12,000.00 awak saya settlekan terus.
> Nama akaun: Khairul Anuar
> No. akaun: 6217 2290 4418 5563

**T13** (Chinese, reworded). Scam not caught. An acquaintance in an unregistered college's finance office settles fees for less. Found: R4, R8.

> 同学，我在海景理工学院财务室有熟人，可以帮你把学费办下来。你转我人民币 8,500.00 元，原本 10,000.00 元的学费就算结清了。
> 收款人：孙丽
> 账号：6228 3317 6642 9905

**T18** (English, official_warning). Legitimate message blocked. SPIU warns about scams; it asks for no payment. Found: THIRD_PARTY_DISCOUNT, SCAM_PATTERN.

> SPIU Student Affairs: beware of people claiming to be university payment agents who offer discounts or say your visa will be cancelled. The University never does this. If you receive such a message, do not pay and contact the Finance Office.

## Every miss of B (Claim check only): 0

None.

## Every miss of C (Both combined (what Bridge uses)): 1

**T18** (English, official_warning). Legitimate message blocked. SPIU warns about scams; it asks for no payment. Found: THIRD_PARTY_DISCOUNT, SCAM_PATTERN.

> SPIU Student Affairs: beware of people claiming to be university payment agents who offer discounts or say your visa will be cancelled. The University never does this. If you receive such a message, do not pay and contact the Finance Office.
