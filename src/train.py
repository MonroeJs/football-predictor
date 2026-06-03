"""
训练 Pipeline — 按联赛独立训练模型并持久化

功能:
1. 下载/加载五大联赛数据
2. 按联赛分别提取特征
3. 训练各联赛的 ML 模型（RandomForest, LogisticRegression, GradientBoosting）
4. 保存模型到 models/ 目录
5. 评估每个模型的性能

使用方式:
    python predict.py train
    python predict.py train --league EPL
    python predict.py train --reset
"""

import sys
from pathlib import Path

import pandas as pd
import numpy as np

# 确保项目根目录在路径中
sys.path.insert(0, str(Path(__file__).parent.parent.absolute()))

from config import LEAGUES, TRAIN_SEASONS, MODELS_DIR, RAW_DIR, PROCESSED_DIR
from src.utils import logger
from src.data_loader import download_league_data, standardize_dataframe, load_data
from src.features import build_features
from src.ml_models import (
    FootballPredictor,
    EnsemblePredictor,
    train_per_league as train_all_models,
    load_per_league_models,
)
from src.poisson import calc_attack_defense_strength, predict_match_poisson


def run_training(
    league_key: str | None = None,
    force_download: bool = False,
    save: bool = True,
) -> dict:
    """
    训练指定联赛（或全部五大联赛）的模型

    Args:
        league_key: 联赛代码，None 表示全部
        force_download: 强制重新下载数据
        save: 是否保存模型到文件

    Returns:
        {联赛: {模型类型: 训练结果}}
    """
    all_results = {}
    leagues = [league_key] if league_key else list(LEAGUES.keys())

    for lk in leagues:
        logger.info(f"\n{'='*60}")
        logger.info(f"{lk} ({LEAGUES[lk]['name']}) — 训练开始")
        logger.info(f"{'='*60}")

        # 1. 下载数据
        raw = download_league_data(lk, season_codes=TRAIN_SEASONS, force=force_download)
        if raw.empty:
            logger.warning(f"{lk}: 无数据，跳过")
            continue

        # 2. 标准化
        std = standardize_dataframe(raw)
        logger.info(f"{lk}: 标准化后 {len(std)} 条记录")

        # 3. 特征工程
        df = build_features(std)
        logger.info(f"{lk}: 特征工程后 {len(df)} 条记录")

        if len(df) < 200:
            logger.warning(f"{lk}: 特征后数据不足 ({len(df)} 条)，跳过")
            continue

        # 4. 计算泊松基线参数
        attack, defense, avg_h, avg_a = calc_attack_defense_strength(df)

        # 5. 训练 ML 模型
        models_config = ["random_forest", "logistic_regression", "gradient_boosting"]
        league_models = {}

        for model_type in models_config:
            logger.info(f"  {lk} 训练 {model_type}...")
            predictor = FootballPredictor(model_type=model_type, league=lk)
            train_result = predictor.train(df, use_tscv=True)

            if "error" not in train_result:
                league_models[model_type] = {
                    "predictor": predictor,
                    "result": train_result,
                }
                if save:
                    predictor.save()
            else:
                logger.warning(f"  {lk} {model_type}: {train_result['error']}")

        all_results[lk] = league_models

        # 打印摘要
        print(f"\n  {lk} 训练摘要:")
        print(f"    数据量: {len(df)} 条")
        for mt, info in league_models.items():
            acc = info["result"].get("accuracy", 0)
            print(f"    {mt:25s}: {acc:.2%}")

    return all_results


def evaluate_on_test_set(
    df: pd.DataFrame,
    league_key: str,
    test_cutoff: str = "2526",
) -> dict:
    """
    在测试集上评估各模型性能

    Args:
        df: 完整特征数据
        league_key: 联赛代码
        test_cutoff: 用作测试的赛季

    Returns:
        评估结果
    """
    train_df = df[df["season_code"] < test_cutoff].copy()
    test_df = df[df["season_code"] >= test_cutoff].copy()

    if len(test_df) < 10:
        logger.warning(f"{league_key}: 测试数据不足 ({len(test_df)} 条)")
        return {}

    logger.info(f"{league_key}: 训练 {len(train_df)} 条, 测试 {len(test_df)} 条")

    # 训练 ML 模型
    models_config = ["random_forest", "logistic_regression"]
    predictors = []

    for model_type in models_config:
        p = FootballPredictor(model_type=model_type, league=f"{league_key}_eval")
        result = p.train(train_df, use_tscv=False)
        if "error" not in result:
            predictors.append(p)

    # 集成预测
    ensemble = EnsemblePredictor(predictors) if len(predictors) > 0 else None

    # 泊松基线
    attack, defense, avg_h, avg_a = calc_attack_defense_strength(train_df)

    # 评估
    results = {f"ml_{mt}": {"correct": 0, "total": 0} for mt in models_config}
    results["ensemble"] = {"correct": 0, "total": 0}
    results["poisson"] = {"correct": 0, "total": 0}

    for _, row in test_df.iterrows():
        actual = row["result"]
        results["poisson"]["total"] += 1

        # 泊松
        poisson_pred = predict_match_poisson(
            row["home_team"], row["away_team"],
            attack, defense, avg_h, avg_a,
            league=row["league"],
            elo_home=row.get("elo_home"),
            elo_away=row.get("elo_away"),
        )
        poisson_pick = (
            "H" if poisson_pred.home_win_prob > max(poisson_pred.draw_prob, poisson_pred.away_win_prob)
            else ("D" if poisson_pred.draw_prob > poisson_pred.away_win_prob else "A")
        )
        if poisson_pick == actual:
            results["poisson"]["correct"] += 1

        # ML 模型预测
        feat_row = {c: row[c] for c in predictors[0].feature_names if c in row.index}
        for p in predictors:
            key = f"ml_{p.model_type}"
            results[key]["total"] += 1
            try:
                pred = p.predict(feat_row)
                if pred.predicted == actual:
                    results[key]["correct"] += 1
            except Exception:
                pass

        # 集成预测
        if ensemble:
            results["ensemble"]["total"] += 1
            try:
                pred = ensemble.predict(feat_row)
                if pred.predicted == actual:
                    results["ensemble"]["correct"] += 1
            except Exception:
                pass

    # 打印结果
    print(f"\n{league_key} 测试集评估 ({len(test_df)} 场):")
    for key, v in results.items():
        if v["total"] > 0:
            print(f"  {key:30s}: {v['correct']}/{v['total']} = {v['correct']/v['total']:.2%}")

    return results


def train_all_and_evaluate(
    force_download: bool = False,
    save: bool = True,
    test_cutoff: str = "2526",
):
    """
    全流程：下载 → 训练 → 评估 → 保存

    Args:
        force_download: 强制重新下载
        save: 保存模型
        test_cutoff: 用作测试的赛季
    """
    all_results = {}

    for league_key in LEAGUES:
        logger.info(f"\n{'='*60}")
        logger.info(f"{league_key} ({LEAGUES[league_key]['name']})")
        logger.info(f"{'='*60}")

        # 下载所有数据（含测试赛季）
        all_seasons = list(set(TRAIN_SEASONS + [test_cutoff]))
        all_seasons.sort()
        raw = download_league_data(league_key, season_codes=all_seasons, force=force_download)
        if raw.empty:
            continue

        std = standardize_dataframe(raw)
        df = build_features(std)

        if len(df) < 200:
            continue

        # 训练（使用训练赛季）
        train_df = df[df["season_code"] < test_cutoff].copy()
        test_df = df[df["season_code"] >= test_cutoff].copy()

        models_config = ["random_forest", "logistic_regression", "gradient_boosting"]
        predictors = []

        for model_type in models_config:
            p = FootballPredictor(model_type=model_type, league=league_key)
            tr = p.train(train_df, use_tscv=True)
            if "error" not in tr:
                predictors.append(p)
                if save:
                    p.save()

        # 评估
        if len(test_df) >= 10:
            eval_results = evaluate_on_test_set(df, league_key, test_cutoff)
            all_results[league_key] = eval_results

    # 汇总
    print(f"\n{'='*60}")
    print("训练完成！模型保存位置:")
    print(f"  {MODELS_DIR}")
    print(f"\n各联赛模型文件:")
    for f in sorted(MODELS_DIR.glob("*.pkl")):
        size = f.stat().st_size / 1024
        print(f"  {f.name} ({size:.1f} KB)")

    return all_results


if __name__ == "__main__":
    train_all_and_evaluate()
