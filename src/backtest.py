"""
回测评估引擎 — 使用历史数据模拟预测并评估性能

支持分批回测 + 断点续跑 (checkpoint)

使用方式:
    # 完整回测 (每次窗口后自动存 checkpoint)
    result = sliding_window_backtest(df, checkpoint_path="data/checkpoint.json")

    # 断点续跑 (自动检测已有 checkpoint)
    result = sliding_window_backtest(df, checkpoint_path="data/checkpoint.json")
"""

import json
import os
from dataclasses import dataclass, asdict
from pathlib import Path

import pandas as pd
import numpy as np

from config import BACKTEST_CONFIG
from src.utils import logger
from src.features import build_features
from src.poisson import calc_attack_defense_strength, predict_match_poisson
from src.ml_models import FootballPredictor


# ─── 结果数据类 ───────────────────────────────────────────────

@dataclass
class BacktestResult:
    """回测结果"""
    total_matches: int
    poisson_accuracy: float
    ml_accuracy: float
    poisson_confusion: dict
    ml_confusion: dict
    poisson_by_league: dict
    ml_by_league: dict
    simulated_roi: float
    details: list[dict]


# ─── Checkpoint（断点续跑） ───────────────────────────────────

@dataclass
class BacktestCheckpoint:
    """回测 checkpoint — 保存中间状态，失败后可从该处续跑"""
    pos: int               # 当前滑动窗口起始位置
    iteration: int         # 当前迭代次数
    total_rows: int        # 总数据行数（用于校验）
    train_window: int
    test_window: int
    step_size: int
    # 累计统计
    poisson_correct: int
    ml_correct: int
    total: int
    poisson_by_league: dict
    ml_by_league: dict
    details: list[dict]
    bankroll: float
    total_bets: int
    total_won: int
    ml_total: int = 0

    def save(self, path: str | Path):
        """保存 checkpoint 到 JSON 文件"""
        dirname = os.path.dirname(path)
        if dirname:
            os.makedirs(dirname, exist_ok=True)

        # details 可能很长，只保留后 100 条以减少 IO
        data = asdict(self)
        data["details"] = data["details"][-100:]  # 只保留最近 100 条详情

        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, default=str)

        logger.info(f"  [checkpoint] 已保存: pos={self.pos}, iter={self.iteration}, 已回测 {self.total} 场")

    @classmethod
    def load(cls, path: str | Path) -> "BacktestCheckpoint | None":
        """从 JSON 加载 checkpoint，文件不存在时返回 None"""
        if not os.path.exists(path):
            return None
        try:
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
            return cls(**data)
        except Exception as e:
            logger.warning(f"  [checkpoint] 加载失败: {e}，将从头开始")
            return None


# ─── 滑窗回测（带 checkpoint） ───────────────────────────────

def sliding_window_backtest(
    df: pd.DataFrame,
    train_window: int = 380,
    test_window: int = 38,
    step_size: int = 76,
    checkpoint_path: str | Path | None = None,
) -> BacktestResult:
    """
    滑动窗口回测（带断点续跑能力）

    每处理一个窗口就保存 checkpoint，中断后重新调用可自动续跑。

    Args:
        df: 标准化比赛数据 (含预计算特征)
        train_window: 训练窗口大小
        test_window: 测试窗口大小
        step_size: 滑动步长
        checkpoint_path: checkpoint 文件路径，None 则不保存

    Returns:
        BacktestResult 对象
    """
    df = df.sort_values("date").reset_index(drop=True)
    n = len(df)

    if n < train_window + test_window:
        logger.warning(f"数据量不足 ({n} < {train_window + test_window})")
        train_window = int(n * 0.7)
        test_window = n - train_window
        step_size = max(1, test_window // 2)

    # ── 尝试加载 checkpoint ──
    cp = None
    if checkpoint_path:
        cp = BacktestCheckpoint.load(checkpoint_path)
        if cp:
            # 校验参数一致性
            if cp.total_rows != n:
                logger.warning(
                    f"  [checkpoint] 数据量不一致: cp={cp.total_rows}, actual={n}，忽略 checkpoint"
                )
                cp = None
            elif cp.train_window != train_window or cp.test_window != test_window or cp.step_size != step_size:
                logger.warning(
                    f"  [checkpoint] 参数不一致，忽略 checkpoint"
                )
                cp = None

    if cp:
        pos = cp.pos
        iteration = cp.iteration
        poisson_correct = cp.poisson_correct
        ml_correct = cp.ml_correct
        total = cp.total
        ml_total = getattr(cp, 'ml_total', 0)
        poisson_by_league = cp.poisson_by_league
        ml_by_league = cp.ml_by_league
        details = cp.details
        bankroll = cp.bankroll
        total_bets = cp.total_bets
        total_won = cp.total_won
        logger.info(
            f"  [checkpoint] 恢复断点: pos={pos}, iter={iteration}, "
            f"已回测 {total} 场, 剩余约 {(n - pos) // step_size} 个窗口"
        )
    else:
        pos = train_window
        iteration = 0
        poisson_correct = 0
        ml_correct = 0
        ml_total = 0
        total = 0
        poisson_by_league: dict[str, dict] = {}
        ml_by_league: dict[str, dict] = {}
        details = []
        bankroll = 1000.0
        total_bets = 0
        total_won = 0
        logger.info(
            f"滑动窗口回测: "
            f"训练={train_window}, 测试={test_window}, "
            f"步长={step_size}, 总数据={n}"
        )

    SIMULATED_ODDS_HOME = 2.5
    SIMULATED_ODDS_DRAW = 3.4
    SIMULATED_ODDS_AWAY = 2.8
    stake = 10.0

    # 如果有真实赔率，使用真实赔率计算更真实的 ROI
    has_real_odds = "AvgH" in df.columns or "B365H" in df.columns

    while pos + test_window <= n:
        iteration += 1
        train_df = df.iloc[pos - train_window:pos]
        test_df = df.iloc[pos:pos + test_window]

        # --- 泊松模型 (按联赛计算) ---
        attack, defense, avg_h_by_league, avg_a_by_league = calc_attack_defense_strength(train_df)

        # --- ML 模型 (每 10 个窗口训练一次) ---
        ml_ready = False
        if iteration % 10 == 1 or iteration == 1:
            ml_pred = FootballPredictor(model_type="random_forest")
            try:
                ml_pred.train(train_df, use_tscv=False)
                ml_ready = True
            except Exception as e:
                logger.warning(f"ML 训练失败 (iter {iteration}): {e}")

        for _, row in test_df.iterrows():
            poisson_pred = predict_match_poisson(
                row["home_team"], row["away_team"],
                attack, defense, avg_h_by_league, avg_a_by_league,
                league=row["league"],
                elo_home=row.get("elo_home"),
                elo_away=row.get("elo_away"),
            )
            poisson_result = (
                "H" if poisson_pred.home_win_prob > max(poisson_pred.draw_prob, poisson_pred.away_win_prob)
                else ("D" if poisson_pred.draw_prob > poisson_pred.away_win_prob else "A")
            )
            actual = row["result"]
            league = row["league"]

            poisson_correct += (poisson_result == actual)
            poisson_by_league.setdefault(league, {"correct": 0, "total": 0})
            poisson_by_league[league]["total"] += 1
            poisson_by_league[league]["correct"] += (poisson_result == actual)

            # ML 预测
            ml_result = None
            ml_confidence = 0.0
            if ml_ready:
                try:
                    feat_cols = ml_pred.feature_names
                    feat_row = row[feat_cols].fillna(0).to_frame().T

                    ml_prediction = ml_pred.predict(feat_row)
                    if isinstance(ml_prediction, list) and len(ml_prediction) > 0:
                        ml_result = ml_prediction[0].predicted
                        ml_confidence = ml_prediction[0].confidence
                    elif hasattr(ml_prediction, 'predicted'):
                        ml_result = ml_prediction.predicted
                        ml_confidence = ml_prediction.confidence
                except Exception:
                    pass

            if ml_result:
                ml_correct += (ml_result == actual)
                ml_by_league.setdefault(league, {"correct": 0, "total": 0})
                ml_by_league[league]["total"] += 1
                ml_by_league[league]["correct"] += (ml_result == actual)

            total += 1

            # 模拟投注 (使用真实赔率优先)
            best_prob = max(
                poisson_pred.home_win_prob,
                poisson_pred.draw_prob,
                poisson_pred.away_win_prob,
            )
            best_prob_source = "poisson"
            if ml_confidence > best_prob and ml_result:
                best_prob = ml_confidence
                best_prob_source = "ml"

            if best_prob > 0.35:
                total_bets += 1
                if best_prob_source == "poisson":
                    predicted = poisson_result
                else:
                    predicted = ml_result

                # 使用真实赔率（如果有）
                if predicted == "H":
                    odds = row.get("AvgH", row.get("B365H", SIMULATED_ODDS_HOME))
                elif predicted == "D":
                    odds = row.get("AvgD", row.get("B365D", SIMULATED_ODDS_DRAW))
                else:
                    odds = row.get("AvgA", row.get("B365A", SIMULATED_ODDS_AWAY))

                # 处理 NaN 赔率
                if pd.isna(odds) or odds <= 1:
                    odds = SIMULATED_ODDS_HOME if predicted == "H" else (
                        SIMULATED_ODDS_DRAW if predicted == "D" else SIMULATED_ODDS_AWAY
                    )

                if predicted == actual:
                    bankroll += stake * (float(odds) - 1)
                    total_won += 1
                else:
                    bankroll -= stake

            details.append({
                "match": f"{row['home_team']} vs {row['away_team']}",
                "league": league,
                "actual": actual,
                "poisson_pred": poisson_result,
                "poisson_probs": {
                    "H": poisson_pred.home_win_prob,
                    "D": poisson_pred.draw_prob,
                    "A": poisson_pred.away_win_prob,
                },
                "ml_pred": ml_result,
                "ml_conf": ml_confidence,
            })

        pos += step_size

        # ── 每处理一个窗口就保存 checkpoint ──
        if checkpoint_path:
            cp = BacktestCheckpoint(
                pos=pos,
                iteration=iteration,
                total_rows=n,
                train_window=train_window,
                test_window=test_window,
                step_size=step_size,
                poisson_correct=poisson_correct,
                ml_correct=ml_correct,
                total=total,
                poisson_by_league=poisson_by_league,
                ml_by_league=ml_by_league,
                details=details,
                bankroll=bankroll,
                total_bets=total_bets,
                total_won=total_won,
            )
            cp.ml_total = ml_total
            cp.save(checkpoint_path)

        # 进度日志：每 5 个窗口或每 2000 场比赛
        if iteration % 5 == 0 or total % 2000 < 38:
            logger.info(f"  迭代 {iteration}: 已回测 {total} 场 (pos={pos})...")

    # ── 计算结果并保存 ──
    poisson_acc = poisson_correct / total if total > 0 else 0
    ml_acc = ml_correct / ml_total if ml_total > 0 else 0
    roi = (bankroll - 1000) / 1000 if total_bets > 0 else 0

    def calc_confusion(details_list, key="poisson_pred"):
        conf = {"H": {"H": 0, "D": 0, "A": 0}, "D": {"H": 0, "D": 0, "A": 0}, "A": {"H": 0, "D": 0, "A": 0}}
        for d in details_list:
            pred = d.get(key)
            actual = d["actual"]
            if pred and pred in conf and actual in conf[pred]:
                conf[pred][actual] += 1
        return conf

    poisson_conf = calc_confusion(details, "poisson_pred")
    ml_conf_input = calc_confusion(details, "ml_pred")

    poisson_league_acc = {
        league: round(v["correct"] / v["total"], 4)
        for league, v in poisson_by_league.items()
    }
    ml_league_acc = {
        league: round(v["correct"] / v["total"], 4)
        for league, v in ml_by_league.items()
    }

    result = BacktestResult(
        total_matches=total,
        poisson_accuracy=round(poisson_acc, 4),
        ml_accuracy=round(ml_acc, 4),
        poisson_confusion=poisson_conf,
        ml_confusion=ml_conf_input,
        poisson_by_league=poisson_league_acc,
        ml_by_league=ml_league_acc,
        simulated_roi=round(roi, 4),
        details=details,
    )

    logger.info(
        f"\n回测完成! {total} 场比赛\n"
        f"  泊松准确率: {poisson_acc:.2%}\n"
        f"  ML 准确率:  {ml_acc:.2%}\n"
        f"  模拟投注 ROI: {roi:.2%} "
        f"(投注 {total_bets} 场, 赢 {total_won} 场)"
    )

    # 回测完成，删除 checkpoint
    if checkpoint_path and os.path.exists(checkpoint_path):
        os.remove(checkpoint_path)
        logger.info("  [checkpoint] 回测完成，已清理 checkpoint 文件")

    return result


def per_league_backtest(
    df: pd.DataFrame,
    train_window: int = 380,
    test_window: int = 38,
    step_size: int = 76,
) -> dict[str, BacktestResult]:
    """
    按联赛分别回测

    每个联赛独立的滑动窗口回测，避免跨联赛数据混合。

    Args:
        df: 标准化比赛数据（含 league 列）
        train_window: 训练窗口大小
        test_window: 测试窗口大小
        step_size: 滑动步长

    Returns:
        {联赛: BacktestResult}
    """
    from config import LEAGUES

    results = {}
    all_results = []

    for league_key in LEAGUES:
        league_df = df[df["league"] == league_key].copy()
        if len(league_df) < train_window + test_window:
            logger.warning(f"{league_key}: 数据不足 ({len(league_df)} 条)，使用更小的窗口")
            lw = min(train_window, int(len(league_df) * 0.7))
            ltest = len(league_df) - lw
            lstep = max(1, ltest // 2)
        else:
            lw = train_window
            ltest = test_window
            lstep = step_size

        logger.info(f"\n{'='*50}")
        logger.info(f"回测 {league_key} ({LEAGUES[league_key]['name']})")
        logger.info(f"{'='*50}")
        logger.info(f"  数据: {len(league_df)} 场, 窗口: train={lw}, test={ltest}, step={lstep}")

        result = sliding_window_backtest(
            league_df,
            train_window=lw,
            test_window=ltest,
            step_size=lstep,
        )
        results[league_key] = result

        print(f"\n  {league_key} 回测结果:")
        print(f"    泊松: {result.poisson_accuracy:.2%}")
        print(f"    ML:   {result.ml_accuracy:.2%}")
        print(f"    ROI:  {result.simulated_roi:.2%}")

    # 汇总
    print(f"\n{'='*50}")
    print("各联赛回测汇总")
    print(f"{'='*50}")
    for league_key, r in sorted(results.items()):
        print(f"  {league_key:12s}: 泊松={r.poisson_accuracy:.2%}  ML={r.ml_accuracy:.2%}  ROI={r.simulated_roi:.2%}  ({r.total_matches}场)")

    return results
