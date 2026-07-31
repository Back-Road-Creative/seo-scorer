# Security Policy

## Supported versions

Only the latest released tag receives security fixes. Pin a released `v*` tag;
`main` is unstable.

## Threat model in one paragraph

This library parses text you give it and, with the optional store, reads and
writes files in a directory you name. It makes no network calls, spawns no
processes, and evaluates nothing. The realistic risks are therefore denial of
service from pathological input, and file handling in the store: path traversal
via a caller-supplied storage path, a lock that does not lock, or a permission
mode wider than you intended. Reports in those areas are especially welcome.

Two behaviours are deliberate, not vulnerabilities:

- **Store files are created group-writable (0o664)** so several accounts in a
  shared group can use one store directory. If that is too wide, set
  `seo_scorer.store.LOCK_MODE` before creating a store, or place the directory
  somewhere with a restrictive ACL.
- **The CRC32 checksum on each event detects corruption, not tampering.** It is
  an integrity check against truncated writes and accidental edits. Anyone who
  can write to the log can recompute a valid checksum. If you need
  tamper-evidence, sign the log.

## Reporting a vulnerability

Report privately. Do **not** open a public issue for a security report.

- Preferred: open a private advisory via GitHub's **Security → Report a
  vulnerability** tab on this repository.
- Fallback, if that tab is unavailable to you: open a public issue containing
  **only** the words "security report, requesting a private channel" — no
  details, no proof of concept — and a maintainer will reply with somewhere
  private to send them.

Please include the affected version or commit, a description of the issue and
its impact, reproduction steps, and any suggested fix.

## What to expect

- Acknowledgement within 5 business days.
- An initial assessment and severity triage within 10 business days.
- Coordinated disclosure: we agree a timeline with you before any public
  write-up, and credit reporters who want it.

## Scope

In scope: everything under `seo_scorer/`, and the workflow in
`.github/workflows/`.

Out of scope: the SEO quality of metadata this library scores. It measures
format, not truth — a high score on misleading text is documented behaviour, not
a vulnerability.
