# Agent operating manual

> `CLAUDE.md` and `AGENTS.md` are kept identical so both agents read the
> same rules. Edit `AGENTS.md` and copy it across.

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
| `signals.py`, `risk.py`, `models.py`, `config.py`, `normalize.py`, `sources.py` | Claude | Cross-file invariants and judgment calls where the spec is ambiguous |
| `report.py`, `analytics.py` | Codex | Well-specified rendering against frozen types |
| `strategy.py`, `broker.py` | Codex | Mechanical, heavily spec'd, and fully covered by invariant tests |
| `__main__.py` / CLI | Codex | Flag plumbing with an exact documented surface |
| `tests/` (except risk invariants) | Codex | High-volume case generation |
| `macapp/` (SwiftUI) | Codex | Language breadth |
| Contracts, reviews, merges | Claude | Keeping the pieces coherent |

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

## Talking to each other

Issues and PRs are the **record**: durable, reviewed, slow. `scripts/agent_msg.py`
is the **channel**: structured messages and work claims on the `agent-comms`
branch, which carries no code and needs no review, so a question costs a second
instead of a pull request.

```bash
export AGENT_NAME=codex            # or claude

./scripts/agent_msg.py status                      # who is on what, what's unanswered
./scripts/agent_msg.py claim C03 --branch codex/03-strategy
./scripts/agent_msg.py send --to claude --re C03 --type blocker \
    --subject "clamp_order returns 0 for every entry" --body "..."
./scripts/agent_msg.py inbox --for codex
./scripts/agent_msg.py reply <id> --body "..."
./scripts/agent_msg.py resolve <thread>
./scripts/agent_msg.py release C03
```

**Claim a contract before you write a line of it.** The claim is what stops two
agents building the same file and one silently overwriting the other. Claims go
stale after 12 hours and can then be taken over.

**Run `status` at the start of every session.** It is the one command that tells
you what changed while you were gone.

Message types carry meaning, so use the right one:

| Type | Use it when |
|---|---|
| `blocker` | You cannot proceed. The other agent should treat this as interrupting. |
| `interface-change` | Your contract can't be built without changing a frozen interface. **Never edit around it** — send this and wait. |
| `question` | You can proceed on an assumption, but want it checked. Say what you assumed. |
| `handoff` | You finished something the other agent is waiting on. |
| `review` | You want a second reader on specific reasoning, not just a green build. |
| `fyi` | No response needed. |

Add `--notify` to mirror a message onto the linked GitHub issue when it needs to
be part of the permanent record too.

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
