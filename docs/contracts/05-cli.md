# 05 — Command line interface

Owner: **Codex**. Branch: `codex/05-cli`. Owns exactly: `congress_trader/__main__.py`.
Consumes: 00, 02, 03, 04. Blocks: 07.

The README's three commands are the acceptance test. They must work verbatim.

```bash
python3 -m congress_trader report --sample      # works offline
python3 -m congress_trader report               # live data
python3 -m congress_trader run --dry-run        # orders it would place
```

## Flags

Shared: `--lookback INT` (default 60), `--min-members INT` (default 3),
`--min-dollars FLOAT` (default 1000), `--midpoint {geometric,arithmetic}`
(default geometric), `--source {live,house,senate,sample}` (default live),
`--sample` (alias for `--source sample`), `--refresh` (bypass the cache),
`--asof YYYY-MM-DD`.

`report`: `--top INT` (default 25), `--json`.

`run`: `--dry-run`, `--paper` (default), `--live`, `--yes-really`,
`--min-score FLOAT` (default 0.5), `--exit-score FLOAT` (default -0.5).

## Rules

- **`--live` without `--yes-really` exits non-zero with a clear message and
  places no orders.** This gate is not negotiable and is covered by a test.
  **The refusal message must contain the literal string `--yes-really`.** CI
  greps for it, because a non-zero exit on its own proves nothing -- an import
  error exits non-zero too, and a gate check that passes on an import error is
  worse than no check at all.
- `main(argv=None) -> int`. Return the exit code, don't call `sys.exit` from
  anywhere but the `if __name__ == "__main__"` guard, so tests can call it.
- Exit codes: `0` success, `1` runtime failure, `2` bad usage.
- `SourceError` prints a readable message suggesting `--sample`, and returns 1.
  Never dump a traceback at the user for an unreachable feed.
- `--json` writes only JSON to stdout — no banners, no progress text. Anything
  informational goes to stderr, so `report --json | jq` works.
- `run` prints the plan (including `skipped` with reasons) before submitting,
  in every mode.

## Done when

All three README commands work, `report --sample --json | python3 -m json.tool`
parses, and `run --live` without `--yes-really` returns non-zero having
submitted nothing.
