# Contributing to voicebench

Thanks for your interest in voicebench. This guide explains how to set up a development environment and get a change merged.

## Ways to contribute

- Report a bug with a scenario that reproduces it.
- Propose a metric. Explain how to compute it from the recorded audio, because voicebench measures from the outside.
- Add or improve an adapter.
- Share a scenario that exercises a failure mode other people are likely to hit.

For anything larger than a small fix, open an issue first so you can agree on the approach before you write code.

## Set up

You need Python 3.11 or later.

```sh
git clone https://github.com/superintelligenceco/voicebench
cd voicebench
python -m venv .venv
source .venv/bin/activate
python -m pip install -e ".[dev]"
```

## Run the checks

CI runs these commands. Run them before you open a pull request:

```sh
ruff check .
ruff format --check .
mypy
pytest --cov
```

Tests marked `realtime` use the wall clock and a local socket, and take a few seconds. Skip them while you iterate with `pytest -m "not realtime"`.

## Guidelines

- **Tests.** Every behavior change needs a test. Metric and VAD tests use synthesized audio from `voicebench.audio`, so they run offline and give exact expected values. Do not add tests that need network access or an external service.
- **Types.** The package passes `mypy --strict`. Keep it that way.
- **Honest numbers.** Do not add benchmark results for real products to the docs or examples. Numbers in docs must come from a command a reader can run.
- **Experimental adapters.** Mark an adapter experimental until the test suite exercises it against the real service.
- **Docs.** Update `README.md` or `docs/` when users see the change, and add an entry to `CHANGELOG.md` under `Unreleased`.
- **Style for docs.** Write in second person and present tense, use sentence-case headings, and avoid em-dashes.

## Commit messages

Use [Conventional Commits](https://www.conventionalcommits.org/): `feat:`, `fix:`, `docs:`, `test:`, `ci:`, `chore:`, or `refactor:`, followed by a short summary in the imperative mood. Release automation builds the changelog from these prefixes.

## Pull requests

1. Fork the repository and create a branch from `main`.
2. Make your change, with tests.
3. Run the checks above.
4. Open a pull request and fill in the template.

A maintainer reviews every pull request. Expect questions about how a change affects measured numbers, since the value of a benchmark depends on its numbers staying comparable.

## License

By contributing, you agree that your contributions are licensed under the Apache License 2.0.
