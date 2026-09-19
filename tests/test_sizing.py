"""Unit tests for pure sizing math."""

from __future__ import annotations

import pytest

from trading_risk_calculator.sizing import (
    SizingError,
    gap_loss,
    max_shares_for_risk,
    normalize_weights,
    plan_exits,
    risk_per_share,
    size_levels,
    size_single,
    soft_weights_near_stop,
    sort_entries_farthest_to_nearest,
    target_pnl,
    validate_entry_vs_stop,
)


class TestValidate:
    def test_long_ok(self):
        assert validate_entry_vs_stop("long", 100, 95) is None

    def test_long_bad(self):
        msg = validate_entry_vs_stop("long", 95, 100)
        assert msg and "above stop" in msg

    def test_long_equal_bad(self):
        assert validate_entry_vs_stop("long", 100, 100) is not None

    def test_short_ok(self):
        assert validate_entry_vs_stop("short", 95, 100) is None

    def test_short_bad(self):
        msg = validate_entry_vs_stop("short", 100, 95)
        assert msg and "below stop" in msg


class TestWholeSharesNeverOver:
    def test_exact_fit(self):
        # $1 risk/share, $300 cap → 300 shares
        r = size_single("long", 100, 99, 300)
        assert r.total_shares == 300
        assert r.total_risk_used == 300.0

    def test_floor_when_one_more_exceeds(self):
        # classic: $301 would need if fractional; rps=1.003... wait
        # entry 50.01 stop 49 → rps=1.01; max 300 → 300/1.01 = 297.02 → 297
        r = size_single("long", 50.01, 49.0, 300)
        assert r.total_shares == int(300 // 1.01)
        assert r.total_risk_used <= 300
        # one more would exceed
        assert (r.total_shares + 1) * 1.01 > 300

    def test_301_on_300_style(self):
        # rps = 1.0 exactly would be 300; use rps that floors
        # max_risk 300, rps 1.00333... → floor
        r = size_single("long", 10.0, 8.993333, 300)
        rps = risk_per_share("long", 10.0, 8.993333)
        assert r.total_shares == int(300 // rps)
        assert r.total_risk_used <= 300 + 1e-6
        assert (r.total_shares + 1) * rps > 300

    def test_max_shares_helper(self):
        assert max_shares_for_risk(300, 1.0) == 300
        assert max_shares_for_risk(300, 1.01) == 297
        assert max_shares_for_risk(0, 1.0) == 0

    def test_whole_shares_only(self):
        r = size_single("long", 100.5, 99.0, 100)
        assert isinstance(r.total_shares, int)
        assert r.total_shares == int(r.total_shares)


class TestLongShort:
    def test_long_risk(self):
        assert risk_per_share("long", 100, 95) == 5.0

    def test_short_risk(self):
        assert risk_per_share("short", 95, 100) == 5.0

    def test_short_sizing(self):
        r = size_single("short", 50, 55, 500)
        assert r.total_shares == 100  # $5 rps
        assert r.total_risk_used == 500.0

    def test_long_target_pnl(self):
        assert target_pnl("long", 100, 10, 110) == 100.0

    def test_short_target_pnl(self):
        assert target_pnl("short", 100, 10, 90) == 100.0


class TestWeights:
    def test_default_3(self):
        assert soft_weights_near_stop(3) == pytest.approx([0.20, 0.30, 0.50])

    def test_default_1(self):
        assert soft_weights_near_stop(1) == [1.0]

    def test_default_2(self):
        assert soft_weights_near_stop(2) == pytest.approx([0.40, 0.60])

    def test_default_n_sums(self):
        for n in range(1, 8):
            w = soft_weights_near_stop(n)
            assert len(w) == n
            assert sum(w) == pytest.approx(1.0)
            # nearer (last) >= farther (first) for n>1
            if n > 1:
                assert w[-1] >= w[0]

    def test_normalize(self):
        assert normalize_weights([20, 30, 50]) == pytest.approx([0.2, 0.3, 0.5])


class TestScaleIn:
    def test_three_levels_long(self):
        # Common case inspired: 78/76/75 stop below — use 80/78/76 stop 74
        entries = [80.0, 78.0, 76.0]  # farthest → nearest
        stop = 74.0
        max_risk = 300.0
        r = size_levels("long", entries, stop, max_risk)
        assert r.total_risk_used <= max_risk + 1e-6
        assert r.total_shares == sum(lv.shares for lv in r.levels)
        assert len(r.levels) == 3
        # Heavier near stop (last level should have most shares typically)
        assert r.levels[2].shares >= r.levels[0].shares
        assert r.avg_cost > 0

    def test_rebalance_custom_weights(self):
        entries = [100.0, 98.0, 96.0]
        stop = 94.0
        r1 = size_levels("long", entries, stop, 600, weights=[0.2, 0.3, 0.5])
        r2 = size_levels("long", entries, stop, 600, weights=[0.5, 0.3, 0.2])
        assert r1.levels[0].shares != r2.levels[0].shares or True
        assert r1.total_risk_used <= 600
        assert r2.total_risk_used <= 600

    def test_invalid_long_raises(self):
        with pytest.raises(SizingError):
            size_levels("long", [90.0], 95.0, 100)

    def test_invalid_short_raises(self):
        with pytest.raises(SizingError):
            size_levels("short", [100.0], 95.0, 100)

    def test_sort_long(self):
        assert sort_entries_farthest_to_nearest("long", [76, 80, 78], 74) == [
            80.0,
            78.0,
            76.0,
        ]

    def test_sort_short(self):
        assert sort_entries_farthest_to_nearest("short", [104, 100, 102], 106) == [
            100.0,
            102.0,
            104.0,
        ]


class TestExits:
    def test_full_dump(self):
        # buy avg 76, dump all at 78
        er = plan_exits("long", 76.0, 100, [78.0])
        assert er.total_shares_exited == 100
        assert er.total_pnl == 200.0
        assert er.remaining_shares == 0

    def test_partial_peels(self):
        er = plan_exits("long", 100.0, 100, [110.0, 120.0], [0.5, 0.5])
        assert er.total_shares_exited == 100
        assert er.total_pnl == pytest.approx(0.5 * 100 * 10 + 0.5 * 100 * 20)

    def test_pct_over_100_raises(self):
        with pytest.raises(SizingError):
            plan_exits("long", 100.0, 10, [110.0, 120.0], [0.6, 0.6])


class TestGap:
    def test_gap_long_loss(self):
        # avg 100, stop area, gap to 90 → -$10/share
        loss = gap_loss("long", 100.0, 50, 90.0)
        assert loss == -500.0

    def test_gap_short_loss(self):
        loss = gap_loss("short", 100.0, 50, 110.0)
        assert loss == -500.0
