# Contributing to reid-score

Thanks for your interest. This project is a small, dependency-free privacy
toolkit, and the contribution flow is correspondingly lightweight.

## Quick start

```bash
git clone https://github.com/mokhld/reid-score.git
cd reid-score
python -m venv .venv && source .venv/bin/activate
pip install -e .
python -m unittest discover -s tests -v
```

The full test suite runs in under two seconds and has no network or system
dependencies. CI runs the same command on Python 3.10, 3.11, and 3.12
across Ubuntu and macOS — please make sure tests pass locally before
pushing.

## What's in scope

- Bug fixes (with a regression test).
- New attacker providers, anonymizer adapters, or compliance report
  renderers.
- Improvements to the bundled demographic data or the scripts that build
  it (`scripts/build_sample_data.py`).
- Documentation that brings the README closer to the code.

## What's out of scope (for now)

- Hard dependencies. The package promises zero runtime dependencies; LLM
  providers go through `urllib.request`.
- Breaking changes to the public API in `reid_score/__init__.py` without
  a CHANGELOG entry and a deprecation cycle.
- Heavy new ML models. If you need one, propose it as an optional
  extension first.

## Coding conventions

- Python 3.10+ syntax. `from __future__ import annotations` everywhere.
- Type hints on every public function and method.
- Docstrings are encouraged on public APIs. Don't write docstrings that
  restate the signature.
- Prefer fixing the root cause over papering over symptoms.
- Add a regression test alongside any bug fix.

## Submitting a PR

1. Create a topic branch from `main`.
2. Make your change. Run `python -m unittest discover -s tests -v`.
3. Update `CHANGELOG.md` under the "Unreleased" section.
4. Open a PR with a one-paragraph description of what changed and why.

## Reporting issues

For security issues, please open a private security advisory on GitHub
rather than a public issue. For everything else, a GitHub issue with a
minimal reproducer is the fastest way to get a fix.
