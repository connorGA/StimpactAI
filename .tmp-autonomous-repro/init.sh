#!/usr/bin/env bash
set -euo pipefail

REPO_ROOT="/Users/connor/Desktop/StimpactAi/.tmp-autonomous-repro"
cd "$REPO_ROOT"

echo "Bootstrapping repository at $REPO_ROOT"

echo "Environment notes:"
echo " - Python 3.12+ is available locally."
echo " - Control-plane repo profile profile-1 is active for project project-1."

# Install project dependencies as defined by the repository profile.
pip install -r requirements.txt

echo "Suggested next commands:"
echo " - pytest tests/test_billing.py::test_timeout_fixed"
echo " - python app.py"
echo " - Browser verify: repo-profile-default -> http://127.0.0.1:3000"

echo "Bootstrap complete. Review the suggested commands above before running long-lived services."
