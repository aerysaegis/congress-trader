"""Paths, reference maps, and knobs. Everything optional degrades quietly."""
from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from pathlib import Path

# Repo root when running from a checkout; cwd otherwise.
ROOT = Path(os.environ.get("CONGRESS_TRADER_ROOT", Path.cwd()))
CACHE_DIR = Path(os.environ.get("CONGRESS_TRADER_CACHE", ROOT / ".cache"))
REFERENCE_DIR = Path(os.environ.get("CONGRESS_TRADER_REFERENCE", ROOT / "reference"))

UNMAPPED = "Unmapped"


def _load_map(name: str) -> dict:
    """Load a reference JSON from reference/ or the repo root. Missing is fine."""
    for candidate in (REFERENCE_DIR / name, ROOT / name):
        if candidate.is_file():
            try:
                with candidate.open() as fh:
                    data = json.load(fh)
            except (OSError, json.JSONDecodeError):
                return {}
            return data if isinstance(data, dict) else {}
    return {}


@dataclass(slots=True)
class Reference:
    """The three tuning maps. Anything unmapped buckets rather than drops."""

    sectors: dict[str, str] = field(default_factory=dict)
    parties: dict[str, str] = field(default_factory=dict)
    member_weights: dict[str, float] = field(default_factory=dict)

    @classmethod
    def load(cls) -> Reference:
        raw_weights = _load_map("member_weights.json")
        weights: dict[str, float] = {}
        for member, value in raw_weights.items():
            try:
                weights[_norm(member)] = float(value)
            except (TypeError, ValueError):
                continue
        return cls(
            sectors={str(k).upper().strip(): str(v) for k, v in _load_map("sectors.json").items()},
            parties={_norm(k): str(v).upper().strip()[:1] for k, v in _load_map("parties.json").items()},
            member_weights=weights,
        )

    @property
    def has_parties(self) -> bool:
        """The bipartisan signal is silently off without a parties map."""
        return bool(self.parties)

    def sector_of(self, ticker: str) -> str:
        return self.sectors.get(ticker.upper().strip(), UNMAPPED)

    def party_of(self, member: str) -> str | None:
        return self.parties.get(_norm(member))

    def weight_of(self, member: str) -> float:
        return self.member_weights.get(_norm(member), 1.0)


def _norm(name: str) -> str:
    """Loose name key: case- and punctuation-insensitive, order-preserving."""
    cleaned = "".join(ch.lower() if (ch.isalnum() or ch.isspace()) else " " for ch in str(name))
    return " ".join(cleaned.split())


def cache_path(name: str) -> Path:
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    return CACHE_DIR / name
