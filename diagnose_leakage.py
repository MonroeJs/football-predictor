"""
诊断：验证特征的正确性和数据泄露
"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.absolute()))

import pandas as pd
import numpy as np
from sklearn.ensemble import RandomForestClassifier
from src.data_loader import download_league_data, standardize_dataframe
from src.features_v2 import build_features_v2, get_feature_columns_v2

# 1. 加载 EPL
raw = download_league_data("EPL")
std = standardize_dataframe(raw)
df = build_features_v2(std)

train = df[df["season_code"] < "2425"].copy()
test = df[df["season_code"] >= "2425"].copy()

print(f"Train: {len(train)}, Test: {len(test)}")
print(f"Train date range: {train['date'].min()} to {train['date'].max()}")
print(f"Test date range: {test['date'].min()} to {test['date'].max()}")

# 2. 特征列
features = get_feature_columns_v2()
available = [c for c in features if c in df.columns]
print(f"Total features available: {len(available)}")

X_train = train[available].fillna(0).values
y_train = train["result"].map({"H": 0, "D": 1, "A": 2}).values
X_test = test[available].fillna(0).values
y_test = test["result"].map({"H": 0, "D": 1, "A": 2}).values

# 3. RF with all features
rf = RandomForestClassifier(n_estimators=100, max_depth=8, random_state=42, n_jobs=-1)
rf.fit(X_train, y_train)
y_pred = rf.predict(X_test)
print(f"\nRF accuracy (all features): {np.mean(y_pred == y_test):.4f}")

# 4. Per-class accuracy
for i, label in enumerate(["H", "D", "A"]):
    mask = y_test == i
    if mask.sum() > 0:
        acc = (y_pred[mask] == i).sum() / mask.sum()
        print(f"  {label}: {acc:.4f} ({mask.sum()} matches)")

# 5. Without odds features
non_odds = [c for c in available if "odds" not in c.lower()]
X_train_no = train[non_odds].fillna(0).values
X_test_no = test[non_odds].fillna(0).values
rf2 = RandomForestClassifier(n_estimators=100, max_depth=8, random_state=42, n_jobs=-1)
rf2.fit(X_train_no, y_train)
y_pred2 = rf2.predict(X_test_no)
print(f"\nRF accuracy (w/o odds): {np.mean(y_pred2 == y_test):.4f}")

# 6. Feature importance (top 20)
fi = sorted(zip(available, rf.feature_importances_), key=lambda x: -x[1])
print("\nTop 20 features:")
for f, imp in fi[:20]:
    print(f"  {f}: {imp:.4f}")
