# Managing users

The service uses bcrypt passwords and JWT access tokens. It has three
roles: `admin`, `user` and `readonly`. Permissions apply across the database;
there are no per-study access lists or built-in SSO, LDAP or OIDC integration.
An external access layer can restrict who reaches the service, but API
clients still authenticate with pulse-ep JWTs.

## Permissions

| Operation | `readonly` | `user` | `admin` |
| --- | :---: | :---: | :---: |
| Read studies, meshes, points, waveforms and reports | ✓ | ✓ | ✓ |
| Calculate areas and compare maps | ✓ | ✓ | ✓ |
| Create, generate and delete reports | | ✓ | ✓ |
| Enqueue, prepare, edit and commit imports | | ✓ | ✓ |
| Create, edit and delete colormaps | | | ✓ |
| Change map attributes through REST | | | ✓ |
| Register an `admin` or `readonly` account through REST | | | ✓ |

**Standard-user self-registration is open.** Anyone who can reach
`/register_user` can create a `user` account. Creating an administrator does
not disable that endpoint. Restrict network access or apply an external
access-control policy before storing clinical data in a shared deployment.

## Create or update an account

The initializer creates the first administrator:

```bash
pulse-ep-init
```

For subsequent account creation or password/role changes:

```bash
pulse-ep-create-user --username clinician_01 --role user
pulse-ep-create-user --username mcp-reader --role readonly
```

The command prompts for a hidden password. **An existing account is updated**,
including its role. Always pass the intended role; the CLI default is `admin`.
For scripted use, pass the password on standard input with `--password-stdin`.

In Docker, prefix the command with `docker compose exec server`:

```bash
docker compose exec server pulse-ep-create-user --username mcp-reader --role readonly
```

There is no `Settings → Users` administrator screen. Accounts can be managed
with the CLI or created through the [registration endpoint](../reference/rest-api.md#post-register_user).

## MCP accounts

Use a dedicated `readonly` account for MCP. The MCP server exposes read and
calculation tools only, and the role also prevents changes through direct REST
requests with that account. Data access is still database-wide: isolate an
approved study collection in a separate deployment if narrower access is
required. See the [MCP guide](mcp.md) before enabling it.

## Revoking access

The schema has no enabled/disabled flag. Changing a password blocks new logins
with the old password; deleting an account blocks future logins entirely.
Existing JWTs retain their signed identity and role until expiry. The current
Flask-JWT-Extended default is 15 minutes; pulse-ep does not override it.
To invalidate all issued tokens immediately, change `PULSE_EP_JWT_SECRET_KEY`
and restart every server worker.

An administrator with direct database access can remove an account:

```python
from pulse_ep.core.database import get_db_session
from pulse_ep.core.models import UserModel

with get_db_session() as session:
    session.query(UserModel).filter_by(username="mcp-reader").delete()
```

Use [configuration](../getting-started/configuration.md#security) to set a
strong JWT secret and an appropriate bcrypt work factor.
