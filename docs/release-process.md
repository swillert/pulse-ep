# Release process

`pulse-ep` lives on the self-hosted [GitLab](https://gitlab.willert.net/sw/pulse-ep)
as its canonical home, with a public mirror on
[GitHub](https://github.com/swillert/pulse-ep) for citation, Zenodo
DOIs, and discoverability. This page documents the end-to-end
release workflow.

## Architecture

```
gitlab.willert.net/sw/pulse-ep   ← canonical, every push lands here
            │
            │ GitLab CI: mirror_to_github (deploy stage)
            ▼
github.com/swillert/pulse-ep     ← public mirror, every push & tag
            │
            │ Manual: GitHub Release from tag
            ▼
Zenodo: pulse-ep                 ← citable DOI per release
```

A single `git push --tags origin main` from your local machine
therefore triggers the entire chain.

## One-time setup

You only need to do this once, at the time the GitHub mirror is
created.

### 1. Create the GitHub repository

- Sign in to [github.com](https://github.com) as `swillert`.
- Create a new **empty, public** repository named `pulse-ep`.
- **Important**: do *not* initialise it with a README, `.gitignore`,
  or LICENSE; otherwise the first force-push from GitLab will
  conflict.
- Set the description to something like:
  *"Open-source platform for programmatic access to CARTO
  electroanatomical mapping data — public mirror of
  gitlab.willert.net/sw/pulse-ep."*

### 2. Generate a Personal Access Token

- Go to
  [github.com/settings/tokens](https://github.com/settings/tokens)
  → *Generate new token (classic)*.
- Scope: `repo` (full control of private and public repositories).
- Copy the token immediately; GitHub will not show it again.

### 3. Store the token in GitLab

- In GitLab go to **Settings → CI/CD → Variables** for the
  `pulse-ep` project.
- Add two variables — both **Protected** and **Masked**:

  | Key            | Value                          |
  |----------------|--------------------------------|
  | `GITHUB_USER`  | `swillert`                     |
  | `GITHUB_TOKEN` | the token from step 2          |

### 4. Connect Zenodo to GitHub

- Sign in to [zenodo.org](https://zenodo.org) (link with GitHub
  on first use).
- Go to
  [zenodo.org/account/settings/github/](https://zenodo.org/account/settings/github/).
- Find `swillert/pulse-ep` in the repository list and flip the
  toggle to **On**.
- From now on, every GitHub *release* will automatically produce a
  Zenodo deposit with a citable DOI.

## Cutting a release

For each tagged release (e.g.\ `v0.1.0`, `v0.1.0-softwarex`):

### 1. Tag on GitLab

```bash
# In your local clone of gitlab.willert.net/sw/pulse-ep
git checkout main
git pull
git tag -a v0.1.0 -m "v0.1.0 — initial open-source release"
git push origin main --tags
```

GitLab CI will run, and the `mirror_to_github` job in the `deploy`
stage will force-push the branch and tags to
`github.com/swillert/pulse-ep`. You can watch it under **CI/CD →
Pipelines** in GitLab.

### 2. Create the matching GitHub Release

The Zenodo integration only fires on GitHub *releases* — not bare
tags. So after the mirror push:

- Open
  [github.com/swillert/pulse-ep/releases/new](https://github.com/swillert/pulse-ep/releases/new).
- Pick the tag you just pushed (e.g.\ `v0.1.0`).
- Title: the same string.
- Description: short release notes — link to the changelog entry
  is enough.
- Click **Publish release**.

### 3. Grab the Zenodo DOI

- Within ~1 minute Zenodo deposits the release. Watch the progress
  at
  [zenodo.org/account/settings/github/](https://zenodo.org/account/settings/github/)
  (each linked repo shows its latest deposit and DOI).
- Copy the DOI (looks like `10.5281/zenodo.NNNNNNN`).

### 4. Update `CITATION.cff` and any paper drafts

```yaml
# CITATION.cff
identifiers:
  - description: "Zenodo DOI for this release"
    type: doi
    value: "10.5281/zenodo.NNNNNNN"
```

For the SoftwareX manuscript, replace the placeholder
`XXXXXXX` in `paper.tex` (Code & Data Availability section,
Code Metadata Table row C3) with the real Zenodo record.

## Verifying the mirror

After the first run, sanity-check that GitHub really got the
content:

```bash
git ls-remote https://github.com/swillert/pulse-ep.git | head
```

You should see your `HEAD`, `refs/heads/main` and any tags. If you
see nothing, the most likely cause is one of the CI-variable steps
above being skipped; check the `mirror_to_github` job log in
GitLab.

## Limitations

- The mirror is force-pushed, so it tracks the GitLab state. **Do
  not commit directly on GitHub** — your changes will be wiped on
  the next mirror run.
- Issues, MRs, and CI badges live on GitLab; the GitHub mirror is
  intentionally read-only.
- Zenodo only versions GitHub *releases*; pre-release tags pushed
  but not turned into releases will be on GitHub but not on Zenodo.
