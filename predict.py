"""
足球预测分析 — CLI 入口

使用方法:
    python predict.py download           # 下载五大联赛数据
    python predict.py sample             # 使用合成数据跑分析
    python predict.py backtest           # 滑动窗口回测
    python predict.py compare            # 对比泊松 vs ML
    python predict.py predict --home "Man City" --away "Arsenal"
    python predict.py summary            # 数据概览
"""

import argparse
import sys
import pandas as pd
import numpy as np
from pathlib import Path

# 确保项目根目录在路径中
sys.path.insert(0, str(Path(__file__).parent.absolute()))

from src.utils import logger, setup_logger
from src.data_loader import load_data, download_all_leagues, standardize_dataframe
from src.features import build_features, get_feature_columns
from src.poisson import (
    calc_attack_defense_strength,
    predict_match_poisson,
    evaluate_poisson_model,
)
from src.ml_models import FootballPredictor, compare_models, EnsemblePredictor, load_per_league_models
from src.backtest import sliding_window_backtest, per_league_backtest
from src.train import run_training, train_all_and_evaluate


def cmd_download():
    """下载五大联赛数据"""
    logger.info("开始下载五大联赛数据...")
    dfs = download_all_leagues()

    total = sum(len(df) for df in dfs.values())
    for key, df in dfs.items():
        std = standardize_dataframe(df) if not df.empty else pd.DataFrame()
        logger.info(f"  {key}: {len(std)} 条标准化记录")

    # 保存合并数据
    all_std = []
    for key in dfs:
        if not dfs[key].empty:
            try:
                all_std.append(standardize_dataframe(dfs[key]))
            except Exception as e:
                logger.warning(f"  {key} 标准化失败: {e}")

    if all_std:
        merged = pd.concat(all_std, ignore_index=True)
        merged.to_parquet(
            Path(__file__).parent / "data" / "processed" / "all_leagues.parquet"
        )
        logger.info(f"保存合并数据: {len(merged)} 条")
    else:
        logger.warning("未下载到有效数据")


def _get_data(args):
    """根据 --real 标志获取数据"""
    if args.real:
        return load_data(data_source="download")
    else:
        return load_data(data_source="sample", n_sample=3000)


def cmd_backtest(args):
    """滑动窗口回测（带断点续跑）"""
    logger.info("加载数据...")
    df = _get_data(args)

    logger.info("构建特征...")
    df = build_features(df)

    # checkpoint 路径
    cp_path = Path(__file__).parent / "data" / "processed" / "backtest_checkpoint.json"
    if args.reset:
        if cp_path.exists():
            cp_path.unlink()
            logger.info("已删除 checkpoint，从头开始")
        else:
            logger.info("无 checkpoint 可删除")

    # 结果保存路径
    result_path = Path(__file__).parent / "data" / "processed" / "backtest_result.json"

    logger.info("开始回测...")
    result = sliding_window_backtest(
        df,
        train_window=args.train_window,
        test_window=args.test_window,
        step_size=args.step_size,
        checkpoint_path=str(cp_path),
    )

    # 保存结果到文件
    result_data = {
        "total_matches": result.total_matches,
        "poisson_accuracy": result.poisson_accuracy,
        "ml_accuracy": result.ml_accuracy,
        "simulated_roi": result.simulated_roi,
        "poisson_confusion": result.poisson_confusion,
        "ml_confusion": result.ml_confusion,
        "poisson_by_league": result.poisson_by_league,
        "ml_by_league": result.ml_by_league,
        "total_details": len(result.details),
    }
    result_path.parent.mkdir(parents=True, exist_ok=True)
    with open(result_path, "w", encoding="utf-8") as f:
        import json
        json.dump(result_data, f, ensure_ascii=False, indent=2)
    logger.info(f"结果已保存到: {result_path}")

    print("\n" + "=" * 60)
    print("回测结果摘要")
    print("=" * 60)
    print(f"总比赛场次:     {result.total_matches}")
    print(f"泊松准确率:     {result.poisson_accuracy:.2%}")
    print(f"ML 模型准确率:  {result.ml_accuracy:.2%}")
    print(f"模拟投注 ROI:   {result.simulated_roi:.2%}")
    print()

    print("--- 泊松模型: 联赛准确率 ---")
    for league, acc in sorted(result.poisson_by_league.items()):
        print(f"  {league:12s}: {acc:.2%}")

    if result.ml_accuracy > 0:
        print("\n--- ML 模型: 联赛准确率 ---")
        for league, acc in sorted(result.ml_by_league.items()):
            print(f"  {league:12s}: {acc:.2%}")

    return result


def cmd_compare(args):
    """对比泊松模型和 ML 模型"""
    logger.info("加载数据...")
    df = _get_data(args)

    logger.info("构建特征...")
    df = build_features(df)

    # 泊松评估
    logger.info("\n=== 泊松模型评估 ===")
    poisson_result = evaluate_poisson_model(df)

    # ML 评估
    logger.info("\n=== ML 模型评估 ===")
    ml_results = compare_models(df)

    # 打印对比
    print("\n" + "=" * 60)
    print("模型对比结果")
    print("=" * 60)
    print(f"数据量: {len(df)} 场比赛")
    print()
    print(f"泊松模型:           {poisson_result['accuracy']:.2%}")
    print(f"  主胜准确率:       {poisson_result['home_win_accuracy']:.2%}")
    print(f"  平局准确率:       {poisson_result['draw_accuracy']:.2%}")
    print(f"  客胜准确率:       {poisson_result['away_win_accuracy']:.2%}")
    print()

    for model_type, result in ml_results.items():
        if "error" in result:
            print(f"{model_type}: {result['error']}")
            continue
        print(f"{model_type:25s}: {result['accuracy']:.2%}")

        if "feature_importance" in result:
            print(f"  top3 特征:")
            for fi in result["feature_importance"][:3]:
                print(f"    {fi['feature']}: {fi['importance']:.4f}")

    return poisson_result, ml_results


def cmd_predict(args):
    """预测单场比赛"""
    # 加载数据 + 训练
    logger.info("加载数据并训练模型...")
    df = load_data(data_source="sample", n_sample=2000)
    df = build_features(df)

    # 泊松
    attack, defense, avg_h_by_league, avg_a_by_league = calc_attack_defense_strength(df)

    # ML
    ml_pred = FootballPredictor(model_type="random_forest")
    ml_pred.train(df)

    # 预测
    print("\n" + "=" * 60)
    print(f"比赛预测: {args.home} vs {args.away}")
    print("=" * 60)

    # 泊松
    poisson_result = predict_match_poisson(
        args.home, args.away, attack, defense, avg_h_by_league, avg_a_by_league,
    )
    # 如果有 Elo 特征，传入以提升精度
    if "elo_home" in df.columns:
        elo_cols = ["elo_home", "elo_away"]
        elo_row = df[elo_cols].iloc[-1]
        poisson_result_with_elo = predict_match_poisson(
            args.home, args.away, attack, defense, avg_h_by_league, avg_a_by_league,
            elo_home=float(elo_row["elo_home"]),
            elo_away=float(elo_row["elo_away"]),
        )
        poisson_result = poisson_result_with_elo
    print(f"\n[泊松分布模型]")
    print(f"  预期进球:  {args.home} {poisson_result.home_goals:.2f} - {poisson_result.away_goals:.2f} {args.away}")
    print(f"  主胜概率:  {poisson_result.home_win_prob:.1%}")
    print(f"  平局概率:  {poisson_result.draw_prob:.1%}")
    print(f"  客胜概率:  {poisson_result.away_win_prob:.1%}")
    print(f"  最可能比分:")
    for (h, a), p in list(poisson_result.score_probs.items())[:5]:
        print(f"    {h}-{a}: {p:.1%}")

    # ML
    print(f"\n[ML 模型 ({ml_pred.model_type})]")
    try:
        feat_cols = ml_pred.feature_names
        # 用两队最近比赛的特征作为预测基准
        home_matches = df[df["home_team"] == args.home]
        away_matches = df[df["away_team"] == args.away]
        ref_idx = df.index[-1]
        if len(home_matches) > 0:
            ref_idx = max(ref_idx, home_matches.index[-1])
        if len(away_matches) > 0:
            ref_idx = max(ref_idx, away_matches.index[-1])
        feat_row = df.loc[[ref_idx], feat_cols]
        pred = ml_pred.predict(feat_row)
        if isinstance(pred, list):
            pred = pred[0]
        print(f"  预测结果:  {pred.predicted}")
        print(f"  主胜概率:  {pred.home_win_prob:.1%}")
        print(f"  平局概率:  {pred.draw_prob:.1%}")
        print(f"  客胜概率:  {pred.away_win_prob:.1%}")
        print(f"  置信度:    {pred.confidence:.1%}")
    except Exception as e:
        print(f"  ML 预测失败: {e}")

    # 综合建议
    print(f"\n[综合建议]")
    max_poisson = max(poisson_result.home_win_prob,
                      poisson_result.draw_prob,
                      poisson_result.away_win_prob)
    poisson_pick = ("主胜" if poisson_result.home_win_prob == max_poisson
                    else "平局" if poisson_result.draw_prob == max_poisson
                    else "客胜")
    print(f"  泊松推荐: {poisson_pick} ({max_poisson:.1%})")


def cmd_train(args):
    """训练 per-league 模型"""
    if args.reset:
        import shutil
        from config import MODELS_DIR
        if MODELS_DIR.exists():
            shutil.rmtree(MODELS_DIR)
            logger.info("已删除旧模型目录")
        MODELS_DIR.mkdir(parents=True, exist_ok=True)

    if args.real:
        results = train_all_and_evaluate(
            force_download=args.force_download,
            save=True,
            test_cutoff="2526",
        )
    else:
        # 合成数据
        from src.data_loader import load_data
        df = load_data(data_source="sample", n_sample=3000)
        df = build_features(df)
        from src.ml_models import train_per_league
        train_per_league(df, save=True)


def cmd_predict_week(args):
    """预测下一轮比赛"""
    if not args.real:
        logger.info("predict-week 需要 --real 标志（使用真实数据）")
        return

    logger.info("加载已训练的模型...")
    models = load_per_league_models()
    if not models:
        logger.error("未找到已训练的模型！请先运行: python predict.py train --real")
        return

    # 加载最新数据
    from src.data_loader import download_league_data, standardize_dataframe
    from config import CURRENT_SEASON_CODE

    leagues_to_predict = [args.league] if args.league else list(LEAGUES.keys())

    for league_key in leagues_to_predict:
        logger.info(f"\n=== 预测 {league_key} 下一轮比赛 ===")

        # 下载当前赛季数据
        raw = download_league_data(league_key, season_codes=[CURRENT_SEASON_CODE])
        if raw.empty:
            logger.warning(f"{league_key}: 当前赛季无数据")
            continue

        std = standardize_dataframe(raw)
        df = build_features(std)

        if df.empty:
            logger.warning(f"{league_key}: 特征工程后无数据")
            continue

        # 获取最后 N 场比赛作为特征
        last_matches = df.tail(20).copy()

        # 找到下一轮尚未进行的比赛
        # 如果有赔率数据，有赔率 = 尚未进行
        has_odds_col = "AvgH" in df.columns or "B365H" in df.columns
        if has_odds_col:
            odds_col = "AvgH" if "AvgH" in df.columns else "B365H"
            upcoming = df[pd.isna(df[odds_col]) | (df[odds_col] <= 0)].copy()
            if upcoming.empty:
                # 尝试找最近的没有结果的比赛 (result 为空)
                upcoming = df[~df["date_parsed"]].copy() if "date_parsed" in df.columns else pd.DataFrame()
        else:
            upcoming = pd.DataFrame()

        if upcoming.empty:
            # 如果无法自动识别，取最后 N 场还未预测的比赛
            logger.info(f"{league_key}: 使用最近数据进行预测")
            # 找最后 38 场（约 1 轮）
            upcoming = last_matches

        # 组装联赛模型
        league_models = {}
        for model_type in ["random_forest", "logistic_regression", "gradient_boosting"]:
            key = f"{league_key}_{model_type}"
            if key in models:
                league_models[model_type] = models[key]

        if not league_models:
            logger.warning(f"{league_key}: 无可用模型")
            continue

        # 集成预测
        try:
            ensemble = EnsemblePredictor(list(league_models.values()))
        except ValueError as e:
            logger.warning(f"{league_key}: 集成预测器创建失败: {e}")
            continue

        # 泊松模型
        from src.poisson import calc_attack_defense_strength, predict_match_poisson
        attack, defense, avg_h, avg_a = calc_attack_defense_strength(df)

        # 预测
        print(f"\n{league_key} 下一轮预测 ({len(upcoming)} 场比赛):")
        print("-" * 80)

        for idx, row in upcoming.iterrows():
            home = row["home_team"]
            away = row["away_team"]

            # 泊松
            poisson_pred = predict_match_poisson(
                home, away, attack, defense, avg_h, avg_a,
                league=row["league"],
                elo_home=row.get("elo_home"),
                elo_away=row.get("elo_away"),
            )

            # ML 集成
            try:
                feat = {c: row[c] for c in ensemble.predictors[0].feature_names if c in row.index}
                ml_pred = ensemble.predict(feat)
            except Exception as e:
                ml_pred = None

            # 综合推荐
            poisson_pick = (
                "H" if poisson_pred.home_win_prob > max(poisson_pred.draw_prob, poisson_pred.away_win_prob)
                else ("D" if poisson_pred.draw_prob > poisson_pred.away_win_prob else "A")
            )

            if ml_pred:
                combined_pick = (
                    "H" if (poisson_pred.home_win_prob + ml_pred.home_win_prob) / 2
                    > max((poisson_pred.draw_prob + ml_pred.draw_prob) / 2,
                          (poisson_pred.away_win_prob + ml_pred.away_win_prob) / 2)
                    else ("D" if (poisson_pred.draw_prob + ml_pred.draw_prob) / 2
                          > (poisson_pred.away_win_prob + ml_pred.away_win_prob) / 2
                          else "A")
                )
            else:
                combined_pick = poisson_pick

            label = {"H": "🏠 主胜", "D": "🤝 平局", "A": "✈️ 客胜"}
            print(f"  {home:22s} vs {away:22s}")
            print(f"    泊松: H={poisson_pred.home_win_prob:.0%} D={poisson_pred.draw_prob:.0%} A={poisson_pred.away_win_prob:.0%} → {label[poisson_pick]}")
            if ml_pred:
                print(f"    ML集成: H={ml_pred.home_win_prob:.0%} D={ml_pred.draw_prob:.0%} A={ml_pred.away_win_prob:.0%} → {label[ml_pred.predicted]}")
            print(f"    🎯 推荐: {label[combined_pick]}")
            print()


def cmd_backtest_pl(args):
    """按联赛分别回测"""
    logger.info("加载数据...")
    df = _get_data(args)

    logger.info("构建特征...")
    df = build_features(df)

    logger.info("开始按联赛分别回测...")
    results = per_league_backtest(
        df,
        train_window=args.train_window,
        test_window=args.test_window,
    )

    return results


def cmd_summary(args):
    """数据概览"""
    logger.info("加载数据...")
    df = _get_data(args)

    print("\n" + "=" * 60)
    print("数据概览")
    print("=" * 60)
    print(f"总比赛场次: {len(df)}")
    print(f"联赛分布:")
    for league in df["league"].value_counts().index:
        count = (df["league"] == league).sum()
        print(f"  {league}: {count} 场")
    print(f"日期范围: {df['date'].min()} ~ {df['date'].max()}")
    print(f"\n结果分布:")
    print(f"  主胜: {(df['result']=='H').sum()} ({(df['result']=='H').mean():.1%})")
    print(f"  平局: {(df['result']=='D').sum()} ({(df['result']=='D').mean():.1%})")
    print(f"  客胜: {(df['result']=='A').sum()} ({(df['result']=='A').mean():.1%})")
    print(f"\n场均进球:")
    print(f"  主场: {df['home_goals'].mean():.2f}")
    print(f"  客场: {df['away_goals'].mean():.2f}")


def main():
    parser = argparse.ArgumentParser(
        description="五大联赛足球预测分析工具",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
示例:
  python predict.py download          # 下载真实数据
  python predict.py summary           # 合成数据概览
  python predict.py summary --real    # 真实数据概览
  python predict.py backtest          # 合成数据回测
  python predict.py backtest --real   # 真实数据回测
  python predict.py compare           # 模型对比 (合成数据)
  python predict.py predict --home "Man City" --away "Arsenal"
        """,
    )

    subparsers = parser.add_subparsers(dest="command", help="子命令")

    # download
    subparsers.add_parser("download", help="下载五大联赛数据")

    # summary
    p_summary = subparsers.add_parser("summary", help="数据概览")
    p_summary.add_argument("--real", action="store_true", help="使用真实数据")

    # backtest
    p_bt = subparsers.add_parser("backtest", help="滑动窗口回测")
    p_bt.add_argument("--real", action="store_true", help="使用真实数据")
    p_bt.add_argument("--train-window", type=int, default=380, help="训练窗口大小")
    p_bt.add_argument("--test-window", type=int, default=38, help="测试窗口大小")
    p_bt.add_argument("--step-size", type=int, default=76, help="滑动步长 (每4轮步进一次)")
    p_bt.add_argument("--reset", action="store_true", help="清空 checkpoint，从头开始")

    # compare
    p_cmp = subparsers.add_parser("compare", help="模型对比")
    p_cmp.add_argument("--real", action="store_true", help="使用真实数据")

    # train
    p_train = subparsers.add_parser("train", help="训练 per-league 模型")
    p_train.add_argument("--league", default=None, help="指定联赛代码（如 EPL），默认全部")
    p_train.add_argument("--real", action="store_true", help="使用真实数据")
    p_train.add_argument("--force-download", action="store_true", help="强制重新下载")
    p_train.add_argument("--reset", action="store_true", help="删除旧模型重新训练")

    # predict-week
    p_pw = subparsers.add_parser("predict-week", help="预测下一轮比赛")
    p_pw.add_argument("--league", default=None, help="指定联赛，默认全部")
    p_pw.add_argument("--real", action="store_true", help="使用真实数据")
    p_pw.add_argument("--num-weeks", type=int, default=1, help="预测未来几轮")

    # predict (single match)
    p_pred = subparsers.add_parser("predict", help="预测单场比赛")
    p_pred.add_argument("--home", required=True, help="主队名")
    p_pred.add_argument("--away", required=True, help="客队名")

    # backtest-per-league
    p_bpl = subparsers.add_parser("backtest-pl", help="按联赛分别回测")
    p_bpl.add_argument("--real", action="store_true", help="使用真实数据")
    p_bpl.add_argument("--train-window", type=int, default=380, help="训练窗口大小")
    p_bpl.add_argument("--test-window", type=int, default=38, help="测试窗口大小")

    args = parser.parse_args()

    if args.command == "download":
        cmd_download()
    elif args.command == "train":
        cmd_train(args)
    elif args.command == "backtest":
        cmd_backtest(args)
    elif args.command == "backtest-pl":
        cmd_backtest_pl(args)
    elif args.command == "compare":
        cmd_compare(args)
    elif args.command == "predict":
        cmd_predict(args)
    elif args.command == "predict-week":
        cmd_predict_week(args)
    elif args.command == "summary":
        cmd_summary(args)
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
