# Changelog

All notable changes to this project are documented here. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/) and this project
adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## 0.1.0

First release.

### Added

- `SEOScorer` — keyword extraction, title/description/tag optimisation, a
  four-component SEO structure score, keyword density, Flesch Reading Ease, and
  slug-plus-timestamp content ids. Pure standard library: no third-party
  imports, no network calls, no corpus downloads, and deterministic output.
- Platform adapters — `YouTubeAdapter`, `BlogAdapter`, `TwitterAdapter`, and the
  `BasePlatformAdapter` contract, which supplies the three `validate_*` helpers
  from four length/format answers.
- `PlatformValidator` — checks metadata against a platform's hard limits and
  returns errors, warnings, and a stamped copy of the metadata. Never mutates
  its input.
- `SEOMetadata` — a frozen dataclass covering identity, core SEO fields,
  per-platform extras, quality metrics, and validation state, with dict
  serialisation both ways.
- `SEOEvent` / `EventType` — event records that carry a CRC32 checksum, so a
  truncated or hand-edited line is caught on read.
- `seo_scorer.store.SEOEventStore` — append-only JSONL store with an advisory
  file lock, site partitioning, four indexes, and index rebuild on corruption.
  Behind the optional `store` extra, which is the only thing in the package
  with a third-party dependency (`filelock`).
- 169 tests, and a CI job that installs the package with no extras and asserts
  the scoring half still imports and scores with zero third-party packages
  present.

### Notes on the design

- **The structure score measures format, not truth.** Well-formed but
  fabricated or self-contradictory text scores exactly as high as accurate
  text. The method name says "structure" for that reason.
- **Keyword extraction is dependency-free by construction.** It uses a built-in
  English stopword list, frequency counting, and a capitalised-run pass for
  proper nouns — no tokeniser package and nothing fetched at runtime, so the
  same text always yields the same keywords.
- **Store files are created group-writable (0o664).** The lock library's
  default of 0o644 makes a store directory unusable by a second account in the
  same group; `seo_scorer.store.LOCK_MODE` is the single place that mode is
  set.
- **The index is a cache.** `events.jsonl` is the source of truth; a missing or
  unreadable `index.json` is rebuilt by scanning the log, so deleting it is
  safe.

### Roadmap

- Confidence-scored autofix: propose the minimal edit that clears a validation
  failure, with a confidence value so a caller can decide whether to apply it
  unattended. Not shipped — it lands when it has tests.
