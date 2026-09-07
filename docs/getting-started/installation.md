# Installation

Python 3.10 or newer is required. PostgreSQL is needed for persistent storage
and the shared service; in-memory readers and the synthetic demo need no
running database. The supplied deployment and publication checks use
PostgreSQL 16. The CI test matrix covers CPython 3.10 through 3.14.

## From source

The supported installation route is the public source repository:

```bash
git clone https://github.com/swillert/pulse-ep.git
cd pulse-ep
python -m venv .venv
source .venv/bin/activate
pip install -e ".[all]"
```

These activation commands are for a POSIX shell. On Windows, activate the
virtual environment with `.venv\Scripts\Activate.ps1` in PowerShell.
An editable installation picks up changes in the checkout immediately.
For a fixed installation, omit `-e` and install from the chosen release checkout.

## Optional dependencies

The base package includes the numerical, mesh, plotting, database and Parquet
libraries, including PyVista and VTK. Extras add these capabilities:

| Extra | Adds | Use |
| --- | --- | --- |
| `server` | Flask, JWT, CORS, bcrypt, gunicorn | REST service and browser viewer |
| `figures` | reportlab, openpyxl, simplekml | PDF, Excel and KML report generators |
| `sevenzip` | py7zr | 7-Zip archives, including CARTO files named `.zip` |
| `mcp` | MCP SDK | MCP stdio server and protocol example |
| `dev` | pytest, pytest-cov, ruff, mypy | Tests and code checks |
| `docs` | MkDocs Material, mkdocstrings and Markdown plugins | Documentation site |
| `all` | All six extras above | Full development installation |

For example, `pip install -e ".[server,figures,sevenzip]"` installs a service
with report generation and support for both ZIP and 7-Zip exports.
JupyterLab and R, MATLAB or ParaView are installed separately when using the
corresponding [client examples](../examples/index.md).

## Verify the installation

From the activated environment and repository root:

```bash
pulse-ep-demo
python -c "import pulse_ep; print(pulse_ep.__version__)"
examples/verify.sh
```

The demo prints an in-memory synthetic mesh summary. The verification script
parses the paired synthetic CARTO and EnSite X exports without a database.
With `[all]` installed, run the complete local test suite:

```bash
pytest -q
ruff check .
ruff format --check .
```

The unit suite needs no live database. Tests for optional components require
the corresponding extras; with the complete installation they should run
rather than skip. PostgreSQL persistence is checked separately in the
publication's integration protocol.

## With Docker

The repository includes PostgreSQL and an optional server container:

```bash
cp .env.example .env
# Set PULSE_EP_JWT_SECRET_KEY and the database credentials in .env.
docker compose --profile server up -d --build
docker compose exec server pulse-ep-migrate
docker compose exec server pulse-ep-populate-colormaps
docker compose exec server pulse-ep-create-user --username admin --role admin
```

Docker Compose 2.24 or newer is required by the `env_file.required` option.
See [Docker deployment](../guides/docker-deployment.md) for persistent signal
storage, importing and upgrades. With this route, run commands inside the
server container, for example `docker compose exec server pulse-ep-demo`.

## Next steps

- [Quickstart](quickstart.md): configure, import and inspect a study.
- [Configuration](configuration.md): settings and their precedence.
- [Examples](../examples/index.md): connect analysis environments.
