from __future__ import annotations

import json
from dataclasses import replace
from datetime import date, datetime, timezone

from congress_trader.config import Reference
from congress_trader.normalize import normalize
from congress_trader.report import build, render_json, render_text
from congress_trader.sample_data import build_sample

ANCHOR = date(2025, 1, 31)
GENERATED = datetime(2025, 1, 31, 12, 0, tzinfo=timezone.utc)


def sample_report(*, parties: bool = True):
    loaded = Reference.load()
    reference = loaded if parties else Reference(sectors=loaded.sectors)
    universe = normalize(build_sample(anchor=ANCHOR), reference=reference)
    data = build(universe, reference=reference, asof=ANCHOR, source="sample")
    return replace(data, generated_at=GENERATED)


def test_text_contains_all_six_sections_in_order() -> None:
    rendered = render_text(sample_report(), top=5)
    headings = ["CONGRESS-TRADER", "TOP NAMES", "SECTOR ROTATION", "CONTESTED", "FILERS", "DROPPED"]

    offsets = [rendered.index(heading) for heading in headings]
    assert offsets == sorted(offsets)


def test_text_is_plain_ascii_and_honors_requested_width() -> None:
    rendered = render_text(sample_report(), top=5, width=80)

    assert rendered.isascii()
    assert max(map(len, rendered.splitlines())) <= 80


def test_json_round_trips_with_schema_v1_and_documented_keys() -> None:
    payload = json.loads(render_json(sample_report()))

    assert payload["schema_version"] == 1
    assert payload["generated_at"] == "2025-01-31T12:00:00+00:00"
    assert payload["asof"] == "2025-01-31"
    assert set(payload) == {
        "schema_version",
        "generated_at",
        "asof",
        "lookback",
        "min_members",
        "midpoint",
        "source",
        "has_parties",
        "n_trades_considered",
        "dropped",
        "signals",
        "sectors",
        "contested",
        "filers",
    }
    assert set(payload["signals"][0]) == {
        "ticker",
        "sector",
        "score",
        "components",
        "raw",
        "n_members",
        "n_buyers",
        "n_sellers",
        "net_dollars",
        "gross_dollars",
        "n_trades",
        "buyers",
        "sellers",
        "parties",
        "first_date",
        "last_date",
        "median_lag_days",
        "contested",
        "direction",
    }


def test_no_party_mode_is_visible_and_omits_component() -> None:
    data = sample_report(parties=False)
    payload = json.loads(render_json(data))

    assert "bipartisan component is off" in render_text(data).lower()
    assert all("bipartisan" not in item["components"] for item in payload["signals"])
