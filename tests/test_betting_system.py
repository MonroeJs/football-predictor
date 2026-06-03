"""Unit tests for KellyCalculator in src.betting_system.py"""

import pytest
from src.betting_system import KellyCalculator


kc = KellyCalculator()


# ─── kelly_fraction ──────────────────────────────────────────

class TestKellyFraction:
    """Kelly 比例计算 — f* = (p*b - q) / b  where b=odds-1, q=1-p"""

    def test_kelly_fraction_normal(self):
        """prob=0.6, odds=2.5 → f = (0.6*1.5 - 0.4) / 1.5 = 0.3333"""
        result = kc.kelly_fraction(0.6, 2.5)
        assert result == pytest.approx(0.3333, abs=1e-4)

    def test_kelly_fraction_no_edge(self):
        """prob=0.5, odds=2.0 (fair odds, no edge) → 0.0"""
        result = kc.kelly_fraction(0.5, 2.0)
        assert result == pytest.approx(0.0, abs=1e-9)

    def test_kelly_fraction_prob_zero(self):
        """prob=0 → 0.0"""
        assert kc.kelly_fraction(0.0, 2.0) == 0.0

    def test_kelly_fraction_prob_one(self):
        """prob=1 → 0.0"""
        assert kc.kelly_fraction(1.0, 2.0) == 0.0

    def test_kelly_fraction_odds_one(self):
        """odds=1 (even money, no net profit) → 0.0"""
        assert kc.kelly_fraction(0.6, 1.0) == 0.0

    def test_kelly_fraction_odds_below_one(self):
        """odds<1 → 0.0"""
        assert kc.kelly_fraction(0.6, 0.5) == 0.0

    def test_kelly_fraction_negative_edge_clamps(self):
        """negative edge → clamped to 0.0"""
        result = kc.kelly_fraction(0.4, 2.0)
        assert result == pytest.approx(0.0, abs=1e-9)


# ─── expected_value ─────────────────────────────────────────

class TestExpectedValue:
    """EV = p * odds - 1"""

    def test_expected_value_positive(self):
        """prob=0.6, odds=2.0 → EV=0.2"""
        result = kc.expected_value(0.6, 2.0)
        assert result == pytest.approx(0.2, abs=1e-9)

    def test_expected_value_negative(self):
        """prob=0.4, odds=2.0 → EV=-0.2"""
        result = kc.expected_value(0.4, 2.0)
        assert result == pytest.approx(-0.2, abs=1e-9)

    def test_expected_value_break_even(self):
        """prob=0.5, odds=2.0 → EV=0.0"""
        result = kc.expected_value(0.5, 2.0)
        assert result == pytest.approx(0.0, abs=1e-9)


# ─── implied_prob ───────────────────────────────────────────

class TestImpliedProb:
    """隐含概率 = 1/odds (odds<=1 → 0.0)"""

    def test_implied_prob_even_odds(self):
        """odds=2.0 → implied=0.5"""
        result = kc.implied_prob(2.0)
        assert result == pytest.approx(0.5, abs=1e-9)

    def test_implied_prob_long_odds(self):
        """odds=4.0 → implied=0.25"""
        result = kc.implied_prob(4.0)
        assert result == pytest.approx(0.25, abs=1e-9)

    def test_implied_prob_evens(self):
        """odds=1.0 → 0.0 (edge case)"""
        assert kc.implied_prob(1.0) == 0.0

    def test_implied_prob_below_one(self):
        """odds<1 → 0.0"""
        assert kc.implied_prob(0.5) == 0.0
        assert kc.implied_prob(0.0) == 0.0


# ─── edge ───────────────────────────────────────────────────

class TestEdge:
    """edge = prob - implied_prob(odds)"""

    def test_edge_positive(self):
        """model prob > implied prob → positive edge"""
        result = kc.edge(0.45, 2.5)   # 0.45 - 0.40 = +0.05
        assert result > 0.0
        assert result == pytest.approx(0.05, abs=1e-4)

    def test_edge_negative(self):
        """model prob < implied prob → negative edge"""
        result = kc.edge(0.55, 1.8)   # 0.55 - 0.5556 = -0.0056
        assert result < 0.0
        assert result == pytest.approx(-0.0056, abs=1e-4)

    def test_edge_zero(self):
        """model prob == implied prob → edge ≈ 0"""
        result = kc.edge(0.5, 2.0)
        assert result == pytest.approx(0.0, abs=1e-9)

    def test_edge_boundary_odds(self):
        """odds<=1 should give edge = prob - 0 = prob"""
        result = kc.edge(0.6, 1.0)
        assert result == pytest.approx(0.6, abs=1e-9)
