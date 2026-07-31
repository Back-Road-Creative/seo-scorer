# Contributing to seo-scorer

Thanks for your interest. This guide covers how to propose a change and get it
merged.

## Reporting

- **Bugs and features:** open an issue. For a bug, include the input, what you
  expected, and what you got.
- **Security vulnerabilities:** do **not** open a public issue — follow
  [SECURITY.md](SECURITY.md).

## Setup

Requires Python 3.11 or newer. From a clone of this repository:

```bash
python -m venv .venv && source .venv/bin/activate
pip install -e ".[store,dev]"
```

## The gates

CI runs these on every push and pull request. Run them first.

```bash
pytest
ruff check .
ruff format --check .
```

CI also installs the package with **no** extras and asserts that
`import seo_scorer` works and scores correctly with zero third-party packages
present.

## The one hard rule

**The scoring half of this package has no dependencies, and that is the
product.** `seo_scorer/scoring.py`, `metadata.py`, `events.py`, `validation.py`,
and `platforms/` may import from the standard library and from each other.
Nothing else.

`seo_scorer/store.py` is the single exception: it may use `filelock`, and it is
behind the `store` extra so a plain install never pulls it in. A new optional
dependency needs its own extra and its own import guard that names the extra in
the error message.

## Changes

- **Tests first.** For a bug fix, add a test that fails before your change and
  passes after. Never weaken or delete a test to make the suite pass.
- **Keep the output deterministic.** No network calls, no runtime downloads, no
  clock or locale dependence in scoring. Same input, same output, everywhere.
- **Docs land with the code.** A behaviour change updates the README in the
  same commit. A new limitation goes in the "What it does not do" section — an
  honest limit is more useful than a quiet one.
- **Thresholds are conventions.** If you propose changing one, say what evidence
  you have. "Everyone says 60 characters" is a real reason; it is also a reason
  the number belongs in an overridable method rather than a constant.
- **Conventional commits** (`feat:`, `fix:`, `docs:`, `test:`, `chore:`).
- One logical change per pull request, with a short summary and the gate output.

## Conduct

By participating you agree to the [Code of Conduct](CODE_OF_CONDUCT.md).
