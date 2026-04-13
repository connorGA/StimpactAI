#!/usr/bin/env bash
set -euo pipefail

REPO_ROOT="/Users/connor/Desktop/StimpactAi"
cd "$REPO_ROOT"

echo "Bootstrapping repository at $REPO_ROOT"

echo "Environment notes:"
echo " - Node.js and npm are available locally."
echo " - Control-plane repo profile e7154231-4cec-4733-a39c-78fd2ad1dde2 is active for project scaletest-scaleproject."

# Install project dependencies as defined by the repository profile.
npm ci

echo "Suggested next commands:"
echo " - npm run build"
echo " - npm run check"
echo " - npm run dev"

echo "Bootstrap complete. Review the suggested commands above before running long-lived services."
