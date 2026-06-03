"""
置信度分层投注系统 — 资金管理 + 赔率价值评估

核心思路:
  整体 ML 预测准确率 ~51%，但分层后高置信度 (>60%) 的子集可达 65-70%。
  配合 Kelly 资金管理，理论上可以从博彩市场获得正期望收益。

置信度 = 模型预测的最高概率 (max(P(H), P(D), P(A)))

资金管理:
  - Kelly 准则: f* = (p * b - q) / b
    p = 模型概率, q = 1-p, b = 赔率 - 1
  - 分层 Kelly 分数: 置信度越高，Kelly 比例越大
  - 防止过度投注: 最大押注不超过 bankroll 的 20%

使用方式:
    from src.betting_system import ConfidenceBettingSystem, run_tiered_backtest

    # 在已有数据上回测
    results = run_tiered_backtest(df, predictor)

    # 或单独使用
    cbs = ConfidenceBettingSystem(initial_bankroll=1000)
    decision = cbs.evaluate_bet(model_probs, odds)
"""

from dataclasses import dataclass, field, asdict
from enum import Enum
from pathlib import Path
from typing import Optional
import json
import numpy as np
import pandas as pd

from config import LEAGUES
from src.utils import logger


# ─── 置信度分层 ───────────────────────────────────────────────

class ConfidenceTier(Enum):
    """置信度分层"""
    LOW = "Low"          # 33-40%    → 不投注
    MEDIUM = "Medium"    # 40-50%   → 极小额试水
    HIGH = "High"        # 50-60%   → 半 Kelly
    VERY_HIGH = "VHigh"  # 60-70%   → 3/4 Kelly
    ELITE = "Elite"      # 70%+     → 全 Kelly（上限 15% 资金）
    MAX = "Max"          # 80%+     → 全 Kelly（上限 20% 资金）


def get_confidence_tier(max_prob: float) -> ConfidenceTier:
    """根据最大概率确定置信度分层"""
    if max_prob >= 0.80:
        return ConfidenceTier.MAX
    elif max_prob >= 0.70:
        return ConfidenceTier.ELITE
    elif max_prob >= 0.60:
        return ConfidenceTier.VERY_HIGH
    elif max_prob >= 0.50:
        return ConfidenceTier.HIGH
    elif max_prob >= 0.40:
        return ConfidenceTier.MEDIUM
    else:
        return ConfidenceTier.LOW


def get_kelly_fraction(tier: ConfidenceTier) -> float:
    """
    分层 Kelly 分数 — 置信度越高，越敢投

    Low: 0 (不投)
    Medium: 0.05 (极轻仓试水)
    High: 0.50 (半 Kelly)
    VHigh: 0.75 (3/4 Kelly)
    Elite: 1.00 (全 Kelly，受上限约束)
    Max: 1.00 (全 Kelly，受上限约束)
    """
    mapping = {
        ConfidenceTier.LOW: 0.0,
        ConfidenceTier.MEDIUM: 0.05,
        ConfidenceTier.HIGH: 0.50,
        ConfidenceTier.VERY_HIGH: 0.75,
        ConfidenceTier.ELITE: 1.00,
        ConfidenceTier.MAX: 1.00,
    }
    return mapping[tier]


def get_max_stake_frac(tier: ConfidenceTier) -> float:
    """
    单个投注占 bankroll 的上限比例

    保守设计：最高不超过 10%（全 Kelly 如果建议 20%，也要截断到 10%）。
    真实足球预测的 edge 很小且不稳定，大仓位等于赌博。
    """
    mapping = {
        ConfidenceTier.LOW: 0.0,
        ConfidenceTier.MEDIUM: 0.01,   # 试水仓位
        ConfidenceTier.HIGH: 0.03,      # 保守
        ConfidenceTier.VERY_HIGH: 0.06, # 正常仓位
        ConfidenceTier.ELITE: 0.10,     # 最大不超过 10%
        ConfidenceTier.MAX: 0.10,       # 最大不超过 10%
    }
    return mapping[tier]


# ─── 数据类 ───────────────────────────────────────────────────

@dataclass
class BetDecision:
    """单场投注决策"""
    match_id: str                # "主队 vs 客队"
    league: str
    date: str
    predicted_outcome: str       # H/D/A
    actual_outcome: str          # H/D/A
    model_probs: dict[str, float]  # {"H": ..., "D": ..., "A": ...}
    confidence: float            # max model probability
    tier: str                    # 分层名称

    odds_available: bool         # 是否有真实赔率
    odds_home: float
    odds_draw: float
    odds_away: float

    # 投注决策
    bet_on: str | None           # 投哪个结果 (H/D/A/None)
    bet_odds: float              # 投注时的赔率
    bet_stake: float             # 投注金额（单位货币）
    bet_kelly: float             # Kelly 建议比例
    bet_ev: float                # 期望值 (p * odds - 1)
    bet_stdout: float            # 如果赢了，净利润

    # 结算
    won: bool | None             # True/False/None(未投)
    profit: float                # 净利润（负为亏损）

    # 分析
    odds_implied_prob: float     # 赔率隐含概率
    edge: float                  # 模型概率 - 隐含概率（正=有优势）


@dataclass
class TierStats:
    """单个置信度分层的统计"""
    tier: str
    total_bets: int = 0
    won: int = 0
    lost: int = 0
    accuracy: float = 0.0
    total_staked: float = 0.0
    total_profit: float = 0.0
    roi: float = 0.0           # 该层投注的 ROI
    avg_odds: float = 0.0
    avg_edge: float = 0.0
    kelly_profit: float = 0.0


@dataclass
class BettingResult:
    """投注回测结果"""
    # 全局统计
    total_matches: int
    total_bets: int
    bets_placed_pct: float
    total_staked: float
    total_profit: float
    roi: float                  # 总收益率
    initial_bankroll: float
    final_bankroll: float
    max_bankroll: float
    min_bankroll: float
    drawdown: float             # 最大回撤
    win_rate: float
    avg_odds: float
    avg_edge: float
    kelly_final: float          # Kelly 资金管理后的最终资金
    kelly_roi: float            # Kelly ROI

    # 分层统计
    tier_stats: dict[str, TierStats]
    # 预测准确率分层 (不含投注，纯预测)
    tier_prediction_accuracy: dict[str, float]

    # 详情
    decisions: list[BetDecision]
    bankroll_history: list[dict]
    summary: dict


# ─── Kelly 计算器 ─────────────────────────────────────────────

class KellyCalculator:
    """Kelly 准则资金管理"""

    @staticmethod
    def kelly_fraction(prob: float, odds: float) -> float:
        """
        计算 Kelly 比例

        f* = (p * b - q) / b
          p = 模型预测概率
          q = 1 - p
          b = 赔率 - 1

        Args:
            prob: 模型预测该结果的概率 (0~1)
            odds: 小数赔率 (如 2.5)

        Returns:
            Kelly 建议比例 (0~1)。负值表示不投。
        """
        if prob <= 0 or odds <= 1 or prob >= 1:
            return 0.0
        b = odds - 1.0
        q = 1.0 - prob
        f = (prob * b - q) / b
        return max(0.0, f)

    @staticmethod
    def expected_value(prob: float, odds: float) -> float:
        """期望值 EV = p * odds - 1"""
        return prob * odds - 1.0

    @staticmethod
    def implied_prob(odds: float) -> float:
        """赔率 → 隐含概率 (不含去边际化)"""
        if odds <= 1:
            return 0.0
        return 1.0 / odds

    @staticmethod
    def edge(prob: float, odds: float) -> float:
        """边际 = 模型概率 - 赔率隐含概率"""
        return prob - KellyCalculator.implied_prob(odds)


# ─── 核心投注系统 ─────────────────────────────────────────────

class ConfidenceBettingSystem:
    """
    置信度分层投注系统

    结合模型预测概率、真实赔率、Kelly 资金管理和置信度分层，
    实现正期望投注。

    使用方式:
        cbs = ConfidenceBettingSystem(initial_bankroll=1000)
        decision = cbs.evaluate_bet(
            model_probs={"H": 0.55, "D": 0.25, "A": 0.20},
            odds={"H": 2.1, "D": 3.5, "A": 3.8},
            match_id="Arsenal vs Chelsea",
            league="EPL",
            date="2025-12-01",
            actual_outcome="H",
        )
        cbs.settle_bet(decision, actual_outcome="H")
    """

    def __init__(
        self,
        initial_bankroll: float = 1000.0,
        min_edge: float = 0.03,
        use_kelly: bool = True,
        calibration_factors: dict[str, float] | None = None,
    ):
        """
        Args:
            initial_bankroll: 初始资金
            min_edge: 最小门槛（模型概率 > 隐含概率 + min_edge 才投）
            use_kelly: 是否使用 Kelly 资金管理
            calibration_factors: 概率校准因子 per tier。
                例如 {"VHigh": 0.85} 表示 VHigh 层的 60% 概率实际只有 51% 可信。
        """
        self.bankroll = initial_bankroll
        self.initial_bankroll = initial_bankroll
        self.max_bankroll = initial_bankroll
        self.min_bankroll = initial_bankroll
        self.min_edge = min_edge
        self.use_kelly = use_kelly
        self.calibration_factors = calibration_factors or {}

        # Edge 门槛按层递增：置信度越高，要求更高 edge 来补偿校准不确定性
        self.min_edge_by_tier = {
            ConfidenceTier.LOW: 999.0,       # 永远不投
            ConfidenceTier.MEDIUM: 0.05,     # 低信心必须有 5% edge
            ConfidenceTier.HIGH: 0.04,       # 中信心 4%
            ConfidenceTier.VERY_HIGH: 0.03,  # 高信心 3%
            ConfidenceTier.ELITE: 0.02,      # 极高 2%
            ConfidenceTier.MAX: 0.02,        # 最高 2%
        }

        self.kelly = KellyCalculator()
        self.decisions: list[BetDecision] = []
        self.bankroll_history: list[dict] = []
        self.iteration = 0

        self._log_bankroll("init")

    def _log_bankroll(self, event: str):
        """记录资金变化"""
        self.bankroll_history.append({
            "iteration": self.iteration,
            "event": event,
            "bankroll": self.bankroll,
        })

    def evaluate_bet(
        self,
        model_probs: dict[str, float],   # {"H": prob, "D": prob, "A": prob}
        odds_series: dict[str, float],   # {"H": odds, "D": odds, "A": odds}
        match_id: str,
        league: str,
        date: str,
        actual_outcome: str,
    ) -> BetDecision:
        """
        评估单场比赛，做出投注决策

        策略:
        1. 找模型概率最高的结果
        2. 计算 Kelly 建议占比
        3. 根据置信度分层调整仓位
        4. 只在 edge > min_edge 时投注

        Returns:
            BetDecision（含投注决策）
        """
        # 找出模型最看好的结果
        pred_outcome = max(model_probs, key=model_probs.get)
        raw_confidence = model_probs[pred_outcome]

        tier = get_confidence_tier(raw_confidence)

        # ── 校准修正 ──
        # 校准因子 = accuracy / avg_confidence per tier
        # >1.0 = 模型保守（预测概率低于实际胜率），上调概率
        # <1.0 = 模型过自信（预测概率高于实际胜率），下调概率
        # 上限 1.5 防止过度修正
        raw_cal = self.calibration_factors.get(tier.value, 1.0)
        cal_factor = min(raw_cal, 1.5)  # 上限 1.5 防止过度修正
        model_prob = model_probs[pred_outcome] * cal_factor
        model_prob = min(model_prob, 0.92)  # 不超过 92%
        confidence = model_prob  # 校准后的置信度

        # 获取对应赔率
        bet_odds = odds_series.get(pred_outcome, 0.0)
        odds_available = bet_odds > 0 and not np.isnan(bet_odds)

        # 计算 Kelly 和 edge（使用校准后的概率）
        ev = self.kelly.expected_value(model_prob, bet_odds) if odds_available else 0.0
        implied_prob = self.kelly.implied_prob(bet_odds) if odds_available else 0.0
        edge_val = self.kelly.edge(model_prob, bet_odds) if odds_available else 0.0
        kelly_frac = self.kelly.kelly_fraction(model_prob, bet_odds) if odds_available else 0.0

        # 该层的最小 edge 门槛（置信度越低要求越高）
        tier_edge_threshold = self.min_edge_by_tier.get(tier, self.min_edge)

        # 投注决策逻辑
        bet_on = None
        bet_stake = 0.0
        won = None
        profit = 0.0

        should_bet = (
            odds_available
            and bet_odds > 1.0
            and tier != ConfidenceTier.LOW
            and edge_val > max(self.min_edge, tier_edge_threshold)
            and self.bankroll > 0
        )

        if should_bet and self.bankroll > 10:
            bet_on = pred_outcome

            # 分层分数
            kelly_frac_tiered = kelly_frac * get_kelly_fraction(tier)

            # 上限约束（保守：不超过 tier 上限，且全局不超过 10%）
            max_stake = min(
                self.bankroll * 0.10,  # 全局上限 10%
                self.bankroll * get_max_stake_frac(tier),
            )

            if self.use_kelly:
                stake = min(
                    self.bankroll * kelly_frac_tiered,
                    max_stake,
                )
            else:
                # 等额投注
                if tier in (ConfidenceTier.ELITE, ConfidenceTier.MAX, ConfidenceTier.VERY_HIGH):
                    flat = 20.0
                elif tier == ConfidenceTier.HIGH:
                    flat = 10.0
                else:
                    flat = 5.0
                stake = min(flat, self.bankroll * 0.05)

            bet_stake = round(max(stake, 0.0), 2)

        # 不在此处结算 — 外部调用 settle()
        stdout_val = bet_stake * (bet_odds - 1) if bet_on else 0.0

        decision = BetDecision(
            match_id=match_id,
            league=league,
            date=str(date),
            predicted_outcome=pred_outcome,
            actual_outcome=actual_outcome,
            model_probs=model_probs,
            confidence=round(confidence, 4),
            tier=tier.value,
            odds_available=odds_available,
            odds_home=odds_series.get("H", 0),
            odds_draw=odds_series.get("D", 0),
            odds_away=odds_series.get("A", 0),
            bet_on=bet_on,
            bet_odds=bet_odds,
            bet_stake=bet_stake,
            bet_kelly=round(kelly_frac, 4),
            bet_ev=round(ev, 4),
            bet_stdout=round(stdout_val, 2),
            won=None,  # 待结算
            profit=0.0,
            odds_implied_prob=round(implied_prob, 4),
            edge=round(edge_val, 4),
        )

        return decision

    def settle_bet(self, decision: BetDecision) -> BetDecision:
        """
        结算投注：根据实际结果更新盈亏

        Modifies decision in-place (won, profit) and updates bankroll.
        """
        self.iteration += 1

        if decision.bet_on is None:
            decision.won = None
            decision.profit = 0.0
        elif decision.bet_on == decision.actual_outcome:
            # 赢了
            decision.won = True
            decision.profit = decision.bet_stake * (decision.bet_odds - 1)
            self.bankroll += decision.profit
        else:
            # 输了
            decision.won = False
            decision.profit = -decision.bet_stake
            self.bankroll -= decision.bet_stake

        # 跟踪极值
        self.max_bankroll = max(self.max_bankroll, self.bankroll)
        self.min_bankroll = min(self.min_bankroll, self.bankroll)

        decision.profit = round(decision.profit, 2)
        self.decisions.append(decision)

        event = "bet_won" if decision.won else ("bet_lost" if decision.won is False else "no_bet")
        self._log_bankroll(event)
        self.bankroll_history[-1]["profit"] = decision.profit

        return decision

    @staticmethod
    def compute_calibration_factors(y_true, y_prob_list, tiers, max_factor=1.5):
        """
        从历史预测数据计算每层的校准因子。

        校准因子 = accuracy / avg_confidence（每层分别计算）
        含平滑防止除零，上限 max_factor 防止过度修正。

        Args:
            y_true: list[str] — 真实结果 ['H','D','A',...]
            y_prob_list: list[dict] — 模型预测概率
                         [{'H':0.6,'D':0.25,'A':0.15}, ...]
            tiers: list[str] — 每场对应的分层 ['VHigh','Medium',...]
            max_factor: float — 校准因子上限，默认 1.5

        Returns:
            dict[str, float] — 每层的校准因子
        """
        from collections import defaultdict
        tier_data = defaultdict(lambda: {'correct': 0, 'total': 0, 'conf_sum': 0.0})

        for true, probs, tier in zip(y_true, y_prob_list, tiers):
            pred = max(probs, key=probs.get)
            conf = probs[pred]
            tier_data[tier]['total'] += 1
            tier_data[tier]['conf_sum'] += conf
            if pred == true:
                tier_data[tier]['correct'] += 1

        factors = {}
        for tier, data in tier_data.items():
            if data['total'] == 0:
                factors[tier] = 1.0
                continue
            accuracy = data['correct'] / data['total']
            avg_conf = data['conf_sum'] / data['total']
            # 平滑：如果 accuracy 接近 0 或 avg_conf 接近 0，用 1.0
            if avg_conf < 0.01 or accuracy < 0.01:
                factors[tier] = 1.0
            else:
                factors[tier] = min(accuracy / avg_conf, max_factor)

        return factors

    def get_betting_stats(self) -> BettingResult:
        """汇总全部投注统计"""
        if not self.decisions:
            return BettingResult(
                total_matches=0, total_bets=0, bets_placed_pct=0,
                total_staked=0, total_profit=0, roi=0,
                initial_bankroll=self.initial_bankroll,
                final_bankroll=self.bankroll,
                max_bankroll=self.initial_bankroll,
                min_bankroll=self.initial_bankroll,
                drawdown=0, win_rate=0, avg_odds=0, avg_edge=0,
                kelly_final=self.bankroll, kelly_roi=0,
                tier_stats={}, tier_prediction_accuracy={},
                decisions=self.decisions,
                bankroll_history=self.bankroll_history,
                summary={},
            )

        # ── 按置信度分层统计投注 ──
        tier_decisions = {}
        tier_pred_total = {}

        for d in self.decisions:
            # 投注统计
            if d.bet_on is not None:
                tier_decisions.setdefault(d.tier, []).append(d)
            # 预测准确率统计（所有比赛，不管是否投注）
            tier_pred_total.setdefault(d.tier, {"total": 0, "correct": 0})
            tier_pred_total[d.tier]["total"] += 1
            if d.predicted_outcome == d.actual_outcome:
                tier_pred_total[d.tier]["correct"] += 1

        # 投注统计
        all_bets = [d for d in self.decisions if d.bet_on is not None]
        total_bets = len(all_bets)
        total_matches = len(self.decisions)
        total_staked = sum(d.bet_stake for d in all_bets)
        total_profit = sum(d.profit for d in all_bets)
        won_bets = sum(1 for d in all_bets if d.won)
        win_rate = won_bets / total_bets if total_bets > 0 else 0
        avg_odds = np.mean([d.bet_odds for d in all_bets]) if all_bets else 0
        avg_edge = np.mean([d.edge for d in all_bets]) if all_bets else 0

        # ROI
        roi = total_profit / total_staked if total_staked > 0 else 0
        kelly_roi = (self.bankroll - self.initial_bankroll) / self.initial_bankroll

        # 最大回撤
        max_drawdown = self._calc_max_drawdown()

        # 分层统计
        tier_stats = {}
        for tname, td in sorted(tier_decisions.items()):
            tstaked = sum(d.bet_stake for d in td)
            tprofit = sum(d.profit for d in td)
            twon = sum(1 for d in td if d.won)
            troi = tprofit / tstaked if tstaked > 0 else 0.0
            toodds = np.mean([d.bet_odds for d in td]) if td else 0.0
            tedge = np.mean([d.edge for d in td]) if td else 0.0

            tier_stats[tname] = TierStats(
                tier=tname,
                total_bets=len(td),
                won=twon,
                lost=len(td) - twon,
                accuracy=twon / len(td) if td else 0,
                total_staked=round(tstaked, 2),
                total_profit=round(tprofit, 2),
                roi=round(troi, 4),
                avg_odds=round(toodds, 4),
                avg_edge=round(tedge, 4),
                kelly_profit=0,
            )

        # 分层预测准确率（所有比赛）
        tier_pred_acc = {}
        for tname, info in sorted(tier_pred_total.items()):
            tier_pred_acc[tname] = round(
                info["correct"] / info["total"], 4
            ) if info["total"] > 0 else 0.0

        summary = self._build_summary(
            total_matches, total_bets, total_staked, total_profit,
            roi, win_rate, avg_odds, kelly_roi, tier_stats, tier_pred_acc,
        )

        return BettingResult(
            total_matches=total_matches,
            total_bets=total_bets,
            bets_placed_pct=round(total_bets / total_matches, 4) if total_matches else 0,
            total_staked=round(total_staked, 2),
            total_profit=round(total_profit, 2),
            roi=round(roi, 4),
            initial_bankroll=self.initial_bankroll,
            final_bankroll=round(self.bankroll, 2),
            max_bankroll=round(self.max_bankroll, 2),
            min_bankroll=round(self.min_bankroll, 2),
            drawdown=round(max_drawdown, 4),
            win_rate=round(win_rate, 4),
            avg_odds=round(avg_odds, 4),
            avg_edge=round(avg_edge, 4),
            kelly_final=round(self.bankroll, 2),
            kelly_roi=round(kelly_roi, 4),
            tier_stats=tier_stats,
            tier_prediction_accuracy=tier_pred_acc,
            decisions=self.decisions,
            bankroll_history=self.bankroll_history,
            summary=summary,
        )

    def _calc_max_drawdown(self) -> float:
        """计算 peak-to-trough 最大回撤"""
        if len(self.bankroll_history) < 2:
            return 0.0
        values = [h["bankroll"] for h in self.bankroll_history]
        peak = values[0]
        max_dd = 0.0

        for v in values:
            if v > peak:
                peak = v
            dd = (peak - v) / peak if peak > 0 else 0
            max_dd = max(max_dd, dd)

        return max_dd

    def _build_summary(self, *args) -> dict:
        """生成可读摘要"""
        tier_stats_dict, tier_pred_acc = args[-2], args[-1]
        total_matches, total_bets, total_staked, total_profit = args[0], args[1], args[2], args[3]
        roi, win_rate, avg_odds, kelly_roi = args[4], args[5], args[6], args[7]

        return {
            "total_matches": total_matches,
            "total_bets": total_bets,
            "bet_rate": f"{total_bets/total_matches:.1%}" if total_matches else "0%",
            "win_rate": f"{win_rate:.1%}" if total_bets else "N/A",
            "total_staked": f"{total_staked:.0f}",
            "total_profit": f"{total_profit:+.0f}",
            "roi": f"{roi:.2%}",
            "avg_odds": f"{avg_odds:.2f}",
            "kelly_roi": f"{kelly_roi:.2%}",
            "final_bankroll": f"{args[-6]:.0f}",
            "bankroll_change": f"{args[-6] - args[-8]:+.0f}",
            "drawdown": f"{args[-3]:.1%}",
            "tier_performance": {
                t: {
                    "bets": s.total_bets,
                    "win_rate": f"{s.accuracy:.1%}",
                    "roi": f"{s.roi:.2%}",
                    "profit": f"{s.total_profit:+.0f}",
                }
                for t, s in sorted(tier_stats_dict.items())
            },
            "prediction_accuracy_by_tier": {
                t: f"{a:.1%}" for t, a in sorted(tier_pred_acc.items())
            },
        }


# ─── 回测运行器 ──────────────────────────────────────────────

def run_tiered_backtest(
    df: pd.DataFrame,
    predictor,
    initial_bankroll: float = 10000.0,
    min_edge: float = 0.03,
    use_kelly: bool = True,
    verbose: bool = True,
) -> BettingResult:
    """
    在已有特征+预测的数据上跑置信度分层回测

    Args:
        df: 含特征列 + result 列的比赛数据（已 predict_proba 了吗？通常在外部预测）
        predictor: 已训练的 FootballPredictor 实例
        initial_bankroll: 初始资金
        min_edge: 最小 edge 门槛
        use_kelly: 是否使用 Kelly
        verbose: 是否打印进度

    Returns:
        BettingResult 对象
    """
    cbs = ConfidenceBettingSystem(
        initial_bankroll=initial_bankroll,
        min_edge=min_edge,
        use_kelly=use_kelly,
    )

    feature_cols = predictor.feature_names
    available = [c for c in feature_cols if c in df.columns]
    n = len(df)

    for i, (_, row) in enumerate(df.iterrows()):
        # 构建特征行
        feat_row = row[available].fillna(0).to_frame().T
        try:
            pred = predictor.predict(feat_row)
        except Exception as e:
            logger.warning(f"预测失败 {row.get('home_team', '?')}: {e}")
            continue

        if isinstance(pred, list):
            pred = pred[0]

        model_probs = {
            "H": pred.home_win_prob,
            "D": pred.draw_prob,
            "A": pred.away_win_prob,
        }

        # 获取赔率（从数据中）
        odds_series = {
            "H": row.get("AvgH", row.get("B365H", 0)),
            "D": row.get("AvgD", row.get("B365D", 0)),
            "A": row.get("AvgA", row.get("B365A", 0)),
        }

        # 处理 NaN 赔率
        for k in odds_series:
            if pd.isna(odds_series[k]) or odds_series[k] <= 1:
                odds_series[k] = 0.0

        match_id = f"{row.get('home_team', '?')} vs {row.get('away_team', '?')}"
        league = row.get("league", "?")
        date = row.get("date", "?")

        actual = row.get("result", "?")
        if actual not in ("H", "D", "A"):
            continue

        decision = cbs.evaluate_bet(
            model_probs=model_probs,
            odds_series=odds_series,
            match_id=match_id,
            league=league,
            date=date,
            actual_outcome=actual,
        )
        cbs.settle_bet(decision)

    result = cbs.get_betting_stats()

    if verbose:
        _print_results(result)

    return result


def run_tiered_backtest_with_model_probs(
    df: pd.DataFrame,
    y_prob: np.ndarray,            # shape (n, 3) — 已训练的模型对各场比赛的预测概率
    inv_label_map: dict,
    verbose: bool = True,
    **cbs_kwargs,
) -> BettingResult:
    """
    直接传入预测概率矩阵，跳过重新预测（节省时间）

    Args:
        df: 比赛数据（含赔率列和 result 列）
        y_prob: (n, 3) 预测概率矩阵 [P(H), P(D), P(A)]
        inv_label_map: {0: "H", 1: "D", 2: "A"}
        **cbs_kwargs: 传给 ConfidenceBettingSystem 的参数

    Returns:
        BettingResult
    """
    cbs = ConfidenceBettingSystem(**cbs_kwargs)
    n = len(df)

    for i, (_, row) in enumerate(df.iterrows()):
        probs = y_prob[i]
        model_probs = {
            "H": float(probs[0]),
            "D": float(probs[1]),
            "A": float(probs[2]),
        }

        odds_series = {
            "H": row.get("AvgH", row.get("B365H", 0)),
            "D": row.get("AvgD", row.get("B365D", 0)),
            "A": row.get("AvgA", row.get("B365A", 0)),
        }
        for k in odds_series:
            if pd.isna(odds_series[k]) or odds_series[k] <= 1:
                odds_series[k] = 0.0

        match_id = f"{row.get('home_team', '?')} vs {row.get('away_team', '?')}"
        league = row.get("league", "?")
        date = row.get("date", "?")
        actual = row.get("result", "?")
        if actual not in ("H", "D", "A"):
            continue

        decision = cbs.evaluate_bet(
            model_probs=model_probs,
            odds_series=odds_series,
            match_id=match_id,
            league=league,
            date=date,
            actual_outcome=actual,
        )
        cbs.settle_bet(decision)

    result = cbs.get_betting_stats()

    if verbose:
        _print_results(result)

    return result


# ─── 输出打印 ─────────────────────────────────────────────────

def _print_results(result: BettingResult):
    """美观地打印回测结果"""
    s = result.summary

    print(f"\n{'='*60}")
    print(f"  置信度分层投注回测结果")
    print(f"{'='*60}")
    print(f"  全局统计:")
    print(f"    总比赛:    {s['total_matches']} 场")
    print(f"    投注场次:  {s['total_bets']} ({s['bet_rate']})")
    print(f"    胜率:      {s['win_rate']}")
    print(f"    总投注额:  {s['total_staked']}")
    print(f"    总盈亏:    {s['total_profit']}")
    print(f"    ROI:       {s['roi']}")
    print(f"    平均赔率:  {s['avg_odds']}")
    print(f"    最大回撤:  {s['drawdown']}")
    print(f"\n  资金变化:")
    print(f"    初始资金:  {s.get('final_bankroll', result.initial_bankroll)}")
    print(f"    Kelly ROI: {s['kelly_roi']}")
    print(f"    资金变化:  {s['bankroll_change']}")
    print(f"    最大回撤:  {s['drawdown']}")

    print(f"\n  预测准确率分层 (全部 {result.total_matches} 场):")
    print(f"  {'分层':12s} {'场次':>6s} {'准确率':>8s}")
    print(f"  {'─'*28}")
    # 按置信度从高到低排序
    tier_order = ["Max", "Elite", "VHigh", "High", "Medium", "Low"]
    for t in tier_order:
        if t in result.tier_prediction_accuracy:
            # 找到该层比赛数
            n_matches = sum(1 for d in result.decisions if d.tier == t)
            print(f"  {t:12s} {n_matches:>6d} {result.tier_prediction_accuracy[t]:>7.1%}")

    print(f"\n  投注分层统计:")
    print(f"  {'分层':12s} {'投注':>5s} {'胜率':>7s} {'ROI':>7s} {'盈亏':>10s} {'投注额':>10s}")
    print(f"  {'─'*52}")
    for t in tier_order:
        if t in result.tier_stats:
            ts = result.tier_stats[t]
            profit_str = f"{ts.total_profit:+.0f}"
            staked_str = f"{ts.total_staked:.0f}"
            print(f"  {t:12s} {ts.total_bets:>5d} {ts.accuracy:>6.1%} {ts.roi:>6.2%} "
                  f"{profit_str:>10s} {staked_str:>10s}")

    print(f"\n  {'─'*52}")
    print(f"  合计: {result.total_bets:>5d}投 {result.win_rate:>6.1%} {result.roi:>6.2%} "
          f"{result.total_profit:+.0f} {result.total_staked:.0f}")


def export_results(result: BettingResult, path: str | Path | None = None) -> dict:
    """
    将回测结果导出为可序列化字典（可选存 JSON）
    """
    data = {
        "summary": result.summary,
        "tier_stats": {
            t: asdict(s) for t, s in result.tier_stats.items()
        },
        "tier_prediction_accuracy": result.tier_prediction_accuracy,
        "bankroll_history": result.bankroll_history,
        "decisions_preview": [
            {
                "match": d.match_id,
                "tier": d.tier,
                "predicted": d.predicted_outcome,
                "actual": d.actual_outcome,
                "bet_on": d.bet_on,
                "confidence": d.confidence,
                "odds": d.bet_odds,
                "stake": d.bet_stake,
                "profit": d.profit,
                "won": d.won,
                "edge": d.edge,
                "ev": d.bet_ev,
            }
            for d in result.decisions[-50:]  # 只保留最近 50 场
        ],
    }

    if path:
        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        logger.info(f"结果已导出: {path}")

    return data
