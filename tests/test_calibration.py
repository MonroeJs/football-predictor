"""Tests for probability calibration in betting system"""
import pytest
from src.betting_system import ConfidenceBettingSystem


class TestCalibrateProb:
    """Test calibration probability adjustment in evaluate_bet"""

    def test_calibrate_increases_prob(self):
        """因子 >1.0 时概率应上调"""
        # model_prob[pred]=0.6 → tier = VHigh
        cbs = ConfidenceBettingSystem(calibration_factors={'VHigh': 1.2})
        decision = cbs.evaluate_bet(
            model_probs={'H': 0.6, 'D': 0.25, 'A': 0.15},
            odds_series={'H': 2.5, 'D': 3.5, 'A': 5.0},
            match_id="Test",
            league="Test",
            date="2026-01-01",
            actual_outcome="H",
        )
        # 0.6 * 1.2 = 0.72
        assert decision.confidence == pytest.approx(0.72, abs=1e-4)

    def test_calibrate_decreases_prob(self):
        """因子 <1.0 时概率应下调"""
        # model_prob[pred]=0.6 → tier = VHigh
        cbs = ConfidenceBettingSystem(calibration_factors={'VHigh': 0.8})
        decision = cbs.evaluate_bet(
            model_probs={'H': 0.6, 'D': 0.25, 'A': 0.15},
            odds_series={'H': 2.5, 'D': 3.5, 'A': 5.0},
            match_id="Test",
            league="Test",
            date="2026-01-01",
            actual_outcome="H",
        )
        # 0.6 * 0.8 = 0.48
        assert decision.confidence == pytest.approx(0.48, abs=1e-4)

    def test_calibrate_no_change(self):
        """因子 =1.0 时概率不变"""
        # model_prob[pred]=0.6 → tier = VHigh
        cbs = ConfidenceBettingSystem(calibration_factors={'VHigh': 1.0})
        decision = cbs.evaluate_bet(
            model_probs={'H': 0.6, 'D': 0.25, 'A': 0.15},
            odds_series={'H': 2.5, 'D': 3.5, 'A': 5.0},
            match_id="Test",
            league="Test",
            date="2026-01-01",
            actual_outcome="H",
        )
        assert decision.confidence == pytest.approx(0.6, abs=1e-4)

    def test_calibrate_capped_at_max(self):
        """因子 >1.5 时应被 cap 到 1.5"""
        # model_prob[pred]=0.6 → tier = VHigh
        cbs = ConfidenceBettingSystem(calibration_factors={'VHigh': 2.0})
        decision = cbs.evaluate_bet(
            model_probs={'H': 0.6, 'D': 0.25, 'A': 0.15},
            odds_series={'H': 2.5, 'D': 3.5, 'A': 5.0},
            match_id="Test",
            league="Test",
            date="2026-01-01",
            actual_outcome="H",
        )
        # 0.6 * min(2.0, 1.5) = 0.9
        assert decision.confidence == pytest.approx(0.9, abs=1e-4)

    def test_calibrate_factor_affects_edge(self):
        """校准因子影响 edge 计算"""
        # model_prob[pred]=0.55 → tier = High
        cbs = ConfidenceBettingSystem(calibration_factors={'High': 1.2})
        decision = cbs.evaluate_bet(
            model_probs={'H': 0.55, 'D': 0.25, 'A': 0.20},
            odds_series={'H': 2.1, 'D': 3.5, 'A': 4.0},
            match_id="Test",
            league="Test",
            date="2026-01-01",
            actual_outcome="H",
        )
        # implied prob = 1/2.1 ≈ 0.4762
        # calibrated prob = 0.55 * 1.2 = 0.66
        # edge = 0.66 - 0.4762 = 0.1838
        assert decision.edge > 0
        assert decision.confidence == pytest.approx(0.66, abs=1e-4)

    def test_calibrate_enables_bet_when_factor_gt_one(self):
        """
        校准因子 >1 让原本不满足 edge 条件的投注变得可行。
        
        Scenario: prob=0.62 (VHigh tier), odds=1.65 (implied ≈ 0.606)
          - Old code (cap at 1.0): edge = 0.62 - 0.606 = 0.014 < 0.03 → no bet
          - New code (cap at 1.5): edge = 0.744 - 0.606 = 0.138 > 0.03 → bet!
        """
        cbs = ConfidenceBettingSystem(
            calibration_factors={'VHigh': 1.2},
            min_edge=0.03,
        )
        decision = cbs.evaluate_bet(
            model_probs={'H': 0.62, 'D': 0.20, 'A': 0.18},
            odds_series={'H': 1.65, 'D': 3.5, 'A': 5.0},
            match_id="Test",
            league="Test",
            date="2026-01-01",
            actual_outcome="H",
        )
        assert decision.bet_on == "H"
        assert decision.edge > 0.03


class TestComputeCalibrationFactors:
    """Test compute_calibration_factors static method"""

    def test_basic_calculation(self):
        """accuracy / avg_confidence per tier"""
        y_true = ['H', 'A', 'D', 'D']
        y_prob_list = [
            {'H': 0.65, 'D': 0.20, 'A': 0.15},  # pred=H, correct, VHigh
            {'H': 0.20, 'D': 0.15, 'A': 0.65},  # pred=A, correct, VHigh
            {'H': 0.55, 'D': 0.25, 'A': 0.20},  # pred=H, wrong, High
            {'H': 0.10, 'D': 0.80, 'A': 0.10},  # pred=D, correct, Elite
        ]
        tiers = ['VHigh', 'VHigh', 'High', 'Elite']

        factors = ConfidenceBettingSystem.compute_calibration_factors(
            y_true, y_prob_list, tiers
        )

        # VHigh: 2 matches, 2 correct, confs=[0.65, 0.65]
        # accuracy=1.0, avg_conf=0.65
        # factor = min(1.0/0.65, 1.5) → capped at 1.5
        assert 'VHigh' in factors
        assert factors['VHigh'] == pytest.approx(1.5, abs=1e-4)

        # High: 1 match, 0 correct, conf=0.55
        # accuracy=0 < 0.01 → smoothing → factor = 1.0
        assert 'High' in factors
        assert factors['High'] == pytest.approx(1.0, abs=1e-4)

        # Elite: 1 match, 1 correct, conf=0.80
        # accuracy=1.0, avg_conf=0.80
        # factor = min(1.0/0.80, 1.5) = 1.25
        assert 'Elite' in factors
        assert factors['Elite'] == pytest.approx(1.25, abs=1e-4)

    def test_smoothing_edge_case(self):
        """accuracy 或 avg_conf 极低时返回 1.0"""
        # Single match, wrong prediction → accuracy = 0 → smoothing → 1.0
        factors1 = ConfidenceBettingSystem.compute_calibration_factors(
            y_true=['H'],
            y_prob_list=[{'H': 0.10, 'D': 0.80, 'A': 0.10}],
            tiers=['High'],
        )
        assert factors1['High'] == pytest.approx(1.0, abs=1e-4)

        # Very low avg confidence (< 0.01)
        factors2 = ConfidenceBettingSystem.compute_calibration_factors(
            y_true=['H'],
            y_prob_list=[{'H': 0.005, 'D': 0.99, 'A': 0.005}],
            tiers=['Low'],
        )
        assert factors2['Low'] == pytest.approx(1.0, abs=1e-4)

    def test_custom_max_factor(self):
        """可以自定义 max_factor"""
        y_true = ['H', 'A']
        y_prob_list = [
            {'H': 0.70, 'D': 0.15, 'A': 0.15},  # correct, Elite
            {'H': 0.15, 'D': 0.15, 'A': 0.70},  # correct, Elite
        ]
        tiers = ['Elite', 'Elite']
        # accuracy=1.0, avg_conf=0.70
        # factor = min(1.0/0.70, 3.0) = 1.428
        factors = ConfidenceBettingSystem.compute_calibration_factors(
            y_true, y_prob_list, tiers, max_factor=3.0
        )
        assert factors['Elite'] == pytest.approx(1.0 / 0.70, abs=1e-4)

    def test_empty_tier_returns_one(self):
        """没有数据的层返回 1.0"""
        factors = ConfidenceBettingSystem.compute_calibration_factors(
            y_true=['H'],
            y_prob_list=[{'H': 0.60, 'D': 0.25, 'A': 0.15}],
            tiers=['VHigh'],
        )
        # VHigh exists, but Medium should not
        assert 'VHigh' in factors
        assert 'NonExistentTier' not in factors
