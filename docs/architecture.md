# Architecture

This page is the internal engineering reference for contributors. The
canonical source is [`ARCHITECTURE.md`](https://gitlab.willert.net/sw/pulse-ep/-/blob/main/ARCHITECTURE.md)
at the repository root — included verbatim below so the documentation
and the in-repo file never drift.

{%
    include-markdown "../ARCHITECTURE.md"
    heading-offset=1
%}

## Going deeper

For task-focused walkthroughs of the same architecture pieces:

- [Configuration](getting-started/configuration.md) — how the
  `pydantic-settings` layer works in practice.
- [Data model](reference/data-model.md) — schema diagram and per-table
  notes.
- [REST API reference](reference/rest-api.md) — every endpoint the
  Flask app exposes.
- [Python API reference](reference/python-api.md) — auto-generated from
  module docstrings; the cleanest entry point if you want to consume
  pulse-ep from your own Python code.
