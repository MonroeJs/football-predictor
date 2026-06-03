"""
英超联赛 — EPL

数据来源: football-data.co.uk (mmz4281/{season}/E0.csv)
预测方式: ML 模型 (RF/CatBoost)
"""
import sys, warnings
warnings.filterwarnings('ignore')

from pathlib import Path
from typing import Optional
import pandas as pd

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from src.leagues.base import BaseLeague
from src.leagues import register
from src.leagues.utils import download_european
from src.model_cache import save_model, load_model, has_model
from config import TRAIN_SEASONS, CURRENT_SEASON_CODE


@register
class EPLLeague(BaseLeague):
    key = "epl"
    name = "Premier League"
    country = "England"
    league_type = "league"
    data_source = "football-data.co.uk (E0)"
    has_ml_model = True
    show_standings = True
    show_goals = True

    def __init__(self):
        super().__init__()
        self.data_dir = Path(__file__).parent.parent.parent / 'data' / 'raw'

    def load_matches(self) -> pd.DataFrame:
        """加载 EPL 比赛数据"""
        if self._matches is not None:
            return self._matches

        all_seasons = sorted(set(TRAIN_SEASONS + [CURRENT_SEASON_CODE]))
        df = download_european(all_seasons, 'E0')
        self._matches = df
        return df

    def get_predictions(self) -> list[dict]:
        """获取预测结果（ML 模型）"""
        if self._predictions is not None:
            return self._predictions

        df = self.load_matches()
        if df.empty:
            return []

        # Use existing ML pipeline
        from src.ml_models import FootballPredictor
        from src.features_v2 import build_features_v2, get_feature_columns_v2

        predictor = load_model('epl')
        if predictor is None:
            predictor = FootballPredictor(model_type='catboost')
            try:
                X_train, y_train, _ = build_features_v2(df)
                if X_train is not None:
                    predictor.fit(X_train, y_train)
                    save_model(predictor, 'epl')
            except Exception as e:
                print(f'  EPL train error: {e}')
                return []

        try:
            latest = df.tail(20)
            X_test, _, _ = build_features_v2(latest)
            if X_test is not None and len(X_test) > 0:
                probs = predictor.predict_proba(X_test)
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
            print(f'  EPL predict error: {e}')

        return []

    def get_standings(self) -> Optional[dict]:
        """积分榜（模拟）"""
        df = self.load_matches()
        if df.empty:
            return None

        # Filter to most recent season
        seasons = sorted(df['season'].unique())
        if not seasons:
            return None
        current = seasons[-1]
        season_df = df[df['season'] == current]

        # Calculate standings
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
            } for t in standings[:20]],
            'season': str(current),
        }
