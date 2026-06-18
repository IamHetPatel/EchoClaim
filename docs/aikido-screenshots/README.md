# Dependency scan output

This directory holds the before/after dependency-scan screenshots referenced from the
"Dependency and code scanning" section of [`../SECURITY.md`](../SECURITY.md).

## Capturing a scan

1. Connect the repository at <https://app.aikido.dev> (GitHub OAuth → "Connect a new
   repository").
2. Wait for the initial scan to finish (a few minutes, depending on dependency count).
3. Screenshot the Issues page showing the finding split (Critical / High / Medium / Low)
   and save it as `before.png`.
4. Run AutoFix on flagged dependencies; merge the fix PRs that keep tests green.
5. Re-scan and screenshot the result as `after.png`.
6. Optionally, `ci-gate.png` — `aikido.yml` configured as a required CI check.

## Files

```
docs/aikido-screenshots/
├── README.md       (this file)
├── before.png      (initial scan, all severities)
├── after.png       (post-fix)
└── ci-gate.png     (optional — required-check configuration)
```

`agent/pii_redact.py` is the redaction boundary and `aikido.yml` is the scan policy; the
screenshots are the scan evidence.
