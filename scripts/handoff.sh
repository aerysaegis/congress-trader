#!/usr/bin/env bash
# Print a self-contained brief for an agent picking up a contract.
#
#   ./scripts/handoff.sh 03            # brief for contract 03
#   ./scripts/handoff.sh 03 | pbcopy   # paste straight into Codex
#
# The brief is deliberately standalone: an agent starting cold with no chat
# history should be able to act on it using only the repo.

set -euo pipefail
cd "$(dirname "$0")/.."

id="${1:-}"
if [ -z "$id" ]; then
  echo "usage: $0 <contract-id>   e.g. $0 03" >&2
  echo "available:" >&2
  ls docs/contracts/ | sed 's/^/  /' >&2
  exit 2
fi

contract=$(ls docs/contracts/ | grep "^${id}-" | head -1 || true)
if [ -z "$contract" ]; then
  echo "no contract matching '${id}' in docs/contracts/" >&2
  exit 2
fi

branch="codex/${contract%.md}"
repo=$(gh repo view --json nameWithOwner -q .nameWithOwner 2>/dev/null || echo "aerysaegis/congress-trader")

cat <<EOF
You are implementing contract ${id} in ${repo}.

Setup:
  git clone https://github.com/${repo}.git && cd congress-trader
  git checkout -b ${branch}
  python3 -m venv .venv && .venv/bin/pip install -e ".[dev]"
  git config core.hooksPath .githooks

Read these three files before writing any code:
  AGENTS.md                        - the rules, and which files you own
  docs/contracts/00-interfaces.md  - frozen types you consume, do not change
  docs/contracts/${contract}        - your task

Hard rules:
  - Implement ONLY the files your contract says it owns. If you need a change
    somewhere else, stop and say so in the PR instead of editing around it.
  - congress_trader/risk.py and tests/test_risk_invariants.py are protected.
  - Tests must not touch the network. Use sources.load("sample").
  - Paper is the default; --live requires --yes-really. Never change that gate.

Before you push:
  .venv/bin/python -m pytest
  .venv/bin/python -m ruff check .
  python3 -m congress_trader report --sample

Then open a PR against main referencing contract ${id}. Claude reviews it.
Do not merge your own PR.

--- contract ${contract} follows ---

EOF
cat "docs/contracts/${contract}"
