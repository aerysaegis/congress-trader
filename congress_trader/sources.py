"""Data loaders. Each returns raw dicts; normalize.py turns them into Trades.

The free community S3 dumps are the default. If they go stale, write another
loader here that returns the same shape and register it in LOADERS, then point
`--source` at it. Nothing else in the codebase needs to change.
"""
from __future__ import annotations

import json
import time
import urllib.error
import urllib.request
from pathlib import Path

from .config import cache_path

HOUSE_URL = "https://house-stock-watcher-data.s3-us-west-2.amazonaws.com/data/all_transactions.json"
SENATE_URL = "https://senate-stock-watcher-data.s3-us-west-2.amazonaws.com/aggregate/all_transactions.json"

CACHE_TTL_SECONDS = 6 * 60 * 60
USER_AGENT = "congress-trader/0.1 (+https://github.com/aerysaegis/congress-trader)"


class SourceError(RuntimeError):
    """Raised when a feed is unreachable and no usable cache exists."""


def _fetch_json(url: str, cache_name: str, *, refresh: bool = False, timeout: int = 60) -> list[dict]:
    path = cache_path(cache_name)
    fresh = path.is_file() and (time.time() - path.stat().st_mtime) < CACHE_TTL_SECONDS
    if fresh and not refresh:
        return _read_cache(path)

    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            payload = resp.read()
    except (urllib.error.URLError, TimeoutError, OSError) as exc:
        if path.is_file():
            # Stale cache beats no data; the caller decides whether that matters.
            return _read_cache(path)
        raise SourceError(f"could not reach {url}: {exc}") from exc

    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_bytes(payload)
    tmp.replace(path)
    return _read_cache(path)


def _read_cache(path: Path) -> list[dict]:
    try:
        with path.open() as fh:
            data = json.load(fh)
    except (OSError, json.JSONDecodeError) as exc:
        raise SourceError(f"cache at {path} is unreadable: {exc}") from exc
    return data if isinstance(data, list) else []


def load_house(*, refresh: bool = False) -> list[dict]:
    rows = _fetch_json(HOUSE_URL, "house_transactions.json", refresh=refresh)
    for row in rows:
        row["_chamber"] = "house"
    return rows


def load_senate(*, refresh: bool = False) -> list[dict]:
    rows = _fetch_json(SENATE_URL, "senate_transactions.json", refresh=refresh)
    for row in rows:
        row["_chamber"] = "senate"
    return rows


def load_live(*, refresh: bool = False) -> list[dict]:
    """Both chambers. One failing chamber is survivable; both is not."""
    rows: list[dict] = []
    errors: list[str] = []
    for loader in (load_house, load_senate):
        try:
            rows.extend(loader(refresh=refresh))
        except SourceError as exc:
            errors.append(str(exc))
    if not rows:
        raise SourceError("; ".join(errors) or "no rows returned from any chamber")
    return rows


def load_sample(*, refresh: bool = False) -> list[dict]:
    """Bundled fixture so `report --sample` proves the pipeline offline."""
    from .sample_data import SAMPLE_ROWS

    return [dict(row) for row in SAMPLE_ROWS]


LOADERS = {"live": load_live, "house": load_house, "senate": load_senate, "sample": load_sample}


def load(source: str = "live", *, refresh: bool = False) -> list[dict]:
    try:
        loader = LOADERS[source]
    except KeyError:
        raise SourceError(f"unknown source {source!r}; choose from {sorted(LOADERS)}") from None
    return loader(refresh=refresh)
