#!/usr/bin/env bash
# Bootstraps the local git repo and pushes the initial commit to GitLab.
# Run this ONCE from your terminal (the Claude sandbox cannot push for permission reasons).
#
#   chmod +x bootstrap-git.sh && ./bootstrap-git.sh
#
# After this you can safely delete this script — it's only the first-push helper.

set -euo pipefail
cd "$(dirname "$0")"

REPO_NAME="pulse-ep"
REMOTE_SSH="ssh://git@gitlab.willert.net:2222/sw/${REPO_NAME}.git"
REMOTE_HTTP="https://gitlab.willert.net/sw/${REPO_NAME}.git"

echo "==> Wiping any half-initialized .git from the agent session"
rm -rf .git

echo "==> git init -b main"
git init -b main
git config user.name  "Sven Willert"
git config user.email "sw@willert.net"

echo "==> git add -A"
git add -A

echo "==> initial commit"
git commit -m "Initial commit: pulse-ep project skeleton

- src/ layout with pulse_ep.{core, cli, figures, server} packages
- pyproject.toml: modern setuptools build, optional extras (server, figures, dev, all)
- LICENSE (MIT), CITATION.cff (Willert, Lian, Frank; SoftwareX target)
- STRATEGY.md: pulse-ultimate -> pulse-ep + pulse-ep-decay split rationale
- .gitignore: Python, IDE, data, analysis outputs

Note: decay/sigma/heat-method code currently in pulse_ep/cli will move to
the pulse-ep-decay extension in a follow-up commit; demo module, README,
tests, docs and CI still to come per STRATEGY.md."

echo "==> adding remote origin (SSH)"
git remote add origin "${REMOTE_SSH}" || git remote set-url origin "${REMOTE_SSH}"

echo "==> push -u origin main"
if ! git push -u origin main; then
  echo "SSH push failed — falling back to HTTPS"
  git remote set-url origin "${REMOTE_HTTP}"
  git push -u origin main
fi

echo
echo "==> Done. Repo synced with ${REMOTE_HTTP}"
echo "You can now delete this bootstrap script if you like."
