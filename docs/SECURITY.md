# Security and data handling

Claims intake processes GDPR Article 9 health data (injury descriptions), Article 6
financial data (policy and bank metadata implicit in CRM lookups), and location data.
This document describes the repository's security surface and the controls in place.

## What lives where, and what is redacted

| Surface | Contents | Redaction |
|---|---|---|
| Live transcript on the bridge | Caller utterances, agent replies | `agent/pii_redact.py` strips policy #, plate, VIN, IBAN, phone, email, DOB before `bridge.publish` |
| Persisted conversation-test transcripts | Synthetic only — no real PII, but redaction is still applied | yes |
| GLiNER2 extractor inputs | Caller utterances | local only (no external call); model runs on-device |
| Tavily lookups | Free-form location strings only — no PII sent | n/a |
| Gemini Flash | Full conversation | governed by the provider's API data-use terms (no training on API data) |

## PII redactor

`agent.pii_redact.redact(text)` runs on every path that writes to a log handler, the
bridge, or disk. Twelve patterns, unit-tested in `tests/test_smoke.py::test_pii_redact`
and `test_pii_redact_extended`:

| Category | Pattern | Token |
|---|---|---|
| Policy number (DE-XXX-YYYY-NNNNNN) | `POLICY_NUMBER` | `[POLICY]` |
| 17-char VIN | `VIN` | `[VIN]` |
| German licence plate | `PLATE` | `[PLATE]` |
| German IBAN | `IBAN` | `[IBAN]` |
| Credit card (with separators) | `CREDIT_CARD` | `[CARD]` |
| Credit card (16 digit, no separators) | `CC_NO_SEPARATORS` | `[CARD]` |
| Sozialversicherungsnummer | `SOCIAL_SECURITY_DE` | `[SVNR]` |
| Krankenversichertennummer (health card) | `HEALTH_CARD_DE` | `[HEALTH_CARD]` |
| Driver licence (alphanumeric) | `DRIVER_LICENSE_DE` | `[DL]` |
| German phone (multi-segment) | `PHONE` | `[PHONE]` |
| Email | `EMAIL` | `[EMAIL]` |
| ISO date of birth | `DOB` | `[DOB]` |

Pattern order matters: DOB runs before PHONE so an ISO date like `1984-03-15` is not
consumed by the looser phone-number pattern.

## Dependency and code scanning

`aikido.yml` declares the scanning policy. The repository is scanned for dependency
vulnerabilities, and CI can be gated to block PRs that introduce critical CVEs in the
data-handling path. Scan output lives under [`docs/aikido-screenshots/`](aikido-screenshots/).

## Threat model

- **Caller-side prompt injection** — the system prompt forbids disclosing that the agent
  is automated; exercised by the adversarial conversation tests (`tests/juror_bot.py`).
- **Telephony abuse** — rate-limit inbound calls at the LiveKit / Twilio edge before they
  reach the agent.
- **Tavily quota exhaustion** — every call is wrapped in try/except and degrades to a
  generic acknowledgement rather than failing the turn.
- **Coverage / policy hallucination** — the system prompt is regenerated every turn from
  the live CRM JSON, and coverage answers are grounded in retrieved, cited clauses
  (`retrieval/`); the agent declines to assert coverage without a confident match.
- **Logging leakage** — `pii_redact.redact` is the single choke-point.
