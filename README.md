# Bridge

An AI money agent for international students: it reads an invoice or a payment message,
plans how to pay across currencies, shows the true cost, checks the payee, and pays in a
sandbox ledger only after the student approves. No real money moves.

Team: Malai Ren. WeBank Fintechathon 2026, International Track, Topic C.

Repository: https://github.com/CoEdd/bridge-remittance-system

Security self-assessment: `docs/security-self-assessment.md`. Execution evidence: the demo
video in `evidence/video/` and the logs of a full sandbox run in `evidence/sandbox-run/`.

## Run it

Docker Desktop must be running.

```
docker compose up --build     # backend on :8000, app on http://localhost:3000
make test                     # backend tests
make reset                    # restore the demo data while the app runs
make e2e                      # the whole demo in a browser (needs Node: cd frontend && npm install)
make check-ui                 # design rules and colour contrast of the frontend
make demo-video MODE=live     # record the demo video (MODE=scripted needs no API key)
make evidence MODE=live       # one full sandbox run through the API, logs in evidence/sandbox-run/
```

## Presenting the demo

Click **Demo** in the header (or press D). A bar under the header shows the nine steps and
one line to read out for the current step.

| Key | Does |
|---|---|
| Right arrow | Run the next step (or move on when it is done) |
| Left arrow | Go back one step; nothing is undone |
| R | Reset the demo (Enter confirms) |
| G | Show English under every answer |
| D | Hide or show the bar |

The bar never approves anything: at step 4 the presenter clicks Approve and types the
one-time code shown on screen. Steps done by hand count too; the bar reads the app's state.
For a live pitch, scripted mode is the safe choice (no network needed).

## Demo video

`evidence/video/` holds the demo video with voice-over and subtitles (`bridge-demo-final.mp4`,
4:45), the subtitles as `bridge-demo.srt`, and `voiceover-script.md` (every line with its start
and end time). `make demo-video` also writes the video without subtitles and without voice. It was
recorded in live mode with Claude by `scripts/video/record_demo.ts`, which uses the app in a
browser like a person: every click, typed character and screen state is real. The recorder draws
the cursor, the zoom, the title cards, a file picker in place of the system's own, and a tab
showing the invoice PDF. Waits for Claude's answers are played faster, with a "Sped up" badge.

## Two agent modes

- `AGENT_MODE=scripted` (default): a fixed driver proposes the tool calls of the demo. No
  internet, no key.
- `AGENT_MODE=live`: Claude proposes the tool calls. Needs `ANTHROPIC_API_KEY` in `.env`.

In both modes every call goes through the same policy engine, ledger and audit log. The
header of the app says which mode is on.

## Language

The app starts in English. Bahasa Melayu and Chinese are in the header; a switch applies
from Bridge's next answer on, and `make reset` goes back to English.

## Who sets the rules

- **The eight rules** are written by people and tested (`backend/app/rules/core_rules.py`).
- **The facts they use** come from published sources (page **Rule sources**,
  `backend/app/sources/`). In live mode a person adds a page or a PDF; Bridge fetches only
  that page (robots.txt obeyed, at most 3 redirects, 2 MB, HTML or PDF). Claude proposes
  items from a fixed vocabulary (`official_account`, `official_channel`, `policy`,
  `known_scam_pattern`), each with the exact sentence it rests on. Plain code drops any item
  whose sentence is not in the page word for word, any item outside the vocabulary, and any
  fact about an institution from a site that is not its own.
- **Nothing is active until a person approves it.** Approve, Reject and Edit (within the
  vocabulary) are logged in the audit chain. If a page changes when it is checked again, its
  items wait for review again.
- **Every fact in a verdict says where it comes from**, for example "Source: SPIU payment
  policy (spiu.example), approved by seed on 15 Sep 2026", with a link to the page.

The two bundled sources (SPIU's policy and a sample scam advisory, both fictional) were
written by us, pass the same checks and are stored as approved by "seed". Public warnings
from real universities, such as UTS and the University of Sussex, count only as evidence of
scam patterns, never as facts about SPIU. There is no login, so approvals are recorded as
"Demo reviewer".

## Neuro-symbolic claim check

What it does: an LLM turns a message, in any wording and language, into a fixed set of
claims ("I act for the university", "pay this account", "15% off"). Fixed, readable rules
then judge those claims against facts we trust, and every verdict keeps the chain of facts
and rules behind it. It can only add caution: it never approves a payment.

- **Neural side** (`backend/app/claims/`): the claim schema and the extraction by the LLM.
  Every claim must quote the exact text it came from; a claim whose quote is not in the
  document is dropped.
- **Symbolic side** (`backend/app/claims/facts.py`, `backend/app/rules/`): trusted facts
  (institution registry, the student's payment history, approved rule-source items) and a
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

## Execution evidence

`evidence/sandbox-run/` holds the logs of one full sandbox run with the real model, made by
`make evidence MODE=live`: the hash-chained audit log (JSON and CSV), the chain check and a
tampering simulation, every action with its tier and status, the ledger transactions, the
balances at each stage, the chat history, the payment receipt and the 11 red-team results.
`summary.md` lists the 13 checks the run makes; all passed. The security self-assessment is in
`docs/security-self-assessment.md`.

## Licence

MIT, copyright Team Malai Ren (see `LICENSE`). Third-party code, models, fonts and data are
listed with their licences in `THIRD_PARTY_NOTICES.md`.
