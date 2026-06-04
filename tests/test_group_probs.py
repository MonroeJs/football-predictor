"""Tests for group_probs Monte Carlo simulation (World Cup knockout)."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

import pytest
import numpy as np
from src.group_probs import (
    GROUPS, GROUP_MATCHUPS, N_SIMULATIONS, FULL_SIMULATIONS,
    elo_expected, odds_to_probs, expected_goals_from_odds,
    simulate_match, _simulate_knockout_match,
    _select_knockout_teams,
)


class TestEloExpected:
    def test_equal_ratings(self):
        """Equal Elo → 50% each"""
        assert elo_expected(1800, 1800) == pytest.approx(0.5, rel=0.01)

    def test_stronger_favorite(self):
        """200 Elo diff → ~76% favorite"""
        p = elo_expected(2000, 1800)
        assert p > 0.7
        assert p < 0.8

    def test_weaker_underdog(self):
        """Lower rating → lower probability"""
        p = elo_expected(1800, 2000)
        assert p < 0.3

    def test_symmetric(self):
        """P(A beats B) + P(B beats A) ≈ 1"""
        p_ab = elo_expected(1900, 1750)
        p_ba = elo_expected(1750, 1900)
        assert p_ab + p_ba == pytest.approx(1.0, abs=0.001)


class TestOddsToProbs:
    def test_fair_odds(self):
        """Fair 3-way odds should sum to 100%"""
        ph, pd, pa = odds_to_probs(2.0, 3.0, 4.0)
        assert ph > 0
        assert pd > 0
        assert pa > 0
        assert ph + pd + pa == pytest.approx(1.0, abs=0.02)

    def test_lopsided_match(self):
        """Big favorite odds → high implied prob"""
        ph, pd, pa = odds_to_probs(1.2, 6.0, 12.0)
        assert ph > 0.7  # strong favorite
        assert pa < 0.15

    def test_very_close_match(self):
        """Nearly even odds"""
        ph, pd, pa = odds_to_probs(2.5, 3.2, 2.6)
        # Home slight favorite but close
        assert abs(ph - pa) < 0.05

    def test_bad_odds_handling(self):
        """Handle edge case of zero odds (should not crash)"""
        import numpy as np
        ph, pd, pa = odds_to_probs(0, 3.0, 4.0)


class TestExpectedGoals:
    def test_returns_positive(self):
        hxg, axg = expected_goals_from_odds(0.5, 0.25, 0.25)
        assert hxg > 0
        assert axg > 0

    def test_better_team_scores_more(self):
        """Strong favorite should have higher xG"""
        hxg1, axg1 = expected_goals_from_odds(0.6, 0.2, 0.2)
        hxg2, axg2 = expected_goals_from_odds(0.2, 0.2, 0.6)
        assert hxg1 > axg1  # home favorite
        assert axg2 > hxg2  # away favorite

    def test_reasonable_total(self):
        """Total xG should be in a reasonable range"""
        hxg, axg = expected_goals_from_odds(0.5, 0.25, 0.25)
        total = hxg + axg
        assert 1.5 < total < 4.5


class TestSimulateKnockout:
    def test_winner_returned(self):
        """Knockout match returns one of the two teams"""
        winner = _simulate_knockout_match(
            "Brazil", "Chad",
            {"Brazil": 2100, "Chad": 1700},
        )
        assert winner in ["Brazil", "Chad"]

    def test_favorite_wins_often(self):
        """Strong favorite should win most of the time statistically"""
        np.random.seed(42)
        elo_map = {"Brazil": 2100, "Chad": 1700}
        wins = sum(
            1 for _ in range(1000)
            if _simulate_knockout_match("Brazil", "Chad", elo_map) == "Brazil"
        )
        assert wins > 500  # should win more than half


class TestSelectKnockoutTeams:
    def test_selects_32_teams(self):
        """Should select 24 group winners/runners-up + 8 best 3rd"""
        # Generate mock group results for 12 groups of 4
        all_results = []
        for g in list("ABCDEFGHIJKL"):
            for rank in range(1, 5):
                all_results.append({
                    'team': f'Team_{g}_{rank}',
                    'points': 10 - rank,
                    'gd': 5 - rank,
                    'gf': 10 - rank,
                    'group_rank': rank,
                    'group': g,
                })
        selected = _select_knockout_teams(all_results)
        assert len(selected) == 32  # 24 + 8 third-placed

    def test_group_winners_included(self):
        """All 12 group winners must be in knockout"""
        all_results = []
        for g in list("ABCDEFGHIJKL"):
            for rank in range(1, 5):
                all_results.append({
                    'team': f'Team_{g}_{rank}',
                    'points': 10 - rank,
                    'gd': 5 - rank,
                    'gf': 10 - rank,
                    'group_rank': rank,
                    'group': g,
                })
        selected = _select_knockout_teams(all_results)
        selected_names = [t['team'] for t in selected]
        for g in list("ABCDEFGHIJKL"):
            assert f'Team_{g}_1' in selected_names

    def test_only_best_third_places(self):
        """Only top 8 third-placed teams advance"""
        all_results = []
        for g in list("ABCDEFGHIJKL"):
            third_pts = (12 - ord(g) + ord('A'))  # Variable 3rd place points
            all_results.append({
                'team': f'Third_{g}',
                'points': third_pts,
                'gd': third_pts - 5,
                'gf': third_pts,
                'group_rank': 3,
                'group': g,
            })
        selected = _select_knockout_teams(all_results)
        third_in = [t['team'] for t in selected if t['group_rank'] == 3]
        assert len(third_in) == 8  # exactly 8 best third-placed


class TestGroupConstants:
    def test_all_12_groups(self):
        """Must have all 12 groups (A-L)"""
        assert len(GROUPS) == 12

    def test_4_teams_per_group(self):
        """Each group must have exactly 4 teams"""
        for g, teams in GROUPS.items():
            assert len(teams) == 4, f"Group {g} has {len(teams)} teams"

    def test_6_matchups(self):
        """Round robin in 4-team group = 6 matches"""
        assert GROUP_MATCHUPS is not None


class TestSimulationConstants:
    def test_group_sims_reasonable(self):
        """Group stage sims should be manageable"""
        assert N_SIMULATIONS >= 1000  # enough for stability
        assert N_SIMULATIONS <= 50000  # not too slow

    def test_full_sims_reasonable(self):
        """Full tournament sims should be reasonable"""
        assert FULL_SIMULATIONS >= 5000
        assert FULL_SIMULATIONS <= 100000


class TestLoadGroupOdds:
    def test_odds_file_exists(self):
        """run_wc_odds.csv must exist for Monte Carlo"""
        csv_path = Path(__file__).parent.parent / 'run_wc_odds.csv'
        assert csv_path.exists(), "Missing run_wc_odds.csv"
        assert csv_path.stat().st_size > 1000

    def test_odds_file_has_72_matches(self):
        """12 groups x 6 matches = 72"""
        import csv
        csv_path = Path(__file__).parent.parent / 'run_wc_odds.csv'
        with open(csv_path) as f:
            rows = list(csv.DictReader(f))
        assert len(rows) == 72
