# Managing users

`pulse-ep` ships with a minimal role-based authentication model — enough
for a small research lab. Heavyweight identity (SSO, LDAP, OIDC) is
intentionally out of scope; if you need that, put pulse-ep behind a
reverse-proxy that does the auth and disable JWT login.

## The model

Users live in the `users` table (`UserModel`). Each user has:

| Field      | Notes                                                |
| ---------- | ---------------------------------------------------- |
| `username` | Unique. Login identifier.                            |
| `password` | bcrypt hash, never plaintext. Cost factor configurable via `PULSE_EP_BCRYPT_LOG_ROUNDS`. |
| `role`     | Either `admin` or `user`.                            |

Roles map to permissions:

| Operation                              | `user` | `admin` |
| -------------------------------------- | :----: | :-----: |
| Read studies / maps / meshes / reports |   ✓    |   ✓     |
| Create / save reports                  |   ✓    |   ✓     |
| Create / update colormaps              |        |   ✓     |
| Set EPMap attributes                   |        |   ✓     |
| Register new users                     |        |   ✓     |

The role is encoded into the JWT access token as the `role` claim, and
the Flask endpoints check it via Flask-JWT-Extended's `additional_claims`.

## Creating the first admin user

Right after `pulse-ep-import-carto` is run for the first time, the database
has no users — the login screen will reject every credential. Bootstrap an
admin with the CLI:

```bash
pulse-ep-create-user --username admin --role admin
```

You will be prompted for a password (input is hidden). If you want
to pass the password non-interactively, e.g. from a secret manager:

=== "Inline `--password`"

    ```bash
    pulse-ep-create-user --username admin --role admin --password '…'
    ```

    Only safe for ad-hoc scripts; the password ends up in your shell
    history.

=== "stdin pipe"

    ```bash
    op read "op://uksh-secrets/pulse-ep-admin/password" \
      | pulse-ep-create-user --username admin --role admin --password-stdin
    ```

    Recommended for CI / orchestration.

The password is hashed with bcrypt (cost factor 12 by default) before
it ever touches the database.

## Creating users inside a running Docker container

```bash
docker compose exec server pulse-ep-create-user --username clinician_01 --role user
```

This is the right path when the stack lives in Compose and you do not
have a local Python install.

## Adding more users (admin self-service)

Once an admin exists, they can register additional users through the
REST API. A common ergonomic shortcut:

```bash
TOKEN=$(curl -s -X POST "$PULSE_EP_BASE_URL/login_user" \
    -H "Content-Type: application/json" \
    -d '{"username":"admin","password":"…"}' \
    | python -c 'import sys, json; print(json.load(sys.stdin)["access_token"])')

curl -s -X POST "$PULSE_EP_BASE_URL/register_user" \
    -H "Content-Type: application/json" \
    -H "Authorization: Bearer $TOKEN" \
    -d '{"username":"clinician_01","password":"…","role":"user"}'
```

The web viewer also exposes this via `Settings → Users` for admins.

## Rotating a user's password

The CLI rejects existing usernames as a safety belt. To rotate, drop
into Python:

```python
from pulse_ep.core.database import get_db_session
from pulse_ep.core.models import UserModel
from flask_bcrypt import Bcrypt

new_hash = Bcrypt().generate_password_hash("new-strong-password").decode("utf-8")
with get_db_session() as s:
    user = s.query(UserModel).filter_by(username="clinician_01").first()
    user.password = new_hash
```

A dedicated `pulse-ep-reset-password` CLI is on the roadmap — for now,
this is the recommended path.

## Disabling vs. deleting a user

There is no `enabled` flag in the current schema; to revoke access,
delete the row:

```python
from pulse_ep.core.database import get_db_session
from pulse_ep.core.models import UserModel

with get_db_session() as s:
    s.query(UserModel).filter_by(username="clinician_01").delete()
```

Active JWT access tokens remain valid until they expire (default
1 hour from issue). If you need to invalidate tokens immediately,
rotate `PULSE_EP_JWT_SECRET_KEY` — that revokes **all** outstanding
tokens.

## Security notes

- pulse-ep stores **only** bcrypt hashes; if your database is leaked,
  hash-cracking the dump is computationally expensive but possible.
  Combine with disk encryption.
- The `register_user` endpoint is admin-only as of the current release.
  Earlier releases of pulse-ultimate exposed it unauthenticated — if
  you migrated from there, make sure the first thing you do is
  `pulse-ep-create-user` to lock it down.
- JWT tokens carry the `role` claim. Tampering with them would
  invalidate the signature; the secret in `PULSE_EP_JWT_SECRET_KEY`
  must therefore be a high-entropy random string and **not** be
  committed to version control.

## See also

- [Configuration → `PULSE_EP_JWT_SECRET_KEY`](../getting-started/configuration.md#security)
  — why this variable matters.
- [REST API → Authentication](../reference/rest-api.md#authentication)
  — full endpoint shapes.
- [`pulse-ep-create-user`](../reference/cli.md#pulse-ep-create-user) —
  CLI flag reference.
