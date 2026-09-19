"""
Persist trading plans as JSON.

Windows: %APPDATA%/trading-risk-calculator/plans.json
Linux/macOS: ~/.trading-risk-calculator/plans.json

One plan per ticker (ticker key is uppercased).
"""

from __future__ import annotations

import json
import os
import sys
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional


APP_DIR_NAME = "trading-risk-calculator"
PLANS_FILENAME = "plans.json"


def default_data_dir() -> Path:
    """User-writable app data directory (platform-aware)."""
    if sys.platform == "win32":
        base = os.environ.get("APPDATA")
        if base:
            return Path(base) / APP_DIR_NAME
        return Path.home() / "AppData" / "Roaming" / APP_DIR_NAME
    return Path.home() / f".{APP_DIR_NAME}"


@dataclass
class ExitPlan:
    mode: str = "full"  # "full" | "partial"
    prices: List[float] = field(default_factory=list)
    pcts: List[float] = field(default_factory=list)  # fractions 0–1


@dataclass
class Plan:
    ticker: str
    side: str = "long"
    entries: List[float] = field(default_factory=list)
    stop: float = 0.0
    max_risk: float = 0.0
    target: Optional[float] = None
    weights: Optional[List[float]] = None  # fractions; None → soft defaults
    exit_plan: Optional[ExitPlan] = None
    gap_price: Optional[float] = None

    def to_dict(self) -> Dict[str, Any]:
        d = asdict(self)
        d["ticker"] = self.ticker.upper().strip()
        return d

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "Plan":
        ep = data.get("exit_plan")
        exit_plan = None
        if isinstance(ep, dict):
            exit_plan = ExitPlan(
                mode=ep.get("mode", "full"),
                prices=list(ep.get("prices") or []),
                pcts=list(ep.get("pcts") or []),
            )
        return cls(
            ticker=str(data.get("ticker", "")).upper().strip(),
            side=str(data.get("side", "long")).lower().strip(),
            entries=[float(x) for x in (data.get("entries") or [])],
            stop=float(data.get("stop") or 0),
            max_risk=float(data.get("max_risk") or 0),
            target=(
                float(data["target"])
                if data.get("target") not in (None, "")
                else None
            ),
            weights=(
                [float(x) for x in data["weights"]]
                if data.get("weights") is not None
                else None
            ),
            exit_plan=exit_plan,
            gap_price=(
                float(data["gap_price"])
                if data.get("gap_price") not in (None, "")
                else None
            ),
        )


class PlanStore:
    """Load / save plans keyed by ticker."""

    def __init__(self, data_dir: Optional[Path] = None) -> None:
        self.data_dir = Path(data_dir) if data_dir else default_data_dir()
        self.path = self.data_dir / PLANS_FILENAME
        self._plans: Dict[str, Plan] = {}
        self.load()

    def load(self) -> None:
        self._plans = {}
        if not self.path.exists():
            return
        try:
            raw = json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return
        if isinstance(raw, dict) and "plans" in raw:
            items = raw["plans"]
        elif isinstance(raw, list):
            items = raw
        elif isinstance(raw, dict):
            # ticker -> plan mapping
            items = list(raw.values())
        else:
            items = []
        for item in items:
            if not isinstance(item, dict):
                continue
            plan = Plan.from_dict(item)
            if plan.ticker:
                self._plans[plan.ticker] = plan

    def save(self) -> None:
        self.data_dir.mkdir(parents=True, exist_ok=True)
        payload = {
            "version": 1,
            "plans": [p.to_dict() for p in sorted(
                self._plans.values(), key=lambda p: p.ticker
            )],
        }
        tmp = self.path.with_suffix(".tmp")
        tmp.write_text(json.dumps(payload, indent=2), encoding="utf-8")
        tmp.replace(self.path)

    def list_tickers(self) -> List[str]:
        return sorted(self._plans.keys())

    def get(self, ticker: str) -> Optional[Plan]:
        return self._plans.get(ticker.upper().strip())

    def upsert(self, plan: Plan) -> None:
        key = plan.ticker.upper().strip()
        if not key:
            raise ValueError("Ticker is required to save a plan")
        plan.ticker = key
        self._plans[key] = plan
        self.save()

    def delete(self, ticker: str) -> bool:
        key = ticker.upper().strip()
        if key in self._plans:
            del self._plans[key]
            self.save()
            return True
        return False
