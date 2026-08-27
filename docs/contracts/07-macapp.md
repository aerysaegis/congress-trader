# 07 — SwiftUI macOS client

Owner: **Codex**. Branch: `codex/07-macapp`. Owns exactly: `macapp/`.
Consumes: the JSON schema in contract 02. Depends on 05 shipping first.

A native Mac front end over the Python engine. The engine stays the source of
truth — the app shells out and renders, it does not reimplement scoring.

## Shape

- SwiftUI, macOS 13+, Swift 6. Build with SwiftPM (`swift build`) so CI can
  compile it headlessly; an Xcode project is optional and secondary.
- `CongressTraderApp` — window with a sidebar (Top Names / Sectors / Contested
  / Filers) and a detail pane.
- `EngineClient` — runs `python3 -m congress_trader report --json …` as a
  subprocess, decodes into `Codable` structs, surfaces stderr as a readable
  error. Async, never blocks the main actor.
- `Report` models mirroring the contract-02 schema exactly. **Pin
  `schema_version == 1`** and show a clear "engine is newer than this app"
  message on mismatch rather than silently decoding garbage.

## UI requirements

- Top Names as a sortable `Table` — ticker, score, members, buyers/sellers,
  net $, sector, median lag. Selecting a row shows the component breakdown and
  the member list in the detail pane.
- Controls for lookback, min-members, midpoint, and source, wired to re-run
  the engine.
- Sector rotation with a simple momentum bar. No charting dependency — draw it
  with SwiftUI shapes.
- Light and dark both legible. Score colouring must not be the *only* signal
  of direction; pair it with a sign or glyph.
- Empty and error states are real states, not a blank window.

## Rules

- No third-party packages. Foundation + SwiftUI only.
- The app never places orders. Analysis surface only in this contract; trading
  stays on the CLI where the `--yes-really` gate lives.
- Do not shell out to a hardcoded `/usr/bin/python3` — resolve the interpreter,
  and let the user point at one in settings.

## Done when

`swift build` succeeds, the app launches, and Top Names populates from
`report --sample --json` with no network.
