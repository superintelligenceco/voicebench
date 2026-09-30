# Security policy

## Supported versions

voicebench is pre-1.0. Security fixes land on `main` and ship in the next release. Only the latest release receives fixes.

## Report a vulnerability

Do not open a public issue for a security problem. Report it privately through GitHub's [private vulnerability reporting](https://github.com/superintelligenceco/voicebench/security/advisories/new) for this repository.

Include:

- A description of the problem and its impact.
- Steps or a scenario file that reproduces it.
- The voicebench version and adapter involved.

You can expect an acknowledgment within 5 business days and a status update at least every 14 days until the report is resolved.

## Scope

voicebench connects to agents you point it at, and it loads adapter classes from module paths you pass it. Treat scenario files like code: a scenario can name any importable Python class as its adapter. Only run scenarios you trust.

Reports never include adapter credentials. The `websocket` adapter removes query strings and user info from URLs, and the `livekit` adapter reads keys from options or environment variables without writing them to the report. If you find a secret in a report, report it as a vulnerability.
