# Contributing

`pulse-ep` welcomes outside contributions — bug reports, documentation
improvements, code patches. This page is the practical reference; the
broader project rationale and architecture decisions live in
[Architecture](architecture.md).

## Reporting issues

Open an issue on the
[GitHub tracker](https://github.com/swillert/pulse-ep/issues). Useful
information:

- pulse-ep version (`python -c "import pulse_ep; print(pulse_ep.__version__)"`).
- Python version and operating system.
- A minimal reproduction (synthetic-mesh-based if at all possible — see
  `src/pulse_ep/examples/demo_synthetic.py` for the pattern).
- The full traceback or HTTP response.
- For CARTO-export-related bugs: the relevant XML snippet with
  patient-identifiable data stripped.

## Setting up a dev environment

```bash
git clone https://github.com/swillert/pulse-ep.git
cd pulse-ep
python -m venv .venv && source .venv/bin/activate
pip install -e ".[all]"
pre-commit install
```

The `[all]` extra pulls in `pytest`, `ruff`, `mypy`, the documentation
toolchain, the figure generators and the server stack.

`pre-commit install` wires the ruff hooks into your local git so the
exact same lint / format checks that run in CI also run on every
`git commit`.

## Running the test suite

```bash
pytest -q
```

Expect `23 passed, 1 skipped`. The skipped test exercises a JSONB
column that SQLite cannot emulate.

## Linting and formatting

```bash
ruff check .
ruff format --check .
```

A consistent code style is a non-negotiable. Run `ruff format .`
(without `--check`) before committing if anything is reformatted; both
the pre-commit hook and CI will block otherwise.

!!! warning "ruff must run from the project root"

    `ruff format` from `/tmp/` uses the default 88-character line
    length, which conflicts with the project's `line-length = 100` in
    `pyproject.toml`. Always run `ruff format` from the repository
    root.

## Building the documentation locally

```bash
pip install -e ".[docs]"
mkdocs serve
```

The site rebuilds on every save and is served at
<http://127.0.0.1:8000>. `mkdocs build` produces the static site in
`site/`.

The CI pages job builds the same documentation on every push to `main`
and deploys it to GitLab Pages.

## Commit style

`pulse-ep` uses [Conventional Commits](https://www.conventionalcommits.org/)
prefixes: `feat:`, `fix:`, `refactor:`, `docs:`, `test:`, `build:`,
`chore:`. The first line of every commit message must be under 72
characters and start with one of those prefixes.

Examples from the repo's history:

- `feat(config): introduce pydantic-settings — replace config.ini reads`
- `refactor(server): wire JWT secret, bcrypt rounds, CORS, host/port through Settings`
- `docs(examples): cross-language σ-recovery reproducibility demos`
- `build(ruff): exclude *.ipynb from ruff format`

## Submitting changes

1. **Fork** the repository on GitLab.
2. **Branch** from `main` with a descriptive name (`feature/x`,
   `fix/y`, `docs/z`).
3. **Implement + test**. Add unit tests for new behaviour. CI runs
   `ruff` + `pytest` against Python 3.10 / 3.11 / 3.12 — make sure
   yours passes locally first.
4. **Document**. If you added a CLI flag, REST endpoint, or
   `Settings` field, update the relevant page under `docs/reference/`.
5. **Open a merge request** against `main`. Reference any related
   issues. Keep the MR description focused on the *intent* of the
   change — the diff already shows the *what*.

## Code review expectations

- One reviewer (Sven Willert) for now. Reviews are usually within 48
  hours.
- Comments on style are bounded by what `ruff` enforces; humans focus
  on architecture, correctness and clarity.
- A merge needs a green pipeline and at least one approval. Squash
  merges are the default.

## Versioning

`pulse-ep` follows [SemVer](https://semver.org/). The current series is
`0.1.x`; we will cut `1.0.0` when the SoftwareX software paper is
accepted, at which point the public API surface (REST endpoints,
Python re-exports, CLI flags) becomes a stability contract.

Breaking changes between `0.1.x` patch releases are possible while we
firm up the API; each one is called out in the
[Changelog](changelog.md).

## License

By contributing to pulse-ep you agree that your contributions are
licensed under the
[MIT License](https://github.com/swillert/pulse-ep/blob/main/LICENSE).
