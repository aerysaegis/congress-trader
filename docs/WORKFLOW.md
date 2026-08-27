# Workflow

GitHub is the shared record. Neither agent can see the other's local state, so
anything not pushed does not exist as far as the other agent is concerned.

## Where work lives

| Thing | Where |
|---|---|
| Task briefs | `docs/contracts/` |
| Tracked work | [Issues](https://github.com/aerysaegis/congress-trader/issues), one per contract |
| Frozen interfaces | `docs/contracts/00-interfaces.md` |
| The rules | `AGENTS.md` (mirrored to `CLAUDE.md`) |
| Cross-check | CI on every PR |

## Handing a contract to Codex

```bash
./scripts/handoff.sh 03 | pbcopy
```

That prints a standalone brief — clone, branch, rules, and the full contract —
so Codex can start cold without any chat history. Paste it into Codex.

If the Codex CLI isn't installed:

```bash
npm install -g @openai/codex
```

## Branch names

`codex/<contract-id>-<slug>` and `claude/<topic>`. One contract per branch.

## Review

Neither agent merges its own PR. Codex's work is reviewed by Claude; Claude's
core changes are reviewed by Codex. CI decides factual disputes — a test either
passes or it doesn't. Judgment calls go to Nigel.

Review checklist:

1. Did the PR touch only the files its contract owns?
2. Did any frozen interface change?
3. Is `risk.py` untouched, and does `test_risk_invariants.py` still pass?
4. Do the tests actually exercise behaviour, or just assert the code it wrote?
5. Does `report --sample` still work offline?

## What the server enforces

`main` is protected. This is not a convention any more:

- Pull requests are required. No direct pushes, including by agents.
- One approving review, and **CODEOWNERS review is required** — so `risk.py`,
  `signals.py`, `tests/test_risk_invariants.py` and `AGENTS.md` cannot change
  without Nigel on the review.
- Five status checks must pass: `offline`, `live-gate`, `secrets`, and both
  Python versions. Branches must be up to date with `main` before merging.
- Force pushes and branch deletion are blocked.

`enforce_admins` is deliberately off so Nigel is never locked out of his own
repo. Agents have no admin, so the rules bind them fully.

`.githooks/pre-push` is still worth enabling as a fast local failure — it tells
you before you push rather than after — but it is no longer what's holding the
line.

## Historical exception

PRs #8 and #9 were self-merged by Claude with Nigel's explicit approval, before
protection was enabled. Both are recorded as exceptions in their PR comments.
Neither has been read by a second party. Worth a retrospective review once
Codex is running — particularly #8, which merged without unit tests.
