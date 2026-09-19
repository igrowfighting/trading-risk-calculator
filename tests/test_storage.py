"""Tests for plan persistence."""

from __future__ import annotations

from pathlib import Path

from trading_risk_calculator.storage import ExitPlan, Plan, PlanStore


def test_upsert_one_per_ticker(tmp_path: Path) -> None:
    store = PlanStore(data_dir=tmp_path)
    store.upsert(Plan(ticker="aapl", side="long", entries=[100], stop=95, max_risk=200))
    store.upsert(Plan(ticker="AAPL", side="short", entries=[90], stop=95, max_risk=150))
    assert store.list_tickers() == ["AAPL"]
    p = store.get("aapl")
    assert p is not None
    assert p.side == "short"
    assert p.max_risk == 150


def test_roundtrip(tmp_path: Path) -> None:
    store = PlanStore(data_dir=tmp_path)
    plan = Plan(
        ticker="TSLA",
        side="long",
        entries=[78.0, 76.0, 75.0],
        stop=74.0,
        max_risk=300.0,
        target=82.0,
        weights=[0.2, 0.3, 0.5],
        exit_plan=ExitPlan(mode="full", prices=[78.0], pcts=[1.0]),
        gap_price=70.0,
    )
    store.upsert(plan)
    store2 = PlanStore(data_dir=tmp_path)
    loaded = store2.get("TSLA")
    assert loaded is not None
    assert loaded.entries == [78.0, 76.0, 75.0]
    assert loaded.weights == [0.2, 0.3, 0.5]
    assert loaded.exit_plan is not None
    assert loaded.exit_plan.prices == [78.0]
    assert loaded.gap_price == 70.0


def test_delete(tmp_path: Path) -> None:
    store = PlanStore(data_dir=tmp_path)
    store.upsert(Plan(ticker="MSFT", entries=[1], stop=0.5, max_risk=10))
    assert store.delete("MSFT")
    assert store.get("MSFT") is None
