"""
日本 J1 联赛

数据来源: football-data.co.uk /new/JP.csv
预测方式: ML 模型
"""
import sys, warnings
warnings.filterwarnings('ignore')

from pathlib import Path
from typing import Optional
import pandas as pd
import numpy as np

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from src.leagues.base import BaseLeague
from src.leagues import register
from src.leagues.utils import download_new_format
from src.model_cache import save_model, load_model


@register
class JLeague(BaseLeague):
    key = "j1"
    name = "J1 League"
    country = "Japan"
    league_type = "league"
    data_source = "football-data.co.uk (/new/JP.csv)"
    has_ml_model = True
    show_standings = True
    show_goals = True

    JP_URL = "https://www.football-data.co.uk/new/JP.csv"

    def __init__(self):
        super().__init__()
        self.data_dir = Path(__file__).parent.parent.parent / 'data' / 'raw'

    def load_matches(self) -> pd.DataFrame:
        """加载 J1 联赛数据（优先本地缓存）"""
        if self._matches is not None:
            return self._matches

        raw_path = self.data_dir / 'JP_2526.csv'
        if raw_path.exists():
            from src.leagues.utils import standardize_new_format
            raw = pd.read_csv(raw_path)
            j1_mask = raw['League'].str.strip() == 'J1 League'
            j1_raw = raw[j1_mask].reset_index(drop=True)
            df = standardize_new_format(j1_raw)
            print(f'  J1 League: {len(df)} matches loaded (from cache)')
        else:
            df = download_new_format(self.JP_URL, 'JP')
            if df.empty:
                return df
            raw_path2 = self.data_dir / 'JP_2526.csv'
            if raw_path2.exists():
                raw = pd.read_csv(raw_path2)
                j1_mask = raw['League'].str.strip() == 'J1 League'
                if sum(j1_mask) > 0:
                    df = df.iloc[:len(raw)].copy()
                    df = df[j1_mask.values].reset_index(drop=True)

        self._matches = df
        return df

    def get_predictions(self) -> list[dict]:
        """获取预测结果"""
        if self._predictions is not None:
            return self._predictions

        df = self.load_matches()
        if df.empty:
            return []

        # Try ML model first (cached)
        predictor = load_model('j1')
        if predictor is not None:
            try:
                from src.features import build_features
                df_feat = build_features(df)
                if 'league' not in df_feat.columns:
                    df_feat['league'] = 'J1'
                
                feature_cols = [c for c in df_feat.columns if c.startswith(('form_', 'elo_', 'gd_', 'avg_'))
                               and c not in ('home_goals', 'away_goals')]
                feature_cols = [c for c in feature_cols if c in df_feat.columns]
                
                if len(feature_cols) >= 3 and len(df_feat) > 100:
                    X = df_feat[feature_cols].fillna(0).tail(20).values
                    probs = predictor.predict_proba(X)
                    latest = df_feat.tail(20)
                    results = []
                    for i, (_, row) in enumerate(latest.iterrows()):
                        if i < len(probs):
                            p = probs[i]
                            results.append({
                                'date': str(row['date'].date()) if pd.notna(row['date']) else '',
                                'home_team': row['home_team'],
                                'away_team': row['away_team'],
                                'prob_H': float(p[2]),
                                'prob_D': float(p[1]),
                                'prob_A': float(p[0]),
                            })
                    self._predictions = self._serialize_predictions(results)
                    return self._predictions
            except Exception as e:
                print(f'  J1 ML predict error: {e}')

        # Fallback: odds-based (same as WC)
        from src.betting_system import get_confidence_tier
        # Note: /new/JP.csv only has Bet365 odds for recent months
        # Earlier matches without odds are shown without betting recommendation
        df_odds = df[df['B365H'].notna()].tail(20)
        results = []
        # Show last 20 matches total (with or without odds)
        for _, row in df.tail(40).iterrows():
            has_odds = pd.notna(row.get('B365H'))
            if has_odds:
                odds = {'H': row['B365H'], 'D': row['B365D'], 'A': row['B365A']}
                total = sum(1.0/max(o, 1.01) for o in odds.values())
                probs = {k: (1.0/max(odds[k], 1.01))/total for k in odds}
                max_outcome = max(probs, key=probs.get)
                max_prob = probs[max_outcome]
                tier = get_confidence_tier(max_prob)
                stake = 30 if tier.value in ('VHigh',) else (50 if tier.value == 'Elite' else (80 if tier.value == 'Max' else 0))
            else:
                max_outcome = ''
                max_prob = 0
                tier = type('t',(),{'value':'Low'})()
                stake = 0
            
            results.append({
                'date': str(row['date'].date()) if pd.notna(row['date']) else '',
                'home': row['home_team'],
                'away': row['away_team'],
                'home_team': row['home_team'],
                'away_team': row['away_team'],
                'predicted_outcome': max_outcome,
                'confidence': f'{max_prob:.1%}' if max_prob > 0 else 'N/A',
                'tier': tier.value,
                'fav_odds': odds[max_outcome] if has_odds else 0,
                'suggested_stake': stake,
                'has_odds': has_odds,
            })
            odds = {'H': row['B365H'], 'D': row['B365D'], 'A': row['B365A']}
            total = sum(1.0/max(o, 1.01) for o in odds.values())
            probs = {k: (1.0/max(odds[k], 1.01))/total for k in odds}
            max_outcome = max(probs, key=probs.get)
            max_prob = probs[max_outcome]
            tier = get_confidence_tier(max_prob)
            

        
        self._predictions = self._serialize_predictions(results)
        return self._predictions

    def get_standings(self) -> Optional[dict]:
        """积分榜"""
        df = self.load_matches()
        if df.empty:
            return None

        # Most recent season
        seasons = sorted(df['season'].unique())
        if not seasons:
            return None
        current = seasons[-1]
        season_df = df[df['season'] == current]

        pts = {}
        gf = {}
        ga = {}
        played = {}

        for _, row in season_df.iterrows():
            h = row['home_team']
            a = row['away_team']
            hg = row['home_goals']
            ag = row['away_goals']
            if pd.isna(hg) or pd.isna(ag):
                continue

            for team in [h, a]:
                if team not in pts:
                    pts[team] = 0
                    gf[team] = 0
                    ga[team] = 0
                    played[team] = 0

            gf[h] += int(hg)
            ga[h] += int(ag)
            gf[a] += int(ag)
            ga[a] += int(hg)
            played[h] += 1
            played[a] += 1

            if hg > ag:
                pts[h] += 3
            elif hg < ag:
                pts[a] += 3
            else:
                pts[h] += 1
                pts[a] += 1

        standings = sorted(pts.keys(), key=lambda t: (pts[t], gf[t] - ga[t], gf[t]), reverse=True)
        return {
            'teams': [{
                'name': t,
                'pts': pts[t],
                'gd': gf[t] - ga[t],
                'gf': gf[t],
                'ga': ga[t],
                'pld': played[t],
            } for t in standings],
            'season': str(current),
        }
