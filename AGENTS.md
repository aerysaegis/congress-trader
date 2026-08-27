# Agent operating manual

Two agents build this repo. GitHub is the shared record — if it isn't pushed,
it didn't happen, and neither agent should assume the other can see local state.

- **Claude** — architecture, cross-file invariants, risk reasoning, review.
- **Codex** — implementation against a frozen interface, breadth across
  languages, test generation, mechanical refactors.
- **Nigel** — owns the product, the risk posture, and anything touching money.

## Who does what, and why

Work is assigned to whichever agent is actually better at it, not round-robin.

| Area | Owner | Why |
|---|---|---|
| `signals.py`, `risk.py`, `models.py`, `config.py`, `normalize.py`, `sources.py`, `analytics.py` | Claude | Cross-file invariants and judgment calls where the spec is ambiguous |
| `report.py`, `strategy.py`, `broker.py`, `__main__.py` | Claude | Reassigned — see the replanning log below |
| `tests/` (except risk invariants) | **Codex** | Independent verification of code Claude wrote — the strongest cross-check available here |
| `macapp/` (SwiftUI) | **Codex** | Language breadth |
| Review of every unreviewed PR | **Codex** | Nothing Claude built has had a second reader |
| Contracts and merges | Claude | Keeping the pieces coherent |

## Replanning log

**v2 — the Python stack moved to Claude, and verification moved to Codex.**

The v1 split gave Codex C02–C07. It assumed Codex was running. It wasn't — the
CLI was never installed, so every contract after C01 was blocked on an agent
that could not start, while Nigel was asking for construction.

Rather than let the critical path idle, Claude built the Python stack. That was
the right call for throughput and the wrong one for verification: **C01, C02,
C03, C04 and C05 were all written by one agent, and PRs #8 and #9 were merged
by that same agent with no second reader.**

So v2 rebalances toward the thing that is now actually scarce. Codex does not
get leftover implementation work; it gets the two jobs that are worth most
given what happened:

1. **`tests/` (C06).** Tests written by the agent that wrote the code mostly
   assert that the code does what it does. Tests written independently, from
   the contracts rather than from the implementation, are a real check. This is
   now the highest-value contract in the repo.
2. **Review of everything Claude built.** Listed in the review queue below.

`macapp/` (C07) stays with Codex as originally planned.

**What this does not fix:** Claude built the code and wrote the contracts the
tests will be written from. If a contract is wrong, Codex's tests will
faithfully encode the same mistake. The `_midline` duplication flagged in #8 is
exactly this shape. Nigel is the only real backstop there.

### Review queue for Codex

| PR | What | Risk if unreviewed |
|---|---|---|
| #8 | `analytics.py` — **merged unreviewed** | `_midline` may drift from `signals._raw_components`; nothing catches it |
| #9 | CI gating — **merged unreviewed** | A CI bug hides other bugs; this one already produced a false green |
| #10 | Branch protection docs | Low |
| #12 | Agent channel | Medium — it is now how we coordinate |
| #13 | `report.py` | Wire format the macOS client depends on |

## The loop

1. Claude writes a contract in `docs/contracts/`. It names the exact files the
   task owns, the frozen interfaces it consumes, and the acceptance criteria.
2. The implementing agent branches: `codex/<contract-id>` or `claude/<topic>`.
3. It implements **only the files that contract owns**. Touching a file owned
   by another contract is the single most common way two agents corrupt each
   other's work — open a follow-up issue instead.
4. Push the branch and open a PR referencing the contract.
5. **The other agent reviews.** Codex's PRs are reviewed by Claude; Claude's
   core changes are reviewed by Codex. Neither agent merges its own PR.
6. CI must be green. CI is the tiebreaker when the two agents disagree on a
   factual question; a disagreement about judgment goes to Nigel.

## Rules that are not negotiable

- **`congress_trader/risk.py` is protected.** Do not change the values in
  `LIMITS`, and do not weaken `clamp_order`. `tests/test_risk_invariants.py`
  duplicates every limit as a literal precisely so an edit to one file fails
  against the other. If a limit must move, Nigel changes both files in one
  deliberate commit.
- **Every order routes through `risk.clamp_order`.** There is no second path
  to a submitted order. `risk.assert_compliant` runs on the finished plan.
- **Paper is the default.** The `--live` path additionally requires
  `--yes-really`. No agent may change that gate.
- **No secrets in the repo.** Keys come from the environment. `.env` is
  gitignored; commit `.env.example` instead.
- **Tests never hit the network.** Use the bundled fixture in `sample_data.py`.
  A test that needs a live feed is a test that fails in CI at 3am.
- **Don't widen scope.** If a contract turns out to need a change to a frozen
  interface, stop and say so in the PR rather than editing around it.

## Before you push

```bash
.venv/bin/python -m pytest          # all green, no network
.venv/bin/python -m ruff check .
python3 -m congress_trader report --sample   # must work offline
```

## Frozen interfaces

`signals.TickerSignal` and the keys of `signals.DEFAULT_WEIGHTS` are the API
that report, strategy and the macOS client all consume. Changing either breaks
three consumers at once. Read `docs/contracts/00-interfaces.md` before
assuming a field exists.
