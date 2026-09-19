"""
Pure position-sizing and risk math.

Whole shares only. Never exceed the max risk cap.
Supports long/short, single or multi-level (scale-in) entries,
optional targets / partial exits, and gap-through loss preview.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import List, Optional, Sequence, Tuple


class SizingError(ValueError):
    """Invalid sizing inputs (prices, weights, side, etc.)."""


def validate_entry_vs_stop(side: str, entry: float, stop: float) -> Optional[str]:
    """
    Return a warning/error message if entry is invalid vs stop, else None.
    Long: entry must be > stop. Short: entry must be < stop.
    """
    side = side.lower().strip()
    if side not in ("long", "short"):
        return f"Invalid side: {side!r} (expected 'long' or 'short')"
    if entry <= 0 or stop <= 0:
        return "Entry and stop prices must be positive"
    if side == "long" and entry <= stop:
        return f"Long entry ({entry}) must be above stop ({stop})"
    if side == "short" and entry >= stop:
        return f"Short entry ({entry}) must be below stop ({stop})"
    return None


def risk_per_share(side: str, entry: float, stop: float) -> float:
    """Absolute $ risk per share from entry to stop."""
    side = side.lower().strip()
    err = validate_entry_vs_stop(side, entry, stop)
    if err:
        raise SizingError(err)
    return abs(entry - stop)


def soft_weights_near_stop(n: int) -> List[float]:
    """
    Default soft weights that put more size nearer the stop.

    For N levels ordered farthest→nearest to stop:
      N=1 → [1.0]
      N=2 → [0.40, 0.60]
      N=3 → [0.20, 0.30, 0.50]
      N>3 → linearly increasing, normalized to sum 1.0
            (smallest weight on farthest, largest on nearest)
    """
    if n < 1:
        raise SizingError("Need at least one entry level")
    if n == 1:
        return [1.0]
    if n == 2:
        return [0.40, 0.60]
    if n == 3:
        return [0.20, 0.30, 0.50]
    # Linear ramp 1..N, normalized
    raw = [float(i) for i in range(1, n + 1)]
    total = sum(raw)
    return [x / total for x in raw]


def normalize_weights(weights: Sequence[float]) -> List[float]:
    """Normalize weights to sum to 1.0. Raises if empty or all zero/negative."""
    if not weights:
        raise SizingError("Weights list is empty")
    cleaned = [float(w) for w in weights]
    if any(w < 0 for w in cleaned):
        raise SizingError("Weights cannot be negative")
    total = sum(cleaned)
    if total <= 0:
        raise SizingError("Weights must sum to a positive value")
    return [w / total for w in cleaned]


def max_shares_for_risk(risk_budget: float, rps: float) -> int:
    """Largest whole-share count whose total risk ≤ risk_budget."""
    if risk_budget < 0:
        raise SizingError("Risk budget cannot be negative")
    if rps <= 0:
        raise SizingError("Risk per share must be positive")
    if risk_budget == 0:
        return 0
    return int(risk_budget // rps)  # floor — never over


@dataclass
class LevelResult:
    """One scale-in level after sizing."""

    entry: float
    weight: float  # fraction of total shares intent (0–1)
    shares: int
    risk_per_share: float
    tranche_risk: float


@dataclass
class SizeResult:
    """Full sizing result for single or multi-level plans."""

    side: str
    stop: float
    max_risk: float
    levels: List[LevelResult] = field(default_factory=list)
    total_shares: int = 0
    total_risk_used: float = 0.0
    avg_cost: float = 0.0
    warnings: List[str] = field(default_factory=list)

    @property
    def risk_remaining(self) -> float:
        return max(0.0, self.max_risk - self.total_risk_used)


def size_single(
    side: str,
    entry: float,
    stop: float,
    max_risk: float,
) -> SizeResult:
    """Size a single-entry position (whole shares, never over risk)."""
    return size_levels(side, [entry], stop, max_risk, weights=[1.0])


def size_levels(
    side: str,
    entries: Sequence[float],
    stop: float,
    max_risk: float,
    weights: Optional[Sequence[float]] = None,
) -> SizeResult:
    """
    Size a multi-level (scale-in) plan.

    ``entries`` should be ordered farthest→nearest to the stop for soft
    default weights to make sense (caller may pass any order + custom weights).

    Combined risk is locked to ``max_risk``. Shares are allocated by weight,
    then greedily adjusted so total $ risk never exceeds the cap.
    """
    side = side.lower().strip()
    if side not in ("long", "short"):
        raise SizingError(f"Invalid side: {side!r}")
    if max_risk < 0:
        raise SizingError("Max risk cannot be negative")
    if not entries:
        raise SizingError("At least one entry price is required")

    warnings: List[str] = []
    for i, e in enumerate(entries):
        msg = validate_entry_vs_stop(side, float(e), float(stop))
        if msg:
            warnings.append(f"Level {i + 1}: {msg}")

    if any(warnings):
        # Still allow computing if somehow called; but typically UI blocks.
        # If invalid, risk math is undefined — raise.
        raise SizingError("; ".join(warnings))

    n = len(entries)
    if weights is None:
        w = soft_weights_near_stop(n)
    else:
        if len(weights) != n:
            raise SizingError(
                f"Weight count ({len(weights)}) must match entry count ({n})"
            )
        w = normalize_weights(weights)

    rps_list = [risk_per_share(side, float(e), float(stop)) for e in entries]

    # Weighted average risk-per-share for initial total-share estimate
    # total_risk ≈ shares_total * sum(w_i * rps_i)
    blended_rps = sum(wi * ri for wi, ri in zip(w, rps_list))
    if blended_rps <= 0:
        raise SizingError("Blended risk per share must be positive")

    # Initial total shares from blended RPS, then distribute by weight
    total_cap_shares = max_shares_for_risk(max_risk, blended_rps)

    # Distribute by weight (floor), then assign leftover shares to
    # nearest-to-stop levels (highest weight / last indices) greedily
    # without exceeding remaining risk budget.
    raw_shares = [int(total_cap_shares * wi) for wi in w]
    # Fix rounding: give remainder preference to higher-weight (nearer) levels
    assigned = sum(raw_shares)
    remainder = total_cap_shares - assigned
    # Order indices by weight descending (nearer stop first for soft defaults)
    order = sorted(range(n), key=lambda i: w[i], reverse=True)
    for idx in order:
        if remainder <= 0:
            break
        raw_shares[idx] += 1
        remainder -= 1

    # Enforce hard risk cap: compute actual risk; if over, strip shares
    # from farthest levels first (lowest weight).
    def total_risk(shares: List[int]) -> float:
        return sum(s * r for s, r in zip(shares, rps_list))

    # Grow if under budget and we can add shares without exceeding
    # (blended estimate can leave headroom when RPS varies)
    shares = list(raw_shares)
    risk_now = total_risk(shares)
    # Try adding shares to highest-weight levels while under cap
    improved = True
    while improved:
        improved = False
        for idx in order:
            add_cost = rps_list[idx]
            if risk_now + add_cost <= max_risk + 1e-9:
                shares[idx] += 1
                risk_now += add_cost
                improved = True
                # keep going to fill as much as possible
    # If somehow over (shouldn't be with floor), strip from lowest weight
    strip_order = sorted(range(n), key=lambda i: w[i])  # farthest first
    while total_risk(shares) > max_risk + 1e-9:
        stripped = False
        for idx in strip_order:
            if shares[idx] > 0:
                shares[idx] -= 1
                stripped = True
                break
        if not stripped:
            break

    levels: List[LevelResult] = []
    for e, wi, s, r in zip(entries, w, shares, rps_list):
        levels.append(
            LevelResult(
                entry=float(e),
                weight=wi,
                shares=s,
                risk_per_share=r,
                tranche_risk=round(s * r, 4),
            )
        )

    total_shares = sum(shares)
    total_risk_used = round(total_risk(shares), 4)
    if total_shares > 0:
        avg_cost = sum(s * float(e) for s, e in zip(shares, entries)) / total_shares
    else:
        avg_cost = 0.0

    return SizeResult(
        side=side,
        stop=float(stop),
        max_risk=float(max_risk),
        levels=levels,
        total_shares=total_shares,
        total_risk_used=total_risk_used,
        avg_cost=round(avg_cost, 6),
        warnings=warnings,
    )


def target_pnl(
    side: str,
    avg_cost: float,
    shares: int,
    target: float,
) -> float:
    """Unrealized / planned P&L if all shares exit at target."""
    side = side.lower().strip()
    if shares < 0:
        raise SizingError("Shares cannot be negative")
    if side == "long":
        return round((target - avg_cost) * shares, 4)
    if side == "short":
        return round((avg_cost - target) * shares, 4)
    raise SizingError(f"Invalid side: {side!r}")


@dataclass
class ExitTranche:
    """One partial exit peel."""

    price: float
    pct: float  # fraction of total shares (0–1)
    shares: int = 0
    pnl: float = 0.0


@dataclass
class ExitResult:
    """Result of full dump or partial peels."""

    tranches: List[ExitTranche]
    total_shares_exited: int
    total_pnl: float
    remaining_shares: int


def plan_exits(
    side: str,
    avg_cost: float,
    total_shares: int,
    exit_prices: Sequence[float],
    exit_pcts: Optional[Sequence[float]] = None,
) -> ExitResult:
    """
    Plan exits: full dump (one price, 100%) or partial peels.

    ``exit_pcts`` as fractions summing to ≤ 1.0. If None and one price,
    dump 100%. Shares are whole; leftover from rounding goes to last tranche.
    """
    side = side.lower().strip()
    if total_shares < 0:
        raise SizingError("Shares cannot be negative")
    if not exit_prices:
        raise SizingError("At least one exit price required")

    n = len(exit_prices)
    if exit_pcts is None:
        if n == 1:
            pcts = [1.0]
        else:
            raise SizingError("exit_pcts required when multiple exit prices")
    else:
        if len(exit_pcts) != n:
            raise SizingError("exit_pcts length must match exit_prices")
        pcts = [float(p) for p in exit_pcts]
        if any(p < 0 for p in pcts):
            raise SizingError("Exit percentages cannot be negative")
        if sum(pcts) > 1.0 + 1e-9:
            raise SizingError("Exit percentages cannot sum over 100%")

    # Allocate whole shares
    raw = [int(total_shares * p) for p in pcts]
    # Give remainder to last non-zero-pct tranche so we don't lose shares
    # when dumping 100%
    target_total = int(round(sum(pcts) * total_shares))
    # Prefer exact floor then distribute remainder
    assigned = sum(raw)
    # Cap target_total to total_shares
    target_total = min(target_total, total_shares)
    rem = target_total - assigned
    for i in range(n - 1, -1, -1):
        if rem <= 0:
            break
        if pcts[i] > 0 or i == n - 1:
            raw[i] += rem
            rem = 0

    # If sum(pcts) ~= 1, ensure we exit all shares (rounding)
    if abs(sum(pcts) - 1.0) < 1e-9 and sum(raw) < total_shares:
        raw[-1] += total_shares - sum(raw)

    tranches: List[ExitTranche] = []
    for price, pct, sh in zip(exit_prices, pcts, raw):
        pnl = target_pnl(side, avg_cost, sh, float(price))
        tranches.append(
            ExitTranche(price=float(price), pct=pct, shares=sh, pnl=pnl)
        )

    exited = sum(t.shares for t in tranches)
    return ExitResult(
        tranches=tranches,
        total_shares_exited=exited,
        total_pnl=round(sum(t.pnl for t in tranches), 4),
        remaining_shares=total_shares - exited,
    )


def gap_loss(
    side: str,
    avg_cost: float,
    shares: int,
    gap_price: float,
) -> float:
    """
    Estimated $ loss if price gaps through stop to ``gap_price``.

    For long, gap_price should be worse (lower) than stop/cost.
    For short, gap_price should be worse (higher).
    Returns signed P&L (negative = loss).
    """
    return target_pnl(side, avg_cost, shares, gap_price)


def sort_entries_farthest_to_nearest(
    side: str, entries: Sequence[float], stop: float
) -> List[float]:
    """
    Sort entry prices farthest→nearest to stop.
    Long: highest entry first (farthest above stop).
    Short: lowest entry first (farthest below stop).
    """
    side = side.lower().strip()
    if side == "long":
        return sorted((float(e) for e in entries), reverse=True)
    if side == "short":
        return sorted(float(e) for e in entries)
    raise SizingError(f"Invalid side: {side!r}")
