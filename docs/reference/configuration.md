# Configuration reference

The operator-facing narrative — "what env var do I set?" — is in
[Getting started → Configuration](../getting-started/configuration.md).
This page links into the Python API documentation for the underlying
classes.

## API

The configuration model and its helpers are documented under the Python
API page:

- [`pulse_ep.core.config.Settings`](python-api.md#pulse_ep.core.config.Settings)
  — the typed model. Every field maps to a `PULSE_EP_*` environment
  variable.
- [`pulse_ep.core.config.get_settings`](python-api.md#pulse_ep.core.config.get_settings)
  — cached singleton accessor.
- [`pulse_ep.core.config.reset_settings`](python-api.md#pulse_ep.core.config.reset_settings)
  — clear the cache (used by tests).

## Resolution order

Reproduced here for ease of cross-reference; the canonical version is in
[Getting started → Configuration](../getting-started/configuration.md#resolution-order).

1. **Process environment**, `PULSE_EP_*` variables.
2. **`.env`** file, path overridable via `PULSE_EP_ENV_FILE`.
3. **Legacy `config.ini`**, path overridable via `PULSE_EP_CONFIG`.
4. **Field defaults** on `Settings`.

## Validation

The model uses pydantic's standard validators:

- `bcrypt_log_rounds`: integer in `[4, 20]`. Out-of-range values raise
  `ValidationError` at construction time.
- `debug`: accepts the boolean spellings `1/0`, `true/false`, `yes/no`,
  `on/off`. Anything else is `False`.
- `cors_origins`: a list. Comma-separated strings from environment /
  `.env` are split (and trimmed) before validation, thanks to the
  `NoDecode` annotation on the field.
- `database_password` and `jwt_secret_key`: stored as `SecretStr` —
  never appear in `repr()`, but their plain values are retrievable via
  `.get_secret_value()`.

## Tests

[`tests/test_config.py`](https://gitlab.willert.net/sw/pulse-ep/-/blob/main/tests/test_config.py)
exercises every precedence rule, the secret-redaction behaviour and the
.env-file loading. It is the executable specification of this module.
