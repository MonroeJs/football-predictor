"""
J1 联赛回测 — v1 特征（J1 没有统计数据）
"""
import sys, warnings
warnings.filterwarnings('ignore')
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

import pandas as pd
import numpy as np
from src.leagues.j_league import JLeague
from src.ml_models import FootballPredictor
from src.features import build_features
from src.betting_system import run_tiered_backtest

print('=' * 60)
print('  J1 League Backtest (v1 features)')
print('=' * 60)

# 1. Load
print('\nLoading J1 data...')
league = JLeague()
df = league.load_matches()
print(f'  Total matches: {len(df)}')
print(f'  Has odds: {df["B365H"].notna().sum()}')

# 2. Build v1 features (don't need stats)
print('\nBuilding v1 features...')
df_feat = build_features(df)
# The v1 features function may also need league column
if 'league' not in df_feat.columns:
    df_feat['league'] = 'J1'

# Find feature columns (numeric, exclude result/goals)
feature_cols = [c for c in df_feat.columns if c.startswith(('form_', 'elo_', 'gd_', 'avg_', 'home_', 'away_')) 
                and c not in ('home_goals', 'away_goals')]

# Get target
from src.features import get_target
y, df_feat = get_target(df_feat)

# Filter to features that exist
feature_cols = [c for c in feature_cols if c in df_feat.columns]
print(f'  Features: {len(feature_cols)}')
print(f'  Samples: {len(df_feat)}')

if len(df_feat) < 100 or len(feature_cols) < 3:
    print('Not enough data for ML')
    sys.exit(1)

X = df_feat[feature_cols].fillna(0).values
# Use recent data for prediction, train on older data
split = int(len(X) * 0.8)
X_train, X_test = X[:split], X[split:]
y_train, y_test = y[:split], y[split:]

print(f'  Train: {len(X_train)}, Test: {len(X_test)}')

# 3. Train
print('\nTraining CatBoost...')
model = FootballPredictor(model_type='catboost')
model.fit(X_train, y_train)

# 4. Test accuracy
test_probs = model.predict_proba(X_test)
test_preds = np.argmax(test_probs, axis=1)
acc = np.mean(test_preds == y_test)
print(f'  Test accuracy: {acc:.1%}')

# 5. Backtest
print('\nBacktesting...')
results = run_tiered_backtest(df_feat, model)
if results:
    s = results.get('summary', {})
    print(f'  Total: {s.get("total_matches", "N/A")}')
    print(f'  Accuracy: {s.get("overall_accuracy", "N/A")}')
    for t in ['VHigh', 'Elite', 'Max']:
        tp = s.get('tier_performance', {}).get(t, {})
        if tp:
            print(f'  {t:10s}: {tp["matches"]:>3d} | {tp["accuracy"]} | {tp["roi"]}')
else:
    print('  No results')
