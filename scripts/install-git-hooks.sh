#!/bin/sh
set -eu
cd "$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)"
git rev-parse --is-inside-work-tree >/dev/null
git config --local core.hooksPath .githooks
echo "Installed repository Git hooks from .githooks/."
