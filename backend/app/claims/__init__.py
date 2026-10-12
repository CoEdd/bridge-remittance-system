"""
The neuro-symbolic claim check.

Neural side (this package: schema.py, extract.py): an LLM turns a message, in any
wording and language, into a fixed set of claims, each with the exact text it came from.

Symbolic side (facts.py here, and app/rules/): explicit facts from data we trust, and
a small rule engine running explicit rules over the claims and the facts.

The check is an extra layer. It can add a block or a warning; it can never approve a
payment, lower a tier or remove another check's finding.
"""
