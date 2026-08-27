from __future__ import annotations

import json
from datetime import date

from congress_trader.__main__ import main
from congress_trader.broker import Account
from congress_trader.sample_data import build_sample

ANCHOR = date(2025, 1, 31)


def fixed_loader(monkeypatch, *, require_sample: bool = False):
    calls = []

    def load(source="live", *, refresh=False):
        calls.append((source, refresh))
        if require_sample and source != "sample":
            raise AssertionError(f"offline command requested {source!r}")
        return build_sample(anchor=ANCHOR)

    monkeypatch.setattr("congress_trader.__main__.sources.load", load)
    return calls


def test_readme_report_sample_command(monkeypatch, capsys) -> None:
    calls = fixed_loader(monkeypatch)

    assert main(["report", "--sample", "--asof", ANCHOR.isoformat(), "--top", "2"]) == 0

    output = capsys.readouterr()
    assert "TOP NAMES" in output.out
    assert calls == [("sample", False)]


def test_json_stdout_contains_only_json(monkeypatch, capsys) -> None:
    fixed_loader(monkeypatch)

    assert main(["report", "--sample", "--asof", ANCHOR.isoformat(), "--json"]) == 0

    output = capsys.readouterr()
    assert json.loads(output.out)["schema_version"] == 1
    assert output.err == ""


def test_readme_dry_run_is_offline_without_extra_flags(monkeypatch, capsys) -> None:
    calls = fixed_loader(monkeypatch, require_sample=True)

    assert main(["run", "--dry-run", "--asof", ANCHOR.isoformat()]) == 0

    output = capsys.readouterr()
    assert "ENTRIES" in output.out
    assert "nothing was submitted" in output.err
    assert calls == [("sample", False)]


def test_live_without_confirmation_stops_before_data_or_broker(monkeypatch, capsys) -> None:
    def forbidden(*args, **kwargs):
        raise AssertionError("live gate allowed a side effect")

    monkeypatch.setattr("congress_trader.__main__.sources.load", forbidden)
    monkeypatch.setattr("congress_trader.__main__.get_broker", forbidden)

    assert main(["run", "--live", "--sample"]) != 0

    output = capsys.readouterr()
    assert "--yes-really" in output.err
    assert "No orders were placed" in output.err


def test_invalid_asof_returns_bad_usage_code(monkeypatch) -> None:
    fixed_loader(monkeypatch)

    assert main(["report", "--sample", "--asof", "not-a-date"]) == 2


def test_empty_signal_set_still_builds_exits(monkeypatch, capsys) -> None:
    fixed_loader(monkeypatch)

    class HeldBroker:
        def account(self):
            return Account(equity=10_000.0, cash=5_000.0, buying_power=5_000.0, is_paper=True)

        def positions(self):
            return {"OLD": 500.0}

        def submit(self, order):
            raise AssertionError("dry run submitted an order")

    monkeypatch.setattr("congress_trader.__main__.get_broker", lambda **kwargs: HeldBroker())

    assert main(
        ["run", "--dry-run", "--sample", "--asof", ANCHOR.isoformat(), "--min-members", "999"]
    ) == 0

    output = capsys.readouterr()
    assert "SELL OLD" in output.out


def test_plan_is_printed_before_any_submission(monkeypatch, capsys) -> None:
    fixed_loader(monkeypatch)
    output_seen_at_submit = []

    class PaperBroker:
        def account(self):
            return Account(equity=25_000.0, cash=10_000.0, buying_power=10_000.0, is_paper=True)

        def positions(self):
            return {}

        def submit(self, order):
            output_seen_at_submit.append(capsys.readouterr().out)
            return f"paper-{order.symbol}"

    monkeypatch.setattr("congress_trader.__main__.get_broker", lambda **kwargs: PaperBroker())

    assert main(["run", "--paper", "--sample", "--asof", ANCHOR.isoformat()]) == 0

    assert output_seen_at_submit
    assert all(section in output_seen_at_submit[0] for section in ("EXITS", "ENTRIES", "SKIPPED"))


def test_source_error_is_readable_and_suggests_sample(monkeypatch, capsys) -> None:
    from congress_trader.sources import SourceError

    monkeypatch.setattr(
        "congress_trader.__main__.sources.load",
        lambda *args, **kwargs: (_ for _ in ()).throw(SourceError("feed unreachable")),
    )

    assert main(["report"]) == 1

    output = capsys.readouterr()
    assert "feed unreachable" in output.err
    assert "--sample" in output.err
