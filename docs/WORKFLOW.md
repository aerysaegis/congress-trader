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

## Known gap

Server-side branch protection needs GitHub Pro or a public repo, so `main` is
**not** protected on the server today. `.githooks/pre-push` blocks direct
pushes to `main` locally — enable it with `git config core.hooksPath .githooks`
— but it only protects clones that ran that command. Until the repo goes public
or gets Pro, the PR-only rule is a convention backed by a local seatbelt, not
something the server enforces.
