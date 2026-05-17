"""Create or update a pulse-ep user from the command line.

Required for the initial admin bootstrap: the `/register_user` HTTP endpoint
is currently unauthenticated, so production deployments should disable it
and rely on this CLI for account creation instead.

Examples
--------
Interactive (TTY-masked password)::

    pulse-ep-create-user --username admin --role admin

Scripted (read password from stdin)::

    echo 's3cret' | pulse-ep-create-user --username admin --password-stdin

Non-interactive with explicit password (avoid in shell history)::

    pulse-ep-create-user --username admin --password s3cret --role admin
"""

from __future__ import annotations

import argparse
import getpass
import sys


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="pulse-ep-create-user",
        description="Create or replace a pulse-ep user account (bcrypt-hashed).",
    )
    parser.add_argument("--username", required=True, help="Login name")
    parser.add_argument(
        "--role",
        default="admin",
        choices=["admin", "user"],
        help="Role granted to the account (default: admin)",
    )
    group = parser.add_mutually_exclusive_group()
    group.add_argument("--password", help="Password (avoid in shell history)")
    group.add_argument(
        "--password-stdin",
        action="store_true",
        help="Read password from stdin (newline-terminated)",
    )
    args = parser.parse_args(argv)

    if args.password_stdin:
        password = sys.stdin.readline().rstrip("\n")
    elif args.password:
        password = args.password
    else:
        password = getpass.getpass(f"Password for {args.username!r}: ")
    if not password:
        print("ERROR: empty password rejected", file=sys.stderr)
        return 2

    try:
        import bcrypt
    except ImportError:
        print(
            "ERROR: bcrypt is not installed. Install the server extra:\n"
            "    pip install 'pulse-ep[server]'",
            file=sys.stderr,
        )
        return 3

    from pulse_ep.core.database import get_db_session, init_db
    from pulse_ep.core.models import UserModel

    init_db()

    hashed = bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")

    with get_db_session() as session:
        existing = session.query(UserModel).filter_by(username=args.username).first()
        if existing:
            existing.password = hashed
            existing.role = args.role
            action = "updated"
        else:
            session.add(UserModel(username=args.username, password=hashed, role=args.role))
            action = "created"

    print(f"User {args.username!r} {action} with role {args.role!r}.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
