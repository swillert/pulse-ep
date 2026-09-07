# Contributing

Bug reports, documentation corrections and code contributions are welcome.
Use [GitHub Issues](https://github.com/swillert/pulse-ep/issues) and include
the software version, operating system, error message and a minimal synthetic
example. Remove identifying data from any export fragments you share.

## Development environment

```bash
git clone https://github.com/swillert/pulse-ep.git
cd pulse-ep
python -m venv .venv
source .venv/bin/activate
pip install -e ".[all]"
```

For optional pre-commit hooks, install the separate tool first:

```bash
pip install pre-commit
pre-commit install
```

## Checks

Run these from the repository root so the project's Ruff configuration applies:

```bash
ruff check .
ruff format --check .
pytest -q
mkdocs build --strict
examples/verify.sh
```

The unit suite needs no live database. Install all extras to exercise the
server, MCP, reporting and 7-Zip tests without optional-dependency skips.
The CI matrix runs Python 3.10 through 3.14. PostgreSQL and external-client
checks are recorded separately in the publication's reproducibility supplement.

## Documentation

Update the relevant guide or reference when changing an endpoint, CLI flag,
data field or setting. Verify example commands against the current code.
`mkdocs serve` serves the documentation locally at `http://127.0.0.1:8000`;
`mkdocs build` writes the static site to `site/`.

## Submit a contribution

Fork the public GitHub repository, branch from `main`, make the change and
run the relevant checks. Open a pull request describing the problem, resulting
behaviour and validation. The maintainer integrates accepted changes through
the canonical GitLab repository; direct GitHub branch edits are overwritten
by the mirror. See [Release process](release-process.md).

Use a short, descriptive commit message. Conventional Commit prefixes such
as `fix:`, `docs:` or `feat:` are welcome. Add tests for changed behaviour and
keep example inputs synthetic.

## Versioning and licence

The current `0.x` series is under development. Changes to public API behaviour
are documented in the [Changelog](changelog.md). Do not assume undocumented
internals are stable between releases. Published release tags should remain
immutable; corrections receive a new release.

Contributions are distributed under the project's [MIT License](https://github.com/swillert/pulse-ep/blob/main/LICENSE).
