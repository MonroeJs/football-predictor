"""Tests for WC2026 league and Flask API integration."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

import pytest


class TestWC2026League:
    def test_league_registered(self):
        """WC2026 league must be in registry"""
        from src.leagues import REGISTRY
        import src.leagues.wc_2026  # noqa: trigger registration
        assert 'wc2026' in REGISTRY

    def test_league_info(self):
        """get_info returns expected structure"""
        from src.leagues.wc_2026 import WC2026League
        league = WC2026League()
        info = league.get_info()
        assert info['key'] == 'wc2026'
        assert 'groups' in info
        assert len(info['groups']) == 12

    def test_get_predictions_returns_list(self):
        """get_predictions returns non-empty list"""
        from src.leagues.wc_2026 import WC2026League
        league = WC2026League()
        preds = league.get_predictions()
        assert isinstance(preds, list)
        assert len(preds) > 0

    def test_prediction_has_required_fields(self):
        """Each prediction has essential fields"""
        from src.leagues.wc_2026 import WC2026League
        league = WC2026League()
        preds = league.get_predictions()
        required = ['home', 'away', 'odds', 'confidence', 'tier']
        for p in preds[:5]:
            for field in required:
                assert field in p, f"Missing {field} in prediction"

    def test_get_standings(self):
        """get_standings returns group structure when available"""
        from src.leagues.wc_2026 import WC2026League
        league = WC2026League()
        standings = league.get_standings()
        # May be None if first call and cache not ready, but should have structure
        if standings:
            assert 'groups' in standings
            assert 'teams_by_group' in standings


class TestFlaskApp:
    def test_app_imports(self):
        """App module loads without errors"""
        import app  # noqa: F401

    def test_app_has_routes(self):
        """App has expected routes"""
        import app as _app
        rules = [r.rule for r in _app.app.url_map.iter_rules()]
        assert '/' in rules
        assert '/api/leagues' in rules
        assert '/api/<league_key>/predictions' in rules
        assert '/api/wc2026/matches' in rules
        assert '/api/wc2026/stats' in rules

    def test_leagues_api(self):
        """Leagues API returns 3 leagues"""
        import app as _app
        with _app.app.test_client() as client:
            r = client.get('/api/leagues')
            assert r.status_code == 200
            data = r.get_json()
            assert 'wc2026' in data
            assert 'epl' in data
            assert 'j1' in data

    def test_wc_predictions_api(self):
        """WC predictions API returns list"""
        import app as _app
        with _app.app.test_client() as client:
            r = client.get('/api/wc2026/predictions')
            assert r.status_code == 200
            data = r.get_json()
            assert isinstance(data, list)

    def test_wc_matches_api(self):
        """WC matches API returns list"""
        import app as _app
        with _app.app.test_client() as client:
            r = client.get('/api/wc2026/matches')
            assert r.status_code == 200
            data = r.get_json()
            assert isinstance(data, list)

    def test_wc_stats_api(self):
        """WC stats API returns dict"""
        import app as _app
        with _app.app.test_client() as client:
            r = client.get('/api/wc2026/stats')
            assert r.status_code == 200
            data = r.get_json()
            assert isinstance(data, dict)

    def test_homepage_redirect(self):
        """Homepage loads WC2026"""
        import app as _app
        with _app.app.test_client() as client:
            r = client.get('/')
            assert r.status_code == 200
            assert b'2026' in r.data or b'World Cup' in r.data
