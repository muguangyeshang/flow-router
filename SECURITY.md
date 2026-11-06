# Security Policy

## Supported Versions

| Version | Supported |
|---|---|
| 1.1.x   | ✅ |
| < 1.1   | ❌ |

## Reporting a Vulnerability

- Please open a private security advisory (GitHub → Security → Report a vulnerability) or contact the maintainer directly.
- Include: affected version, reproduction steps, expected vs actual behavior.
- Expect a response within 7 days; fixes will land as a patch release with a CHANGELOG entry.

## Scope Notes

Both tools are offline, stdlib-only CLIs. Security-relevant surfaces are deliberately small:

- **flow-router**: no network, no subprocess, config loaded from local JSON only.
- **doc-claims**: executes `truth.cmd` shell commands **from your own claims.json** — treat claims.json like a build script; do not commit configs from untrusted sources. Input docs are read as text, never executed.
