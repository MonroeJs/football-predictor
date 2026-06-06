"""
J1 联赛回测 — 使用现有 ML 流水线
"""
import sys, warnings
warnings.filterwarnings('ignore')
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

import pandas as pd
import numpy as np
from src.leagues.j_league import JLeague
from src.ml_models import FootballPredictor
from src.features_v2 import build_features_v2, get_feature_columns_v2
from src.betting_system import run_tiered_backtest

print('=' * 60)
print('  J1 League Backtest')
print('=' * 60)

# 1. Load J1 data
print('\nLoading J1 data...')
league = JLeague()
df = league.load_matches()
print(f'  Total matches: {len(df)}')

# Check data quality
print(f'  Seasons: {sorted(df["season"].unique())}')
print(f'  Teams: {df["home_team"].nunique()}')
print(f'  Has odds: {df["B365H"].notna().sum()}')

# 2. Build features
print('\nBuilding features...')
X_train, y_train, feature_cols = build_features_v2(df)

if X_train is not None:
    print(f'  Training samples: {len(X_train)}')
    print(f'  Features: {len(feature_cols)}')
    
    # Check class balance
    classes, counts = np.unique(y_train, return_counts=True)
    for c, n in zip(classes, counts):
        print(f'  Class {c}: {n} ({n/len(y_train)*100:.1f}%)')
    
    # 3. Train model
    print('\nTraining CatBoost model...')
    model = FootballPredictor(model_type='catboost')
    model.fit(X_train, y_train)
    
    # 4. Cross-validation
    print('\nCross-validation...')
    cv_results = model.cross_validate(X_train, y_train, cv=3)
    mean_acc = np.mean([r['accuracy'] for r in cv_results]) if cv_results else 0
    print(f'  CV accuracy: {mean_acc:.1%}')
    
    # 5. Backtest
    print('\nRunning betting backtest...')
    results = run_tiered_backtest(df, model)
    
    if results:
        summary = results.get('summary', {})
        print(f'\n  Backtest Results:')
        print(f'  Total matches: {summary.get("total_matches", "N/A")}')
        print(f'  Overall accuracy: {summary.get("overall_accuracy", "N/A")}')
        
        # Tier performance
        tier_perf = summary.get('tier_performance', {})
        for t in ['VHigh', 'Elite', 'Max']:
            if t in tier_perf:
                d = tier_perf[t]
                print(f'  {t:10s}: {d["matches"]:>3d} matches | accuracy {d["accuracy"]} | ROI {d["roi"]}')
    else:
        print('  No backtest results')
else:
    print('  Feature building failed - check data quality')
