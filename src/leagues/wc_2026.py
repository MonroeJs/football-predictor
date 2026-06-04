"""
2026 世界杯 — 锦标赛预测

数据来源: run_wc_odds.csv (手动填赔率或从 football-data.co.uk 下载)
预测方式: 赔率驱动 + 置信度分层
"""
import sys, warnings, json, csv
warnings.filterwarnings('ignore')

from pathlib import Path
from datetime import datetime
from typing import Optional
import pandas as pd
import numpy as np

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from src.leagues.base import BaseLeague
from src.leagues import register
from src.wc_predictor import WCPredictor, TEAM_ELO
from src.group_probs import calc_all_groups, calc_full_tournament, GROUPS


@register
class WC2026League(BaseLeague):
    key = "wc2026"
    name = "2026 FIFA World Cup"
    country = "USA / Canada / Mexico"
    league_type = "tournament"
    data_source = "赔率驱动 (run_wc_odds.csv)"
    has_ml_model = False
    show_groups = True
    show_standings = False

    def __init__(self):
        super().__init__()
        self.root = Path(__file__).parent.parent.parent
        self.predictor = WCPredictor()

    def load_matches(self):
        return pd.DataFrame()

    def get_predictions(self) -> list[dict]:
        """从 run_wc_odds.csv 加载预测"""
        csv_path = self.root / 'run_wc_odds.csv'
        if not csv_path.exists():
            return []

        df = pd.read_csv(csv_path)
        from src.betting_system import get_confidence_tier

        predictions = []
        for _, row in df.iterrows():
            for k in ['B365H', 'B365D', 'B365A']:
                try:
                    row[k] = float(row[k])
                except (ValueError, TypeError):
                    continue

            if not all(row.get(k, 0) > 0.1 for k in ['B365H', 'B365D', 'B365A']):
                continue

            result = self.predictor.predict_match(
                row['home'], row['away'],
                float(row['B365H']),
                float(row['B365D']),
                float(row['B365A'])
            )
            result['group'] = row.get('group', '?')
            result['date'] = row.get('date', '')
            predictions.append(result)

        predictions.sort(key=lambda x: (x.get('date', ''),
                                         -float(x['confidence'].rstrip('%')) / 100))
        return self._serialize_predictions(predictions)

    def get_standings(self) -> Optional[dict]:
        """小组出线概率（Monte Carlo）"""
        probs = calc_all_groups()
        if not probs:
            return None

        return {
            'groups': probs,
            'teams_by_group': GROUPS,
        }

    def get_tournament_probs(self) -> Optional[dict]:
        """完整赛事概率（夺冠 + 各轮次晋级）
        使用缓存，后台预热完成前返回 None（页面不显示淘汰赛标签）。
        """
        try:
            from src.group_probs import TOURNEY_CACHE
            if not TOURNEY_CACHE:
                return None
            from src.group_probs import calc_full_tournament
            return calc_full_tournament()
        except Exception as e:
            print(f'Tournament probs error: {e}')
            return None

    def get_info(self) -> dict:
        info = super().get_info()
        info['groups'] = list(GROUPS.keys())
        # 夺冠热门（仅缓存就绪时）
        try:
            from src.group_probs import TOURNEY_CACHE
            if TOURNEY_CACHE:
                top5 = sorted(TOURNEY_CACHE['champion_probs'].items(),
                             key=lambda x: x[1], reverse=True)[:5]
                info['favorites'] = [{'team': t, 'prob': f'{p*100:.1f}%'}
                                    for t, p in top5]
        except:
            pass
        info['team_elo'] = {k: v for k, v in TEAM_ELO.items()
                           if k not in ['Czechia', 'Bosnia', 'Sweden', 'Turkey',
                                        'DR Congo', 'Iraq']}
        return info

    def _serialize_predictions(self, predictions):
        return predictions
