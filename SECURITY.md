# Security Policy

## Secret Handling

The bridge redacts common token patterns before sending text to Claude:

- `sk-*`
- `tp-*`
- `Bearer ...`

This redaction is intentionally conservative and cannot catch every secret format. Users should avoid sending credentials, private keys, session cookies, or sensitive personal data through the bridge.

## Reporting Issues

Open a GitHub issue for security concerns that do not expose sensitive data. For sensitive reports, contact the repository owner privately through the contact method listed on their GitHub profile.
