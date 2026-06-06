"""
LaLiga 滑动窗口回测
"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.absolute()))

from src.data_loader import download_league_data, standardize_dataframe
from src.features import build_features
from src.backtest import sliding_window_backtest
from config import LEAGUES

LEAGUE = "LaLiga"
print(f"Running backtest for {LEAGUE} ({LEAGUES[LEAGUE]['name']})")

raw = download_league_data(LEAGUE, force=False)
std = standardize_dataframe(raw)
df = build_features(std)

result = sliding_window_backtest(
    df,
    train_window=380,
    test_window=38,
    step_size=76,
    checkpoint_path="data/processed/bt_laliga_cp.json",
)

print()
print("### LaLiga 回测结果 ###")
print(f"总场次: {result.total_matches}")
print(f"泊松准确率: {result.poisson_accuracy:.2%}")
print(f"ML准确率:   {result.ml_accuracy:.2%}")
print(f"模拟ROI:    {result.simulated_roi:.2%}")
print()
print("按结果分类(泊松):")
for pred, actuals in result.poisson_confusion.items():
    total = sum(actuals.values())
    print(f"  预测{pred}: {actuals}")
print()
print("按结果分类(ML):")
for pred, actuals in result.ml_confusion.items():
    total = sum(actuals.values())
    print(f"  预测{pred}: {actuals}")
