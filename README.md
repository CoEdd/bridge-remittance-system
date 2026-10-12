# Bridge

An AI money agent for international students: it reads an invoice or a payment message,
plans how to pay across currencies, shows the true cost, checks the payee, and pays in a
sandbox ledger only after the student approves. No real money moves.

Team: Malai Ren. WeBank Fintechathon 2026, International Track, Topic C.

This README is a short start. The full version (deployment, security report, licences)
comes in a later step.

## Run it

Docker Desktop must be running.

```
docker compose up --build     # backend on :8000, app on http://localhost:3000
make test                     # backend tests
make reset                    # restore the demo data while the app runs
```

## Two agent modes

- `AGENT_MODE=scripted` (default): a fixed driver proposes the tool calls of the demo. No
  internet, no key.
- `AGENT_MODE=live`: Claude proposes the tool calls. Needs `ANTHROPIC_API_KEY` in `.env`.

In both modes every call goes through the same policy engine, ledger and audit log. The
header of the app says which mode is on.

## Neuro-symbolic claim check

What it does: an LLM turns a message, in any wording and language, into a fixed set of
claims ("I act for the university", "pay this account", "15% off"). Fixed, readable rules
then judge those claims against facts we trust, and every verdict keeps the chain of facts
and rules behind it. It can only add caution: it never approves a payment.

- **Neural side** (`backend/app/claims/`): the claim schema and the extraction by the LLM.
  Every claim must quote the exact text it came from; a claim whose quote is not in the
  document is dropped.
- **Symbolic side** (`backend/app/claims/facts.py`, `backend/app/rules/`): trusted facts
  (institution registry, the student's payment history, the institution's policy) and a
  small rule engine running eight rules written as data.

**Measured result** (`docs/claim-check-eval.md`, test set of 25 messages in English, Malay
and Chinese, `claude-sonnet-5-5`, 12 October 2026):

| | Scams caught | Legitimate blocked by mistake |
|---|---|---|
| Keyword rules only | 8 / 13 | 1 / 12 |
| Claim check only | 13 / 13 | 0 / 12 |
| Both combined (what Bridge uses) | 13 / 13 | 1 / 12 |

Read with care: the set is small, was written by the same author as the rules, and has not
yet been reviewed by a person (`backend/eval/claims/DATA_CARD.md`).

**In scripted mode the claims are cached from a live run.** The claims for the six bundled
demo documents were returned by Claude once and are kept in
`backend/app/claims/cache/demo_claims.json` with the model name and the date. The rules
still run for real on those claims. For any other text, scripted mode falls back to a small
regex extractor. The app says which one was used ("Claims: cached from a live run").

```
make claims-cache    # ask Claude again for the demo documents' claims (needs a key)
make eval-claims     # run the evaluation again (live mode only)
```
