# Release process

The canonical development repository is the maintainer's
[GitLab](https://gitlab.willert.net/sw/pulse-ep). CI mirrors `main` and tags to
[public GitHub](https://github.com/swillert/pulse-ep). GitHub hosts the public
issue tracker and accepts contributions for maintainer integration. Its `main`
branch is written only by the mirror job, which pushes the current tip of the
canonical `main` without `--force`: a commit made directly on GitHub does not
get overwritten, it makes every later mirror run fail until someone resets that
branch by hand. That is deliberate — a forced push cannot tell a stray commit
from a pipeline arriving out of order, and the second one silently deletes
work.

## Prepare locally

1. Update `pyproject.toml`, `src/pulse_ep/__init__.py`, `CITATION.cff` and the
   changelog together. The author order is **Sven Willert, Derk Frank, Evgeny Lian**.
2. Check the README, guides and example commands against the implementation.
3. Run the local verification from a complete installation:

```bash
ruff check .
ruff format --check .
pytest -q
examples/verify.sh
mkdocs build --strict
python -m pip wheel . --no-deps --wheel-dir dist
```

The paper's supplementary integration protocol checks PostgreSQL and the
actual R, MATLAB, ParaView and MCP clients separately. Its source snapshot,
version, hashes and results must correspond to the release being submitted.

## Publish the reviewed commit and a new tag

Commit the reviewed changes first. Create a **new** version tag; never move an
already published tag to include a correction. For the current release candidate:

```bash
git tag -a v0.4.2        # write release notes in the tag message
git push origin main
git push origin v0.4.2
```

Run these only after the intended changes are committed on `main`. The mirror
job runs independently of the test jobs, so a public mirror update is not
proof of a passing pipeline. Verify both CI and the public tag before creating
a release. A tag pipeline mirrors tags without moving GitHub's `main`; existing
remote tags are not overwritten.

## GitHub Release and Zenodo

Create the matching [GitHub Release](https://github.com/swillert/pulse-ep/releases/new)
from the new tag and include its release notes. A pushed tag alone does not
create a Zenodo deposit. With the repository's Zenodo integration enabled, the
published GitHub Release triggers archiving. Check the resulting deposit,
author order, version and files before using its DOI.

The project concept DOI is `10.5281/zenodo.20263542`. It covers releases
collectively and does not identify the exact revision evaluated in the paper.
Use the release-specific DOI when citing a fixed version. Historical records
include `10.5281/zenodo.22435908` for v0.2.0 and
`10.5281/zenodo.20263543` for v0.1.0-softwarex.

When the new DOI exists, update the current branch's citation metadata and
paper. Do not rewrite the archived release just to add its newly minted DOI.
The current `CITATION.cff` lists only the concept DOI until an identifier for
this release is available; historical version identifiers belong to those
releases, not to the current source version.

## Paper synchronisation

Set metadata C1 to the evaluated version and C2 to its public immutable commit
or release link. Update the source archive hash, reproducibility record and
code-availability statement, then rebuild the paper and submission archives.
If any source files change, repeat the snapshot step. The manuscript's generic
repository URL and concept DOI alone do not pin the submitted code.

## Mirror configuration

The GitLab CI job needs protected, masked `GITHUB_USER` and `GITHUB_TOKEN`
variables with permission to write to the public repository. The GitHub
repository must already exist. Verify propagation with:

```bash
git ls-remote https://github.com/swillert/pulse-ep.git refs/heads/main refs/tags/v0.4.2
```

The documentation sources are public in `docs/`. The CI Pages job builds a
static site; this does not imply that a public hosted documentation URL is
configured or reachable.
