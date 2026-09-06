# Installation

`pulse-ep` is a Python package with optional extras for the web server,
figure generation, and the development toolchain. Pick the install that
matches your role.

## Requirements

| Component        | Minimum | Notes                                                   |
| ---------------- | ------- | ------------------------------------------------------- |
| Python           | 3.10    | Tested on CPython 3.10 / 3.11 / 3.12.                   |
| PostgreSQL       | 14      | Optional — required only to import or serve real study data. Tested on 16. |
| Docker           | 24+     | Optional — recommended for getting a database running quickly. |

If you only want to try out `pulse-ep`, you do **not** need PostgreSQL — the
[synthetic walkthrough](quickstart.md#1-synthetic-walkthrough-no-db-needed)
runs entirely on in-memory SQLite.

## From PyPI

```bash
# Core: importer, ORM, Python toolkit, CLI utilities
pip install pulse-ep

# Add the Flask REST API and 3D viewer
pip install "pulse-ep[server]"

# Add the figure / Excel / KML report generators
pip install "pulse-ep[figures]"

# Everything (server + figures + dev tools + docs builder)
pip install "pulse-ep[all]"
```

The extras correspond to functional capabilities, not to a separation
between "production" and "development". You can mix them freely — for
example, install `pulse-ep[server,figures]` on a deployment server but
skip `dev` and `docs`.

## From source

For contributors and reproducible-research workflows:

```bash
git clone https://gitlab.willert.net/sw/pulse-ep.git
cd pulse-ep
python -m venv .venv && source .venv/bin/activate
pip install -e ".[all]"
```

An editable install (`-e`) means your local edits are picked up
immediately without re-running `pip install`. The `[all]` extra includes
`pytest`, `ruff`, `mypy` and the `mkdocs` documentation builder.

Verify the install:

```bash
pulse-ep-demo
```

This should print a synthetic study summary in under five seconds and exit
cleanly with code 0. If it does, your install is functional.

## With Docker

For a zero-Python-on-the-host setup, the bundled `compose.yaml` spins up
PostgreSQL, the API server, and (optionally) pgAdmin:

```bash
git clone https://gitlab.willert.net/sw/pulse-ep.git
cd pulse-ep
cp .env.example .env  # edit PULSE_EP_JWT_SECRET_KEY at minimum
docker compose --profile server up -d --build
```

The full Docker workflow — including how the profiles interact — is covered
in the [Docker deployment guide](../guides/docker-deployment.md).

## Verifying the install

After any install method, run the smoke tests:

```bash
pulse-ep-demo                    # synthetic end-to-end pipeline
python -c "import pulse_ep; print(pulse_ep.__version__)"
```

If `pip install "pulse-ep[dev]"` was part of your install, also run the
unit-test suite:

```bash
pytest -q
```

The suite needs no database. You should see one skipped test — it exercises
schema creation on SQLite, which cannot render the PostgreSQL `JSONB` and
`ARRAY` types the ORM uses. That skip is expected, not a failure.

## Optional dependencies cheat sheet

| Extra      | Pulls in                                              | When you need it                            |
| ---------- | ----------------------------------------------------- | ------------------------------------------- |
| `server`   | Flask, Flask-JWT-Extended, Flask-CORS, Flask-Bcrypt, gunicorn | Running the REST API and 3D viewer.         |
| `figures`  | reportlab, openpyxl, simplekml                        | Generating PDF / Excel / KML reports.       |
| `dev`      | pytest, pytest-cov, ruff, mypy                        | Contributing to pulse-ep itself.            |
| `docs`     | mkdocs-material, mkdocstrings, pymdown-extensions     | Building this documentation site locally.   |
| `all`      | `server + figures + dev + docs`                       | Just give me everything.                    |

## Next steps

- [Quickstart](quickstart.md) — run the synthetic demo and then a real
  CARTO or EnSiteX study through the full pipeline.
- [Configuration](configuration.md) — set `PULSE_EP_DATABASE_URL`,
  `PULSE_EP_JWT_SECRET_KEY` and friends.
- [Docker deployment](../guides/docker-deployment.md) — bring up the
  full stack with one command.
