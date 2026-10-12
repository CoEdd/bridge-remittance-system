# Claim-check evaluation set: data card

**What it is.** 40 short payment messages and invoices, in English, Malay and Chinese, each
labelled `block` (a scam) or `allow` (legitimate), with the reason for the label.

| Split | Items | Scams | Legitimate | English | Malay | Chinese |
|---|---|---|---|---|---|---|
| dev (`dev.jsonl`) | 15 | 7 | 8 | 6 | 5 | 4 |
| test (`test.jsonl`) | 25 | 13 | 12 | 10 | 8 | 7 |

**How it was made.** Every item was written for this project by the team's AI coding
assistant (Claude) in one sitting, before the claim check was run on any of them. None is
copied from a real message. Every name, bank, account number and institution is fictional,
except that the items use the demo's own data: the registered university (SPIU), the landlord
and the phone company the student has paid before.

**Human review: not done yet.** The brief asks for rewordings reviewed by hand. A team member
still has to read all 40 items and confirm each label. Until then, treat the numbers as a
first measurement, not a final one.

**Scams (20).** Fake agents offering a tuition discount; "our account has changed" notices;
threats (visa, deportation, account freeze) with a short deadline; scams naming institutions
that are not in our registry; and scams reworded to avoid the words our keyword rules look for.

**Legitimate (20).** Invoices and reminders from the registered university to its official
account; invoices from institutions that are not in the registry; rent and phone-bill reminders
to accounts paid before; small requests from friends; and two official notices that warn about
scams (they mention agents, discounts and visa threats without making any).

**The split.** `dev` may be used to tune the rules and the extraction prompt. `test` is never
used for tuning: it was fixed before the first run, and the reported numbers come from it.

**Known limits.**
- Small: 25 test items. One item is 4 percentage points of a rate.
- One author wrote both the rules and the items, so the items may be easier for these rules
  than real messages would be. An independent set would be a fairer test.
- Short, clean text. Real scam messages are messier (screenshots, voice notes, mixed languages).
- "Legitimate" items from unregistered institutions cannot be told from a careful scam by
  text alone. The claim check only warns on them (a one-time code and a waiting period), which
  counts as `allow` here.
