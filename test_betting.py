"""Quick smoke test for betting system"""
import sys, warnings
warnings.filterwarnings('ignore')
sys.path.insert(0, '.')

import numpy as np
from src.betting_system import *

# Create a betting system
cbs = ConfidenceBettingSystem(initial_bankroll=1000, min_edge=0.03, use_kelly=True)

rng = np.random.default_rng(42)

for i in range(100):
    confidence = rng.uniform(0.33, 0.80)
    if rng.random() < 0.35:
        probs = [confidence, (1-confidence)*0.4, (1-confidence)*0.6]
    else:
        probs = [confidence, (1-confidence)*0.5, (1-confidence)*0.5]
    rng.shuffle(probs)

    model_probs = {'H': probs[0], 'D': probs[1], 'A': probs[2]}
    pred = max(model_probs, key=model_probs.get)

    if rng.random() < 0.4:
        odds = {k: 1.0 / max(0.33, v*0.85) for k, v in model_probs.items()}
    else:
        odds = {k: 1.0 / max(0.33, v*1.1) for k, v in model_probs.items()}

    actual = pred if rng.random() < 0.52 else rng.choice(['H','D','A'])

    decision = cbs.evaluate_bet(
        model_probs, odds,
        f'Match {i}', 'EPL', '2025-01-01', actual
    )
    cbs.settle_bet(decision)

result = cbs.get_betting_stats()
s = result.summary
print('=== Mock Betting Test ===')
print(f'Matches: {s["total_matches"]}')
print(f'Bets: {s["total_bets"]} ({s["bet_rate"]})')
print(f'Win rate: {s["win_rate"]}')
print(f'ROI: {s["roi"]}')
print(f'Drawdown: {s["drawdown"]}')
print()
print('Tier Prediction Accuracy:')
for t, a in sorted(result.tier_prediction_accuracy.items()):
    print(f'  {t:12s}: {a:.1%}')
print()
print('Tier Betting Stats:')
for t in ['Max', 'Elite', 'VHigh', 'High', 'Medium', 'Low']:
    if t in result.tier_stats:
        ts = result.tier_stats[t]
        print(f'  {t:12s}: {ts.total_bets:>3d} bets, {ts.accuracy:.1%} win, {ts.roi:.2%} ROI')
print()
print('Basic system test PASSED!')
