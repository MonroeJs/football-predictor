"""
全局配置 — 联赛、数据源路径、模型参数
"""

import os
from pathlib import Path

# 项目根目录
ROOT_DIR = Path(__file__).parent.absolute()
DATA_DIR = ROOT_DIR / "data"
RAW_DIR = DATA_DIR / "raw"
PROCESSED_DIR = DATA_DIR / "processed"

# 确保目录存在
for d in [RAW_DIR, PROCESSED_DIR]:
    d.mkdir(parents=True, exist_ok=True)

# 五大联赛代码映射 (football-data.co.uk 格式)
LEAGUES = {
    "EPL": {"code": "E0", "name": "Premier League", "country": "England"},
    "LaLiga": {"code": "SP1", "name": "La Liga", "country": "Spain"},
    "SerieA": {"code": "I1", "name": "Serie A", "country": "Italy"},
    "Bundesliga": {"code": "D1", "name": "Bundesliga", "country": "Germany"},
    "Ligue1": {"code": "F1", "name": "Ligue 1", "country": "France"},
}

# football-data.co.uk URL 模板
# {code} 如 E0, SP1; {season} 如 2425
FD_URL_TEMPLATE = "https://www.football-data.co.uk/mmz4281/{season}/{code}.csv"

# 当前赛季代码 (2025-26 赛季 → 2526)
CURRENT_SEASON_CODE = "2526"

# 近10个赛季范围 (2016/17 ~ 2025/26)
SEASON_CODES = [
    "1617", "1718", "1819", "1920", "2021",
    "2122", "2223", "2324", "2425", "2526",
]

# 用于训练的赛季范围
TRAIN_SEASONS = SEASON_CODES[:]

# 特征工程参数
FEATURE_CONFIG = {
    "recent_games": [5, 10],  # 近5场和近10场
    "elo_default_rating": 1500,
    "elo_k_factor": 24,
    "min_matches_for_features": 5,  # 少于5场不生成特征
}

# 回测参数
BACKTEST_CONFIG = {
    "train_window": 380,   # 约1个赛季
    "test_window": 38,     # 约1轮
    "step_size": 76,       # 每4轮步进一次
    "min_train_matches": 100,
}

# 模型参数
ML_CONFIG = {
    "random_forest": {
        "n_estimators": 300,
        "max_depth": 12,
        "min_samples_split": 8,
        "min_samples_leaf": 4,
        "random_state": 42,
        "n_jobs": -1,
        "class_weight": "balanced",
    },
    "logistic_regression": {
        "max_iter": 1000,
        "random_state": 42,
        "class_weight": "balanced",
    },
    "gradient_boosting": {
        "n_estimators": 200,
        "max_depth": 6,
        "learning_rate": 0.05,
        "random_state": 42,
        "subsample": 0.8,
    },
    "xgboost": {
        "n_estimators": 500,
        "max_depth": 6,
        "learning_rate": 0.03,
        "subsample": 0.8,
        "colsample_bytree": 0.8,
        "eval_metric": "mlogloss",
        "random_state": 42,
        "verbosity": 0,
    },
    "lightgbm": {
        "n_estimators": 500,
        "max_depth": 8,
        "learning_rate": 0.03,
        "num_leaves": 31,
        "subsample": 0.8,
        "colsample_bytree": 0.8,
        "reg_alpha": 0.1,
        "reg_lambda": 0.1,
        "min_child_samples": 10,
        "class_weight": "balanced",
        "random_state": 42,
        "verbose": -1,
    },
    "catboost": {
        "iterations": 500,
        "depth": 6,
        "learning_rate": 0.03,
        "l2_leaf_reg": 3,
        "border_count": 128,
        "random_seed": 42,
        "verbose": False,
    },
    "test_size": 0.2,
    "random_state": 42,
}

# ── 训练配置 ──
MODELS_DIR = ROOT_DIR / "models"
TRAIN_CONFIG = {
    "min_train_seasons": 3,
    "ensemble": ["random_forest", "logistic_regression", "gradient_boosting", "xgboost", "lightgbm", "catboost"],
}

# ── 博彩赔率相关列（来自 football-data.co.uk）──
# 保留的关键赔率列（关闭赔率为主，开盘赔率标记开=open）
ODDS_COLUMNS = {
    "close": ["B365H", "B365D", "B365A", "BWH", "BWD", "BWA",
              "WHH", "WHD", "WHA", "PSH", "PSD", "PSA",
              "MaxH", "MaxD", "MaxA", "AvgH", "AvgD", "AvgA"],
    "open": ["B365CH", "B365CD", "B365CA", "BWCH", "BWCD", "BWCA",
             "PSCH", "PSCD", "PSCA", "MaxCH", "MaxCD", "MaxCA",
             "AvgCH", "AvgCD", "AvgCA"],
}
