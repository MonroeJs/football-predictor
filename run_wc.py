#!/usr/bin/env python3
"""
世界杯 2026 预测系统 - 运行器

功能:
  1. 历史世界杯回测（验证低赔方+置信度分层策略）
  2. 2026 世界杯比赛预测（需手动输入赔率，或从文件加载）
  3. 小组赛/淘汰赛逐场分析 + 投注建议

使用方式:
    python run_wc.py                    # 回测 + 回测结果展示
    python run_wc.py --predict          # 预测模式（需有赔率数据）
    python run_wc.py --backtest-2022    # 仅回测 2022
    python run_wc.py --full             # 完整分析
    python run_wc.py --export           # 导出结果到 JSON
"""

import sys, warnings, json, argparse
warnings.filterwarnings('ignore')

from pathlib import Path
from datetime import datetime
import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).parent.absolute()))
from src.wc_predictor import WCPredictor
from src.betting_system import (
    KellyCalculator, get_confidence_tier,
    ConfidenceTier, BettingResult,
)

SEP = '=' * 60

# ═══════════════════════════════════════════════════════════════
# 2026 世界杯小组赛赛程 + 赔率（开赛前需填入实时赔率）
# 赔率来源：Bet365 / FanDuel / football-data.co.uk (fixtures.csv)
# ═══════════════════════════════════════════════════════════════

# 小组赛赛程框架 - 比赛时间按 US/Eastern 时间
# 需在开赛前填入实时赔率（B365H/B365D/B365A）
WC_2026_SCHEDULE = [
    {'date': '2026-06-11', 'group': 'A', 'home': 'Mexico', 'away': 'South Africa'},
    {'date': '2026-06-11', 'group': 'A', 'home': 'South Korea', 'away': 'Czechia'},
    {'date': '2026-06-18', 'group': 'A', 'home': 'Czechia', 'away': 'South Africa'},
    {'date': '2026-06-18', 'group': 'A', 'home': 'Mexico', 'away': 'South Korea'},
    {'date': '2026-06-24', 'group': 'A', 'home': 'Czechia', 'away': 'Mexico'},
    {'date': '2026-06-24', 'group': 'A', 'home': 'South Africa', 'away': 'South Korea'},
    {'date': '2026-06-12', 'group': 'B', 'home': 'Canada', 'away': 'Bosnia'},
    {'date': '2026-06-13', 'group': 'B', 'home': 'Qatar', 'away': 'Switzerland'},
    {'date': '2026-06-18', 'group': 'B', 'home': 'Switzerland', 'away': 'Bosnia'},
    {'date': '2026-06-18', 'group': 'B', 'home': 'Canada', 'away': 'Qatar'},
    {'date': '2026-06-24', 'group': 'B', 'home': 'Switzerland', 'away': 'Canada'},
    {'date': '2026-06-24', 'group': 'B', 'home': 'Bosnia', 'away': 'Qatar'},
    {'date': '2026-06-13', 'group': 'C', 'home': 'Brazil', 'away': 'Morocco'},
    {'date': '2026-06-13', 'group': 'C', 'home': 'Haiti', 'away': 'Scotland'},
    {'date': '2026-06-19', 'group': 'C', 'home': 'Scotland', 'away': 'Morocco'},
    {'date': '2026-06-19', 'group': 'C', 'home': 'Brazil', 'away': 'Haiti'},
    {'date': '2026-06-24', 'group': 'C', 'home': 'Scotland', 'away': 'Brazil'},
    {'date': '2026-06-24', 'group': 'C', 'home': 'Morocco', 'away': 'Haiti'},
    {'date': '2026-06-12', 'group': 'D', 'home': 'USA', 'away': 'Paraguay'},
    {'date': '2026-06-13', 'group': 'D', 'home': 'Australia', 'away': 'Turkey'},
    {'date': '2026-06-19', 'group': 'D', 'home': 'Turkey', 'away': 'Paraguay'},
    {'date': '2026-06-19', 'group': 'D', 'home': 'USA', 'away': 'Australia'},
    {'date': '2026-06-25', 'group': 'D', 'home': 'Turkey', 'away': 'USA'},
    {'date': '2026-06-25', 'group': 'D', 'home': 'Paraguay', 'away': 'Australia'},
    {'date': '2026-06-14', 'group': 'E', 'home': 'Germany', 'away': 'Curacao'},
    {'date': '2026-06-14', 'group': 'E', 'home': 'Ivory Coast', 'away': 'Ecuador'},
    {'date': '2026-06-20', 'group': 'E', 'home': 'Germany', 'away': 'Ivory Coast'},
    {'date': '2026-06-20', 'group': 'E', 'home': 'Ecuador', 'away': 'Curacao'},
    {'date': '2026-06-25', 'group': 'E', 'home': 'Ecuador', 'away': 'Germany'},
    {'date': '2026-06-25', 'group': 'E', 'home': 'Curacao', 'away': 'Ivory Coast'},
    {'date': '2026-06-14', 'group': 'F', 'home': 'Netherlands', 'away': 'Japan'},
    {'date': '2026-06-14', 'group': 'F', 'home': 'Sweden', 'away': 'Tunisia'},
    {'date': '2026-06-20', 'group': 'F', 'home': 'Netherlands', 'away': 'Sweden'},
    {'date': '2026-06-20', 'group': 'F', 'home': 'Tunisia', 'away': 'Japan'},
    {'date': '2026-06-25', 'group': 'F', 'home': 'Tunisia', 'away': 'Netherlands'},
    {'date': '2026-06-25', 'group': 'F', 'home': 'Japan', 'away': 'Sweden'},
    {'date': '2026-06-15', 'group': 'G', 'home': 'Belgium', 'away': 'Egypt'},
    {'date': '2026-06-15', 'group': 'G', 'home': 'Iran', 'away': 'New Zealand'},
    {'date': '2026-06-21', 'group': 'G', 'home': 'Belgium', 'away': 'Iran'},
    {'date': '2026-06-21', 'group': 'G', 'home': 'New Zealand', 'away': 'Egypt'},
    {'date': '2026-06-26', 'group': 'G', 'home': 'New Zealand', 'away': 'Belgium'},
    {'date': '2026-06-26', 'group': 'G', 'home': 'Egypt', 'away': 'Iran'},
    {'date': '2026-06-15', 'group': 'H', 'home': 'Spain', 'away': 'Cape Verde'},
    {'date': '2026-06-15', 'group': 'H', 'home': 'Saudi Arabia', 'away': 'Uruguay'},
    {'date': '2026-06-21', 'group': 'H', 'home': 'Spain', 'away': 'Saudi Arabia'},
    {'date': '2026-06-21', 'group': 'H', 'home': 'Uruguay', 'away': 'Cape Verde'},
    {'date': '2026-06-26', 'group': 'H', 'home': 'Uruguay', 'away': 'Spain'},
    {'date': '2026-06-26', 'group': 'H', 'home': 'Cape Verde', 'away': 'Saudi Arabia'},
    {'date': '2026-06-16', 'group': 'I', 'home': 'France', 'away': 'Senegal'},
    {'date': '2026-06-16', 'group': 'I', 'home': 'Iraq', 'away': 'Norway'},
    {'date': '2026-06-22', 'group': 'I', 'home': 'France', 'away': 'Iraq'},
    {'date': '2026-06-22', 'group': 'I', 'home': 'Norway', 'away': 'Senegal'},
    {'date': '2026-06-26', 'group': 'I', 'home': 'Norway', 'away': 'France'},
    {'date': '2026-06-26', 'group': 'I', 'home': 'Senegal', 'away': 'Iraq'},
    {'date': '2026-06-16', 'group': 'J', 'home': 'Argentina', 'away': 'Algeria'},
    {'date': '2026-06-16', 'group': 'J', 'home': 'Austria', 'away': 'Jordan'},
    {'date': '2026-06-22', 'group': 'J', 'home': 'Argentina', 'away': 'Austria'},
    {'date': '2026-06-22', 'group': 'J', 'home': 'Jordan', 'away': 'Algeria'},
    {'date': '2026-06-27', 'group': 'J', 'home': 'Jordan', 'away': 'Argentina'},
    {'date': '2026-06-27', 'group': 'J', 'home': 'Algeria', 'away': 'Austria'},
    {'date': '2026-06-17', 'group': 'K', 'home': 'Portugal', 'away': 'DR Congo'},
    {'date': '2026-06-17', 'group': 'K', 'home': 'Uzbekistan', 'away': 'Colombia'},
    {'date': '2026-06-23', 'group': 'K', 'home': 'Portugal', 'away': 'Uzbekistan'},
    {'date': '2026-06-23', 'group': 'K', 'home': 'Colombia', 'away': 'DR Congo'},
    {'date': '2026-06-27', 'group': 'K', 'home': 'Colombia', 'away': 'Portugal'},
    {'date': '2026-06-27', 'group': 'K', 'home': 'DR Congo', 'away': 'Uzbekistan'},
    {'date': '2026-06-17', 'group': 'L', 'home': 'England', 'away': 'Croatia'},
    {'date': '2026-06-17', 'group': 'L', 'home': 'Ghana', 'away': 'Panama'},
    {'date': '2026-06-23', 'group': 'L', 'home': 'England', 'away': 'Ghana'},
    {'date': '2026-06-23', 'group': 'L', 'home': 'Panama', 'away': 'Croatia'},
    {'date': '2026-06-27', 'group': 'L', 'home': 'Panama', 'away': 'England'},
    {'date': '2026-06-27', 'group': 'L', 'home': 'Croatia', 'away': 'Ghana'},
]


def load_or_create_odds_csv(schedule: list[dict]) -> list[dict]:
    """
    尝试从 odds_csv 加载赔率，否则返回空赔率列表
    用户可在 run_wc_odds.csv 中填入 Bet365 赔率
    """
    odds_path = Path(__file__).parent / 'run_wc_odds.csv'
    
    if odds_path.exists():
        print(f'  从 {odds_path} 加载赔率...')
        odds_df = pd.read_csv(odds_path)
        # 匹配赛程填充赔率
        odds_map = {}
        for _, row in odds_df.iterrows():
            key = (row['home'].strip(), row['away'].strip())
            odds_map[key] = {
                'b365h': float(row.get('B365H', 0)),
                'b365d': float(row.get('B365D', 0)),
                'b365a': float(row.get('B365A', 0)),
            }
        
        filled = 0
        for m in schedule:
            key = (m['home'], m['away'])
            if key in odds_map:
                m['b365h'] = odds_map[key]['b365h']
                m['b365d'] = odds_map[key]['b365d']
                m['b365a'] = odds_map[key]['b365a']
                filled += 1
        
        print(f'  已填入赔率: {filled}/{len(schedule)} 场')
        if filled < len(schedule):
            print(f'  缺少 {len(schedule) - filled} 场赔率，将在预测中跳过')
    else:
        print(f'  赔率文件 {odds_path} 不存在')
        print(f'  创建模板文件...')
        template = pd.DataFrame(schedule)
        template['B365H'] = 0.0
        template['B365D'] = 0.0
        template['B365A'] = 0.0
        template.to_csv(odds_path, index=False)
        print(f'  模板已创建: {odds_path}')
        print(f'  请在文件填入 Bet365 赔率后重新运行')
    
    return schedule


def run_historical_backtest(predictor: WCPredictor) -> None:
    """运行历史世界杯回测"""
    print(f'\n{SEP}')
    print('  世界杯历史回测')
    print(f'{SEP}')
    
    predictor.load_historical_data()
    
    # 2022 回测
    print(f'\n{SEP}')
    r22 = predictor.backtest_2022()
    predictor.print_backtest_summary(r22)
    
    # 2014 回测
    if '2014' in predictor.historical_data:
        print(f'\n{SEP}')
        r14 = predictor.backtest_2014()
        predictor.print_backtest_summary(r14)
    
    # 汇总对比
    print(f'\n{SEP}')
    print('  历史回测汇总')
    print(f'{SEP}')
    
    for year in ['2022', '2014']:
        if year in predictor.historical_data:
            r = predictor.analyze_odds_backtest(predictor.historical_data[year], f'WC {year}')
            tp = r['tier_performance']
            print(f'\n  WC {year}: 总场次 {r["total_matches"]} 总体准确率 {r["overall_accuracy"]}')
            for t in ['VHigh', 'Elite', 'Max']:
                if t in tp:
                    d = tp[t]
                    print(f'    {t:10s}: {d["matches"]:>3d} 场 | 准确率 {d["accuracy"]} | ROI {d["roi"]}')


def run_predictions(predictor: WCPredictor, schedule: list[dict],
                    use_odds_file: bool = True) -> list[dict]:
    """运行 2026 WC 预测"""
    print(f'\n{SEP}')
    print('  2026 世界杯预测')
    print(f'{SEP}')
    
    if use_odds_file:
        schedule = load_or_create_odds_csv(schedule)
    
    # 过滤有赔率的比赛
    valid_matches = [m for m in schedule if m.get('b365h', 0) > 0.1]
    
    if not valid_matches:
        print('\n  [!] 没有可预测的比赛（缺少赔率）')
        print('  请在 run_wc_odds.csv 中填入 Bet365 赔率后重新运行')
        print('  或使用 --no-odds 参数跳过赔率检查\n')
        
        # 即使没有赔率，也用 Elo 做初步分析
        print('  使用 Elo 评级进行初步分析...')
        for m in schedule:
            home = m['home']
            away = m['away']
            from src.wc_predictor import TEAM_ELO
            home_elo = TEAM_ELO.get(home, 1800)
            away_elo = TEAM_ELO.get(away, 1800)
            m['elo_diff'] = home_elo - away_elo
        return []
    
    predictions = predictor.predict_2026_group_stage(valid_matches)
    predictor.print_predictions(predictions)
    
    # 按置信度分层统计
    print(f'\n{"─"*80}')
    print('  投注策略建议')
    print(f'{"─"*80}')
    
    tiers = {}
    for p in predictions:
        t = p['tier']
        if t not in tiers:
            tiers[t] = []
        tiers[t].append(p)
    
    for t in ['Max', 'Elite', 'VHigh', 'High', 'Medium', 'Low']:
        if t in tiers:
            stake_count = sum(1 for p in tiers[t] if p.get('suggested_stake', 0) > 0)
            print(f'  {t:10s}: {len(tiers[t]):>3d} 场比赛 | {stake_count} 场建议投注')
    
    return predictions


def main():
    parser = argparse.ArgumentParser(description='世界杯 2026 预测系统')
    parser.add_argument('--backtest-2022', action='store_true', help='仅回测 2022')
    parser.add_argument('--predict', action='store_true', help='预测模式')
    parser.add_argument('--full', action='store_true', help='完整分析')
    parser.add_argument('--no-odds', action='store_true', help='不加载赔率文件')
    parser.add_argument('--export', action='store_true', help='导出结果到 JSON')
    args = parser.parse_args()
    
    predictor = WCPredictor()
    
    # 默认行为：回测
    if not any([args.backtest_2022, args.predict, args.full]):
        args.full = True
    
    if args.backtest_2022:
        run_historical_backtest(predictor)
        return
    
    if args.predict or args.full:
        predictions = run_predictions(
            predictor, WC_2026_SCHEDULE,
            use_odds_file=not args.no_odds
        )
        
        if args.export and predictions:
            output_path = Path(__file__).parent / 'output' / 'wc_2026_predictions.json'
            output_path.parent.mkdir(exist_ok=True)
            with open(output_path, 'w', encoding='utf-8') as f:
                json.dump(predictions, f, ensure_ascii=False, indent=2)
            print(f'\n  结果已导出: {output_path}')
    
    if args.full:
        run_historical_backtest(predictor)


if __name__ == '__main__':
    main()
