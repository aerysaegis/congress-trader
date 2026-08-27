# 06 — Test suite

Owner: **Codex**. Branch: `codex/06-tests`. Owns exactly: `tests/` **except**
`tests/test_risk_invariants.py`, which is protected and already written.
Consumes: everything.

## Rules

- **No network, ever.** Use `sources.load("sample")` or `build_sample(anchor=...)`
  with a fixed anchor date for determinism. A test that reaches the internet
  fails in CI at 3am and teaches the team to ignore red builds.
- Pass an explicit `anchor`/`asof` everywhere. Nothing may depend on today.
- Test behaviour, not implementation. Assert that the whale is excluded by the
  members floor; don't assert the internal call sequence that excludes it.

## Coverage required

- `test_normalize.py` — every drop rule fires; amount parsing across all bucket
  shapes including open-ended `Over $50,000,000` and `$1,000,001 - $5,000,000`;
  honorific stripping; the two date formats; `Sale (Full)` / `Sale (Partial)`.
- `test_signals.py` — geometric vs arithmetic midpoint; that breadth counts
  people so one whale can't rank a name; that a tight cluster outscores the
  same members spread across the window; that `bipartisan` is absent from
  `components` when no parties map is loaded; that `min_members` gates.
- `test_analytics.py` — ordering rules from contract 01; `Unmapped` bucketing.
- `test_report.py` — all six text sections present; JSON round-trips and
  carries every documented key; `schema_version` is 1.
- `test_strategy.py` — each cap binds independently; 16th position refused;
  exits precede entries; sizing monotonic in score but clamped at both ends.
- `test_broker.py` — module imports with alpaca-py absent; `DryRunBroker`
  needs no credentials; live construction refuses without the gate.
- `test_cli.py` — the three README commands; `--live` without `--yes-really`
  returns non-zero and submits nothing; `--json` emits JSON on stdout only.

## Done when

`pytest` is green with no network access and completes in under 30 seconds.
