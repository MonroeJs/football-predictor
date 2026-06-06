"""
世界杯预测模块

核心思路：针对国家队赛事数据稀疏的特点，使用赔率驱动策略。
- 历史世界杯数据用于验证和校准
- 2026 世界杯使用博彩赔率 → 置信度分层 → 投注系统
- 低赔方 + VHigh+ 策略（欧冠已验证 78% 胜率）

数据来源：
- 历史数据：football-data.co.uk（2014, 2022）
- 当前赔率：用于计算隐含概率和置信度
- 后续可加入 Elo 评级增强

使用方法：
    from src.wc_predictor import WCPredictor
    predictor = WCPredictor()
    predictor.load_historical_data()
    predictor.backtest_2022()  # 验证历史表现
    predictor.predict_2026()   # 预测 2026 所有比赛
"""

import sys
from pathlib import Path
from datetime import datetime, timedelta
from typing import Optional
import json
import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).parent.parent))

from src.betting_system import (
    get_confidence_tier, get_kelly_fraction, get_max_stake_frac,
    ConfidenceTier, KellyCalculator,
)
from config import RAW_DIR


# ═══════════════════════════════════════════════════════════════
# 2026 世界杯 - 小组信息
# ═══════════════════════════════════════════════════════════════

# 小组分组（根据 2025.12 抽签结果）
WC_2026_GROUPS = {
    'A': ['Mexico', 'South Korea', 'South Africa', 'Czechia'],
    'B': ['Canada', 'Bosnia', 'Qatar', 'Switzerland'],
    'C': ['Brazil', 'Morocco', 'Scotland', 'Haiti'],
    'D': ['USA', 'Paraguay', 'Australia', 'Turkey'],
    'E': ['Germany', 'Curacao', 'Ivory Coast', 'Ecuador'],
    'F': ['Netherlands', 'Japan', 'Sweden', 'Tunisia'],
    'G': ['Belgium', 'Iran', 'Egypt', 'New Zealand'],
    'H': ['Spain', 'Cape Verde', 'Saudi Arabia', 'Uruguay'],
    'I': ['France', 'Senegal', 'Iraq', 'Norway'],
    'J': ['Argentina', 'Algeria', 'Austria', 'Jordan'],
    'K': ['Portugal', 'DR Congo', 'Uzbekistan', 'Colombia'],
    'L': ['England', 'Croatia', 'Ghana', 'Panama'],
}

# 世界杯历史冠军赔率参考（2026年5月，来自 FanDuel 等）
WC_2026_WINNER_ODDS = {
    'Spain': 4.30, 'France': 4.70, 'England': 5.50,
    'Brazil': 7.50, 'Argentina': 8.50, 'Germany': 11.00,
    'Portugal': 13.00, 'Netherlands': 15.00, 'Belgium': 19.00,
    'USA': 21.00, 'Croatia': 31.00, 'Uruguay': 31.00,
    'Morocco': 41.00, 'Mexico': 51.00, 'Senegal': 61.00,
    'Colombia': 61.00, 'Japan': 71.00, 'Switzerland': 81.00,
    'Norway': 91.00, 'Austria': 101.00, 'Ecuador': 101.00,
    'Egypt': 121.00, 'Ivory Coast': 151.00, 'Algeria': 201.00,
    'Ghana': 201.00, 'Paraguay': 201.00, 'South Korea': 251.00,
    'Australia': 301.00, 'Scotland': 301.00, 'Iran': 351.00,
    'Tunisia': 401.00, 'Panama': 501.00, 'Canada': 501.00,
    'Saudi Arabia': 501.00, 'Cape Verde': 1001.00, 'New Zealand': 1001.00,
    'Uzbekistan': 1001.00, 'Qatar': 1501.00, 'Jordan': 1501.00,
    'South Africa': 2001.00, 'Haiti': 2001.00, 'Curacao': 5001.00,
    'Czechia': 2501.00, 'Bosnia': 3001.00, 'Sweden': 1501.00,
    'Turkey': 2001.00, 'DR Congo': 5001.00, 'Iraq': 5001.00,
}


# 世界杯历史 Elo 基准（2026年5月，国际比赛 Elo 参考值）
TEAM_ELO = {
    'Argentina': 2084, 'France': 2076, 'Spain': 2068, 'England': 2055,
    'Brazil': 2047, 'Germany': 2038, 'Portugal': 2029, 'Netherlands': 2021,
    'Belgium': 1998, 'Croatia': 1992, 'Uruguay': 1987, 'USA': 1978,
    'Mexico': 1965, 'Japan': 1958, 'Switzerland': 1952, 'Colombia': 1948,
    'Morocco': 1942, 'Senegal': 1935, 'South Korea': 1928, 'Norway': 1925,
    'Austria': 1918, 'Ecuador': 1912, 'Egypt': 1908, 'Ivory Coast': 1898,
    'Australia': 1885, 'Algeria': 1878, 'Scotland': 1872, 'Ghana': 1865,
    'Paraguay': 1858, 'Iran': 1852, 'Canada': 1845, 'Tunisia': 1838,
    'Panama': 1822, 'Saudi Arabia': 1815, 'South Africa': 1802,
    'Qatar': 1795, 'New Zealand': 1788, 'Cape Verde': 1775,
    'Uzbekistan': 1768, 'Jordan': 1755, 'Haiti': 1728, 'Curacao': 1705,
    'Denmark': 1940, 'Italy': 1932, 'Poland': 1905, 'Ukraine': 1892,
    'Turkey': 1882, 'Slovakia': 1865, 'Romania': 1855, 'Kosovo': 1835,
    'Congo': 1750, 'Jamaica': 1742, 'Iraq': 1735, 'Bolivia': 1720,
    'Suriname': 1700, 'New Caledonia': 1680, 'Czechia': 1902,
}


class WCPredictor:
    """世界杯预测器"""

    def __init__(self):
        self.historical_data = {}  # {year: DataFrame}
        self.kelly = KellyCalculator()
        self.player_ratings = self._load_player_ratings()
        
    # ─── 球员数据 ──────────────────────────────────────────────

    def _load_player_ratings(self) -> dict:
        """加载球员评分数据"""
        path = Path(__file__).parent.parent / 'data' / 'wc_player_ratings.json'
        if path.exists():
            with open(path, 'r', encoding='utf-8') as f:
                return json.load(f)
        return {}

    def get_key_players(self, team: str, top_n: int = 5) -> list[dict]:
        """获取球队核心球员（评分最高的 N 人）"""
        players = self.player_ratings.get(team, [])
        return players[:top_n]

    def get_team_avg_rating(self, team: str, top_n: int = 15) -> float:
        """球队平均评分（前 N 名球员）"""
        players = self.player_ratings.get(team, [])
        if not players:
            return 0
        top = players[:top_n]
        return sum(p['rating'] for p in top) / len(top)

    # ─── 数据加载 ──────────────────────────────────────────────

    def load_historical_data(self) -> None:
        """加载历史世界杯数据"""
        for year in ['2014', '2022']:
            path = RAW_DIR / f'WC_{year}.csv'
            if path.exists():
                df = pd.read_csv(path)
                self.historical_data[year] = self._standardize_wc_data(df, year)
                print(f'  WC {year}: {len(self.historical_data[year])} 场比赛')
            else:
                print(f'  WC {year}: 文件不存在')

    def _standardize_wc_data(self, df: pd.DataFrame, year: str) -> pd.DataFrame:
        """标准化世界杯数据"""
        std = pd.DataFrame()
        std['date'] = pd.to_datetime(df['Date'], dayfirst=True, errors='coerce')
        std['home_team'] = df['HomeTeam'].astype(str).str.strip()
        std['away_team'] = df['AwayTeam'].astype(str).str.strip()
        std['home_goals'] = pd.to_numeric(df['FTHG'], errors='coerce')
        std['away_goals'] = pd.to_numeric(df['FTAG'], errors='coerce')
        std['result'] = df['FTR'].str.strip()
        std['year'] = year
        
        # Bet365 odds
        for col in ['B365H', 'B365D', 'B365A']:
            if col in df.columns:
                std[col] = pd.to_numeric(df[col], errors='coerce')
            else:
                std[col] = np.nan
        
        std = std.dropna(subset=['B365H'])
        return std

    # ─── 赔率分析 ──────────────────────────────────────────────

    def analyze_odds_backtest(self, df: pd.DataFrame, label: str = '') -> dict:
        """
        对历史数据做低赔方回测分析
        
        返回各置信度分层的准确率和 ROI
        """
        results = []
        for _, row in df.iterrows():
            if pd.isna(row['B365H']) or pd.isna(row['result']):
                continue
                
            odds = {'H': row['B365H'], 'D': row['B365D'], 'A': row['B365A']}
            fav_outcome = min(odds, key=odds.get)
            
            # 隐含概率（去除抽水）
            total_implied = sum(1.0 / max(o, 1.01) for o in odds.values())
            probs = {k: (1.0 / max(odds[k], 1.01)) / total_implied for k in odds}
            
            max_prob = max(probs.values())
            tier = get_confidence_tier(max_prob)
            fav_odds = odds[fav_outcome]
            correct = (fav_outcome == row['result'])
            
            results.append({
                'tier': tier.value,
                'correct': correct,
                'odds': fav_odds,
                'prob': max_prob,
                'fav': fav_outcome,
                'actual': row['result'],
                'home': row['home_team'],
                'away': row['away_team'],
            })
        
        res_df = pd.DataFrame(results)
        tiers = ['Low', 'Medium', 'High', 'VHigh', 'Elite', 'Max']
        
        summary = {}
        for t in tiers:
            td = res_df[res_df['tier'] == t]
            if len(td) == 0:
                continue
            acc = td['correct'].mean()
            n = len(td)
            
            # 模拟 10 单位固定投注
            won = td[td['correct']]
            lost = td[~td['correct']]
            profit = (won['odds'] - 1).sum() * 10 - len(lost) * 10
            roi = profit / (n * 10) if n > 0 else 0.0
            
            summary[t] = {
                'matches': n,
                'accuracy': f'{acc:.1%}',
                'avg_odds': f'{td["odds"].mean():.2f}',
                'profit': f'{profit:+.0f}',
                'roi': f'{roi:+.2%}',
            }
        
        # 总体统计
        total_correct = res_df['correct'].sum()
        total_matches = len(res_df)
        
        return {
            'label': label,
            'total_matches': total_matches,
            'overall_accuracy': f'{total_correct/total_matches:.1%}' if total_matches > 0 else 'N/A',
            'tier_performance': summary,
            'details': res_df,
        }

    def backtest_2022(self) -> dict:
        """2022 世界杯回测"""
        if '2022' not in self.historical_data:
            self.load_historical_data()
        df = self.historical_data.get('2022')
        if df is None:
            print('No 2022 WC data')
            return {}
        return self.analyze_odds_backtest(df, 'WC 2022')

    def backtest_2014(self) -> dict:
        """2014 世界杯回测"""
        if '2014' not in self.historical_data:
            self.load_historical_data()
        df = self.historical_data.get('2014')
        if df is None:
            print('No 2014 WC data')
            return {}
        return self.analyze_odds_backtest(df, 'WC 2014')

    # ─── 2026 预测 ──────────────────────────────────────────────

    def predict_match(self, home: str, away: str, 
                      b365h: float, b365d: float, b365a: float,
                      neutral_ground: bool = True) -> dict:
        """
        预测一场比赛
        
        参数:
            home, away: 队名
            b365h/b365d/b365a: Bet365 赔率
            neutral_ground: 是否中立场地（世界杯默认是）
            
        返回:
            预测结果字典
        """
        odds = {'H': b365h, 'D': b365d, 'A': b365a}
        
        # 隐含概率
        total = sum(1.0 / max(o, 1.01) for o in odds.values())
        probs = {k: (1.0 / max(odds[k], 1.01)) / total for k in odds}
        
        max_outcome = max(probs, key=probs.get)
        max_prob = probs[max_outcome]
        tier = get_confidence_tier(max_prob)
        
        # Elo 辅助分析（如果有）
        home_elo = TEAM_ELO.get(home, 1800)
        away_elo = TEAM_ELO.get(away, 1800)
        elo_diff = home_elo - away_elo
        
        # 投注决策
        # 世界杯策略：赔率驱动，根据置信度分级直接投注低赔方
        # 不使用 Kelly edge 计算（模型 = 市场本身，edge 永远为 0）
        # 沿用欧冠回测验证的固定投注策略
        # 单位：人民币 ¥，基础单位 = 10¥
        UNIT = 10  # 每注基础单位
        
        # 置信度分级 -> 固定投注额
        tier_stakes = {
            'Max': UNIT * 8,     # 80¥   超高置信度
            'Elite': UNIT * 5,   # 50¥   高置信度
            'VHigh': UNIT * 3,   # 30¥   推荐
            'High': 0,           # 不投
            'Medium': 0,         # 不投
            'Low': 0,            # 不投
        }
        stake = tier_stakes.get(tier.value, 0)
        
        # 计算预期 ROI 参考
        fav_odds_val = odds[max_outcome]
        expected_value = probs[max_outcome] * (fav_odds_val - 1) - (1 - probs[max_outcome]) * 1
        
        return {
            'match': f'{home} vs {away}',
            'home': home,
            'away': away,
            'odds': odds,
            'probs': {k: f'{v:.1%}' for k, v in probs.items()},
            'predicted_outcome': max_outcome,
            'confidence': f'{max_prob:.1%}',
            'tier': tier.value,
            'fav_odds': fav_odds_val,
            'exp_value': f'{expected_value:.2f}' if stake > 0 else '-',
            'elo_diff': elo_diff,
            'suggested_stake': round(stake, 1),
            'stake_unit': f'{int(stake/UNIT)}U' if stake > 0 else '-',
            'analysis': self._get_analysis_text(home, away, max_outcome, max_prob, tier, elo_diff),
            'analysis_data': self._get_analysis_data(home, away, max_outcome, max_prob, odds, elo_diff),
            'key_players_home': self.get_key_players(home, 4),
            'key_players_away': self.get_key_players(away, 4),
            'team_rating_home': round(self.get_team_avg_rating(home), 1),
            'team_rating_away': round(self.get_team_avg_rating(away), 1),
        }

    def _get_analysis_text(self, home: str, away: str, outcome: str,
                           prob: float, tier: ConfidenceTier, elo_diff: float) -> str:
        """生成分析文本"""
        outcome_map = {'H': f'{home} 胜', 'D': '平局', 'A': f'{away} 胜'}
        outcome_str = outcome_map[outcome]
        
        parts = [f'预测: {outcome_str} (置信度 {prob:.0%})']
        
        if tier.value == 'Elite':
            parts.append('[**] 高置信度推荐')
        elif tier.value == 'VHigh':
            parts.append('[**] 推荐投注')
        elif tier.value == 'High':
            parts.append('[*] 谨慎关注')
        elif tier.value == 'Max':
            parts.append('[*] 超高置信度')
        
        if abs(elo_diff) > 50:
            stronger = home if elo_diff > 0 else away
            parts.append(f'Elo 评级: {stronger} 领先 {abs(elo_diff)} 分')
        
        # 球员实力分析
        h_rating = self.get_team_avg_rating(home)
        a_rating = self.get_team_avg_rating(away)
        if h_rating > 0 and a_rating > 0:
            diff = h_rating - a_rating
            if abs(diff) > 3:
                stronger = home if diff > 0 else away
                parts.append(f'阵容评级: {stronger} 平均评分 {abs(diff):.0f} 分领先')
                # 核心球员
                key_h = self.get_key_players(home, 2)
                key_a = self.get_key_players(away, 2)
                if key_h and key_h[0]['rating'] >= 85:
                    parts.append(f'{home} 核心: {key_h[0]["name"]}({key_h[0]["rating"]})')
                if key_a and key_a[0]['rating'] >= 85:
                    parts.append(f'{away} 核心: {key_a[0]["name"]}({key_a[0]["rating"]})')
    
        return ' | '.join(parts)

    def _get_analysis_data(self, home, away, outcome, prob, odds, elo_diff) -> dict:
        """返回结构化分析数据"""
        h_rating = self.get_team_avg_rating(home)
        a_rating = self.get_team_avg_rating(away)
        factors = []
        
        # Factor 1: Market odds
        factors.append({
            'label': '市场赔率',
            'detail': f'隐含 {home} {prob:.0%} 胜率',
            'impact': 'high',
        })
        
        # Factor 2: Elo
        if abs(elo_diff) > 30:
            stronger = home if elo_diff > 0 else away
            factors.append({
                'label': 'Elo 实力差',
                'detail': f'{stronger} 领先 {abs(elo_diff)} 分',
                'impact': 'medium' if abs(elo_diff) < 100 else 'high',
            })
        
        # Factor 3: Squad strength
        if h_rating > 0 and a_rating > 0:
            diff = h_rating - a_rating
            if abs(diff) > 2:
                stronger = home if diff > 0 else away
                factors.append({
                    'label': '阵容深度',
                    'detail': f'{stronger} 球员平均评分 {abs(diff):.1f} 分领先',
                    'impact': 'medium' if abs(diff) < 5 else 'high',
                })
        
        return {
            'prediction': {'H': f'{home} 胜', 'D': '平局', 'A': f'{away} 胜'}.get(outcome, '?'),
            'confidence_pct': round(prob * 100, 1),
            'factors': factors,
            'team_ratings': {
                home: h_rating,
                away: a_rating,
            }
        }

    def predict_2026_group_stage(self, matches: list[dict]) -> list[dict]:
        """
        预测 2026 小组赛
        
        matches: [{home, away, b365h, b365d, b365a}, ...]
        """
        results = []
        for m in matches:
            r = self.predict_match(
                m['home'], m['away'],
                m['b365h'], m['b365d'], m['b365a']
            )
            r['group'] = m.get('group', '?')
            r['date'] = m.get('date', '?')
            results.append(r)
        return results

    # ─── 输出 ──────────────────────────────────────────────────

    def print_backtest_summary(self, result: dict):
        """打印回测结果"""
        if not result:
            return
            
        print(f'\n{"="*60}')
        print(f'  {result.get("label", "回测")}')
        print(f'{"="*60}')
        print(f'  总场次: {result["total_matches"]}')
        print(f'  总体准确率: {result["overall_accuracy"]}')
        
        tp = result.get('tier_performance', {})
        if tp:
            print(f'\n  {"分层":10s} {"场次":>5s} {"准确率":>8s} {"赔率":>6s} {"ROI":>8s}')
            print(f'  {"─"*40}')
            for t in ['Low', 'Medium', 'High', 'VHigh', 'Elite', 'Max']:
                if t in tp:
                    d = tp[t]
                    print(f'  {t:10s} {d["matches"]:>5d} {d["accuracy"]:>8s} '
                          f'{d["avg_odds"]:>6s} {d["roi"]:>8s}')

    def print_predictions(self, predictions: list[dict]):
        """打印比赛预测"""
        print(f'\n{"="*80}')
        print('  世界杯 2026 比赛预测')
        print(f'{"="*80}')
        print(f'  {"日期":10s} {"小组":4s} {"主队":16s} {"客队":16s} {"预测":6s} {"置信度":8s} {"分级":8s} {"建议仓位":>10s}')
        print(f'  {"─"*80}')
        
        for p in predictions:
            date = p.get('date', '????-??-??')[5:10] if len(p.get('date','')) >= 10 else '??-??'
            group = p.get('group', '?')
            home = p['home'][:14]
            away = p['away'][:14]
            outcome = {'H': '主胜', 'D': '平局', 'A': '客胜'}.get(p['predicted_outcome'], '?')
            conf = p['confidence']
            tier = p['tier']
            stake = p.get('suggested_stake', 0)
            fav_odds = p.get('fav_odds', 0)
            stake_str = f'${stake:.0f}' if stake > 0 else '-'
            
            print(f'  {date:10s} {group:3s} {home:16s} {away:16s} '
                  f'{outcome:6s} {conf:8s} {tier:8s} {fav_odds:<6.2f} {stake_str:>10s}')


# ═══════════════════════════════════════════════════════════════
# 命令行入口
# ═══════════════════════════════════════════════════════════════

if __name__ == '__main__':
    predictor = WCPredictor()
    
    # 1) 加载历史数据
    print('\n加载历史数据...')
    predictor.load_historical_data()
    
    # 2) 2022 回测
    print('\n2022 世界杯回测...')
    r22 = predictor.backtest_2022()
    predictor.print_backtest_summary(r22)
    
    # 3) 2014 回测（如果有）
    if '2014' in predictor.historical_data:
        print('\n2014 世界杯回测...')
        r14 = predictor.backtest_2014()
        predictor.print_backtest_summary(r14)
