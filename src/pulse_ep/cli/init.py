#!/usr/bin/env python3
"""pulse-ep-init — bring a fresh installation to a running state.

The quickstart is fifteen commands, and the ones that are easy to forget are
the ones whose absence looks like a different bug: without
``pulse-ep-populate-colormaps`` the viewer shows no colours and the
troubleshooting page has an entry for it; without a real
``PULSE_EP_JWT_SECRET_KEY`` the server runs on a loudly-warned placeholder;
a waveform store that differs between import and server silently serves 404s.

So this asks what it cannot work out, writes ``.env``, and runs the rest.

    pulse-ep-init                       # ask what is missing, do the rest
    pulse-ep-init --non-interactive     # ask nothing; flags and defaults only
    pulse-ep-init --mcp --mcp-user mcp  # enable MCP and create its read-only account

It is **idempotent**: an existing ``.env`` is never overwritten without
saying so, migrations are only applied when they are behind, existing colormap values and users
are preserved, while standard colormap display flags are synchronised. Running it again after an upgrade
is a reasonable thing to do.

Secrets are generated, not asked for: a JWT key nobody typed is a key nobody
reused. The MCP account's password is printed once, in the client
configuration block you paste — not written into ``.env``, where the server
has no use for it.
"""

from __future__ import annotations

import argparse
import json
import os
import secrets
import shutil
import sys
from pathlib import Path

from dotenv import dotenv_values, set_key

DEFAULT_ENV_FILE = ".env"
DEFAULT_DATABASE_URL = "postgresql://pulse:pulse@localhost:5432/pulse"
DEFAULT_WAVEFORM_DIR = "waveforms"
DEFAULT_DROP_DIR = "drop"


# ── asking ────────────────────────────────────────────────────────────────
class Asker:
    """Questions, or defaults where nobody can answer them.

    Non-interactive is not a special mode with its own code path: it is the
    same run with every answer already given, so what CI does and what a
    person does cannot drift apart.
    """

    def __init__(self, interactive: bool) -> None:
        self.interactive = interactive and sys.stdin.isatty()

    def text(self, prompt: str, default: str) -> str:
        if not self.interactive:
            return default
        answer = input(f"{prompt} [{default}]: ").strip()
        return answer or default

    def yes(self, prompt: str, default: bool) -> bool:
        if not self.interactive:
            return default
        suffix = "Y/n" if default else "y/N"
        answer = input(f"{prompt} [{suffix}]: ").strip().casefold()
        return default if not answer else answer.startswith("y")

    def secret(self, prompt: str) -> str:
        """A password: typed twice, or generated when nobody is typing."""
        if not self.interactive:
            return secrets.token_urlsafe(18)
        import getpass

        while True:
            first = getpass.getpass(f"{prompt} (empty = generate one): ")
            if not first:
                return secrets.token_urlsafe(18)
            if first == getpass.getpass("Repeat: "):
                return first
            print("  they differ, try again")


# ── steps ─────────────────────────────────────────────────────────────────
def env_values(database_url: str, waveform_dir: str, drop_dir: str, mcp_enabled: bool) -> dict:
    """The settings a fresh installation needs, with the secret generated.

    Generated, never asked for: a JWT key nobody typed is a key nobody
    reused, and the alternative is the loudly-warned development placeholder
    the server falls back to when the variable is unset.
    """
    return {
        "PULSE_EP_DATABASE_URL": database_url,
        "PULSE_EP_JWT_SECRET_KEY": secrets.token_urlsafe(48),
        "PULSE_EP_WAVEFORM_STORE_DIR": waveform_dir,
        "PULSE_EP_DROP_DIR": drop_dir,
        "PULSE_EP_MCP_ENABLED": "1" if mcp_enabled else "0",
    }


def write_env(path: Path, values: dict, ask: Asker) -> tuple[bool, dict]:
    """Write ``.env``, or keep the existing one.

    Returns ``(written, effective values)`` — the existing file's settings win
    when it is kept, so everything after this step configures what will
    actually run rather than what would have been written.
    """
    if path.exists():
        existing = _read_env(path)
        keep = not ask.yes(f"{path} exists. Replace it?", default=False)
        if keep:
            print(f"  keeping {path} ({len(existing)} settings)")
            # Persist absent keys as well: returning generated defaults only
            # in memory would leave the next server process unconfigured.
            if path.stat().st_mode & 0o077:
                path.chmod(0o600)
                print(f"  tightened {path} to mode 600 (it holds the JWT secret)")
            additions = {key: value for key, value in values.items() if key not in existing}
            if additions:
                for key, value in additions.items():
                    set_key(str(path), key, str(value), quote_mode="always")
                print(f"  added missing settings: {', '.join(additions)}")
            return False, {**values, **existing}
        shutil.copy(path, path.with_suffix(".env.bak"))
        path.with_suffix(".env.bak").chmod(0o600)
        print(f"  previous file kept as {path.with_suffix('.env.bak')}")

    path.parent.mkdir(parents=True, exist_ok=True)
    path.touch(mode=0o600)
    path.chmod(0o600)
    path.write_text(
        "# Written by pulse-ep-init; see docs/getting-started/configuration.md.\n",
        encoding="utf-8",
    )
    for key, value in values.items():
        set_key(str(path), key, str(value), quote_mode="always")
    print(f"  wrote {path} (mode 600)")
    return True, values


def _read_env(path: Path) -> dict:
    return {key: value for key, value in dotenv_values(path).items() if value is not None}


def check_database(url: str) -> str | None:
    """``None`` if the database answers, otherwise why it does not."""
    try:
        import sqlalchemy as sa

        engine = sa.create_engine(url)
        with engine.connect() as connection:
            connection.execute(sa.text("select 1"))
        return None
    except Exception as exc:  # a URL that does not connect is the usual mistake
        return f"{type(exc).__name__}: {str(exc).splitlines()[0][:160]}"


def migrate() -> None:
    from pulse_ep.cli.migrate import main as migrate_main

    migrate_main([])


def seed_colormaps() -> None:
    from pulse_ep.cli.populate_colormaps import populate_colormaps

    populate_colormaps()


def create_account(username: str, password: str, role: str) -> bool:
    import bcrypt

    from pulse_ep.core.config import get_settings
    from pulse_ep.core.database import get_db_session
    from pulse_ep.core.models import UserModel

    hashed = bcrypt.hashpw(
        password.encode("utf-8"), bcrypt.gensalt(rounds=get_settings().bcrypt_log_rounds)
    ).decode("utf-8")
    with get_db_session() as session:
        existing = session.query(UserModel).filter_by(username=username).first()
        if existing is not None:
            # Never silently reset a password: the account may be in use, and
            # the summary must not print a credential that does not work.
            print(
                f"  account {username!r} exists already ({existing.role}) — "
                "left as it is, password unchanged"
            )
            return False
        session.add(UserModel(username=username, password=hashed, role=role))
        session.commit()
    print(f"  created {username!r} ({role})")
    return True


def mcp_client_config(base_url: str, username: str, password: str) -> str:
    """The block to paste into an MCP client, with the password in it.

    Deliberately not written to ``.env``: the server never needs it, and a
    credential is better handed over once than left in a file beside the code.
    """
    return json.dumps(
        {
            "mcpServers": {
                "pulse-ep": {
                    "command": shutil.which("pulse-ep-mcp") or "pulse-ep-mcp",
                    "env": {
                        "PULSE_EP_MCP_ENABLED": "1",
                        "PULSE_EP_MCP_BASE_URL": base_url,
                        "PULSE_EP_MCP_USERNAME": username,
                        "PULSE_EP_MCP_PASSWORD": password,
                    },
                }
            }
        },
        indent=2,
    )


# ── the run ───────────────────────────────────────────────────────────────
def run(args) -> int:
    from pulse_ep.core.roles import ADMIN, READONLY

    ask = Asker(interactive=not args.non_interactive)
    env_path = Path(args.env_file)

    print("pulse-ep-init")
    print()
    print("1. Configuration")
    database_url = args.database_url or ask.text(
        "   PostgreSQL URL", os.environ.get("PULSE_EP_DATABASE_URL") or DEFAULT_DATABASE_URL
    )
    waveform_dir = args.waveform_dir or ask.text("   Waveform store", DEFAULT_WAVEFORM_DIR)
    drop_dir = args.drop_dir or ask.text("   Drop directory", DEFAULT_DROP_DIR)
    if args.mcp is None and ask.interactive:
        print("   MCP serves this deployment to an AI client, read-only. Study")
        print("   data then leaves it for a language model, so establish what")
        print("   you may send before saying yes — see docs/guides/mcp.md.")
    mcp_enabled = args.mcp if args.mcp is not None else ask.yes("   Serve MCP access?", False)

    values = env_values(database_url, waveform_dir, drop_dir, mcp_enabled)
    # Environment values have the same precedence here as in Settings.
    process_values = {key: os.environ[key] for key in values if key in os.environ}
    values.update(process_values)
    _, effective = write_env(env_path, values, ask)
    effective.update(process_values)
    requested_mcp = mcp_enabled
    from pulse_ep.core.config import TRUE_VALUES

    mcp_enabled = str(effective["PULSE_EP_MCP_ENABLED"]).strip().casefold() in TRUE_VALUES
    if mcp_enabled != requested_mcp:
        # An existing file or the process environment decides, but silently
        # dropping what the operator just asked for sends them looking for the
        # fault in the MCP client. Say which setting won, and where it lives.
        asked = "on" if requested_mcp else "off"
        won = "on" if mcp_enabled else "off"
        print(f"  ! you asked for MCP {asked}; {env_path} and the environment say {won}")
        print("    change PULSE_EP_MCP_ENABLED there, or remove it, to override")
    os.environ["PULSE_EP_ENV_FILE"] = str(env_path.resolve())

    for key in ("PULSE_EP_WAVEFORM_STORE_DIR", "PULSE_EP_DROP_DIR"):
        directory = effective.get(key)
        if directory:
            Path(directory).mkdir(parents=True, exist_ok=True)
    print(
        f"  directories ready: {effective.get('PULSE_EP_WAVEFORM_STORE_DIR')}, "
        f"{effective.get('PULSE_EP_DROP_DIR')}"
    )

    # Everything below talks to the database through the settings, so the
    # process must see what was just written.
    for key, value in effective.items():
        os.environ[key] = value
    from pulse_ep.core.config import reset_settings

    reset_settings()

    print()
    print("2. Database")
    problem = check_database(effective["PULSE_EP_DATABASE_URL"])
    if problem:
        print(f"  cannot connect: {problem}")
        print("  start it (docker compose up -d) or fix PULSE_EP_DATABASE_URL, then run again.")
        return 2
    print("  connected")
    migrate()
    seed_colormaps()

    print()
    print("3. Accounts")
    admin_user = args.admin_user or ask.text("   Administrator login", "admin")
    admin_password = args.admin_password or ask.secret(f"   Password for {admin_user!r}")
    admin_created = create_account(admin_user, admin_password, ADMIN)

    mcp_config = None
    if mcp_enabled:
        mcp_user = args.mcp_user or (
            ask.text("   Read-only account for the MCP server", "mcp") if ask.interactive else None
        )
        if mcp_user:
            mcp_password = args.mcp_password or secrets.token_urlsafe(18)
            if create_account(mcp_user, mcp_password, READONLY):
                mcp_config = mcp_client_config(args.base_url, mcp_user, mcp_password)
            else:
                print(
                    f"  the MCP client keeps the password {mcp_user!r} already has; "
                    f"reset it with:  pulse-ep-create-user --username {mcp_user} "
                    "--role readonly"
                )

    print()
    print("Done. Next:")
    print("  pulse-ep-server")
    if admin_created and args.admin_password is None:
        # Only for an account this run created — printing a generated password
        # for a pre-existing one would hand out a credential that cannot log in.
        print(f"  log in as {admin_user!r} / {admin_password}")
    elif not admin_created:
        print(f"  log in as {admin_user!r} (existing password)")
    if mcp_enabled:
        print()
        print("  MCP access is ON. Study data reaches a language model through")
        print("  it: keep to the rules that apply to your data, and adapt what")
        print("  is sent where they ask for more than the anonymiser removes.")
    if mcp_config:
        print()
        print("  Register the MCP server with your client (the password is not")
        print("  stored anywhere else — copy it now):")
        print()
        print("\n".join("    " + line for line in mcp_config.splitlines()))
    return 0


def _build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="pulse-ep-init",
        description="Configure a fresh pulse-ep installation and bring it up.",
    )
    p.add_argument(
        "--env-file",
        default=os.environ.get("PULSE_EP_ENV_FILE", DEFAULT_ENV_FILE),
        help="Where to write settings.",
    )
    p.add_argument("--database-url", help="PostgreSQL URL.")
    p.add_argument("--waveform-dir", help="Root for Parquet waveform storage.")
    p.add_argument("--drop-dir", help="Directory the import watcher scans.")
    p.add_argument("--admin-user", help="Administrator login to create.")
    p.add_argument("--admin-password", help="Its password (generated when omitted).")
    p.add_argument("--mcp-user", help="Read-only account for the MCP server.")
    p.add_argument("--mcp-password", help="Its password (generated when omitted).")
    p.add_argument(
        "--base-url",
        default="http://127.0.0.1:5000",
        help="How the MCP server reaches this deployment (default: %(default)s).",
    )
    mcp = p.add_mutually_exclusive_group()
    mcp.add_argument(
        "--mcp", dest="mcp", action="store_true", default=None, help="Serve MCP access."
    )
    mcp.add_argument("--no-mcp", dest="mcp", action="store_false", help="Refuse MCP access.")
    p.add_argument(
        "--non-interactive",
        action="store_true",
        help="Ask nothing: flags and defaults only, and generate what is missing.",
    )
    return p


def main(argv: list[str] | None = None) -> int:
    return run(_build_parser().parse_args(argv))


if __name__ == "__main__":
    sys.exit(main())
