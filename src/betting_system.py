"""
缃俊搴﹀垎灞傛姇娉ㄧ郴缁?鈥?璧勯噾绠＄悊 + 璧旂巼浠峰€艰瘎浼?

鏍稿績鎬濊矾:
  鏁翠綋 ML 棰勬祴鍑嗙‘鐜?~51%锛屼絾鍒嗗眰鍚庨珮缃俊搴?(>60%) 鐨勫瓙闆嗗彲杈?65-70%銆?
  閰嶅悎 Kelly 璧勯噾绠＄悊锛岀悊璁轰笂鍙互浠庡崥褰╁競鍦鸿幏寰楁鏈熸湜鏀剁泭銆?

缃俊搴?= 妯″瀷棰勬祴鐨勬渶楂樻鐜?(max(P(H), P(D), P(A)))

璧勯噾绠＄悊:
  - Kelly 鍑嗗垯: f* = (p * b - q) / b
    p = 妯″瀷姒傜巼, q = 1-p, b = 璧旂巼 - 1
  - 鍒嗗眰 Kelly 鍒嗘暟: 缃俊搴﹁秺楂橈紝Kelly 姣斾緥瓒婂ぇ
  - 闃叉杩囧害鎶曟敞: 鏈€澶ф娂娉ㄤ笉瓒呰繃 bankroll 鐨?20%

浣跨敤鏂瑰紡:
    from src.betting_system import ConfidenceBettingSystem, run_tiered_backtest

    # 鍦ㄥ凡鏈夋暟鎹笂鍥炴祴
    results = run_tiered_backtest(df, predictor)

    # 鎴栧崟鐙娇鐢?
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


# 鈹€鈹€鈹€ 缃俊搴﹀垎灞?鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€

class ConfidenceTier(Enum):
    """缃俊搴﹀垎灞?""
    LOW = "Low"          # 33-40%    鈫?涓嶆姇娉?
    MEDIUM = "Medium"    # 40-50%   鈫?鏋佸皬棰濊瘯姘?
    HIGH = "High"        # 50-60%   鈫?鍗?Kelly
    VERY_HIGH = "VHigh"  # 60-70%   鈫?3/4 Kelly
    ELITE = "Elite"      # 70%+     鈫?鍏?Kelly锛堜笂闄?15% 璧勯噾锛?
    MAX = "Max"          # 80%+     鈫?鍏?Kelly锛堜笂闄?20% 璧勯噾锛?


def get_confidence_tier(max_prob: float) -> ConfidenceTier:
    """鏍规嵁鏈€澶ф鐜囩‘瀹氱疆淇″害鍒嗗眰"""
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
    鍒嗗眰 Kelly 鍒嗘暟 鈥?缃俊搴﹁秺楂橈紝瓒婃暍鎶?

    Low: 0 (涓嶆姇)
    Medium: 0.05 (鏋佽交浠撹瘯姘?
    High: 0.50 (鍗?Kelly)
    VHigh: 0.75 (3/4 Kelly)
    Elite: 1.00 (鍏?Kelly锛屽彈涓婇檺绾︽潫)
    Max: 1.00 (鍏?Kelly锛屽彈涓婇檺绾︽潫)
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
    鍗曚釜鎶曟敞鍗?bankroll 鐨勪笂闄愭瘮渚?

    淇濆畧璁捐锛氭渶楂樹笉瓒呰繃 10%锛堝叏 Kelly 濡傛灉寤鸿 20%锛屼篃瑕佹埅鏂埌 10%锛夈€?
    鐪熷疄瓒崇悆棰勬祴鐨?edge 寰堝皬涓斾笉绋冲畾锛屽ぇ浠撲綅绛変簬璧屽崥銆?
    """
    mapping = {
        ConfidenceTier.LOW: 0.0,
        ConfidenceTier.MEDIUM: 0.01,   # 璇曟按浠撲綅
        ConfidenceTier.HIGH: 0.03,      # 淇濆畧
        ConfidenceTier.VERY_HIGH: 0.06, # 姝ｅ父浠撲綅
        ConfidenceTier.ELITE: 0.10,     # 鏈€澶т笉瓒呰繃 10%
        ConfidenceTier.MAX: 0.10,       # 鏈€澶т笉瓒呰繃 10%
    }
    return mapping[tier]


# 鈹€鈹€鈹€ 鏁版嵁绫?鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€

@dataclass
class BetDecision:
    """鍗曞満鎶曟敞鍐崇瓥"""
    match_id: str                # "涓婚槦 vs 瀹㈤槦"
    league: str
    date: str
    predicted_outcome: str       # H/D/A
    actual_outcome: str          # H/D/A
    model_probs: dict[str, float]  # {"H": ..., "D": ..., "A": ...}
    confidence: float            # max model probability
    tier: str                    # 鍒嗗眰鍚嶇О

    odds_available: bool         # 鏄惁鏈夌湡瀹炶禂鐜?
    odds_home: float
    odds_draw: float
    odds_away: float

    # 鎶曟敞鍐崇瓥
    bet_on: str | None           # 鎶曞摢涓粨鏋?(H/D/A/None)
    bet_odds: float              # 鎶曟敞鏃剁殑璧旂巼
    bet_stake: float             # 鎶曟敞閲戦锛堝崟浣嶈揣甯侊級
    bet_kelly: float             # Kelly 寤鸿姣斾緥
    bet_ev: float                # 鏈熸湜鍊?(p * odds - 1)
    bet_stdout: float            # 濡傛灉璧簡锛屽噣鍒╂鼎

    # 缁撶畻
    won: bool | None             # True/False/None(鏈姇)
    profit: float                # 鍑€鍒╂鼎锛堣礋涓轰簭鎹燂級

    # 鍒嗘瀽
    odds_implied_prob: float     # 璧旂巼闅愬惈姒傜巼
    edge: float                  # 妯″瀷姒傜巼 - 闅愬惈姒傜巼锛堟=鏈変紭鍔匡級


@dataclass
class TierStats:
    """鍗曚釜缃俊搴﹀垎灞傜殑缁熻"""
    tier: str
    total_bets: int = 0
    won: int = 0
    lost: int = 0
    accuracy: float = 0.0
    total_staked: float = 0.0
    total_profit: float = 0.0
    roi: float = 0.0           # 璇ュ眰鎶曟敞鐨?ROI
    avg_odds: float = 0.0
    avg_edge: float = 0.0
    kelly_profit: float = 0.0


@dataclass
class BettingResult:
    """鎶曟敞鍥炴祴缁撴灉"""
    # 鍏ㄥ眬缁熻
    total_matches: int
    total_bets: int
    bets_placed_pct: float
    total_staked: float
    total_profit: float
    roi: float                  # 鎬绘敹鐩婄巼
    initial_bankroll: float
    final_bankroll: float
    max_bankroll: float
    min_bankroll: float
    drawdown: float             # 鏈€澶у洖鎾?
    win_rate: float
    avg_odds: float
    avg_edge: float
    kelly_final: float          # Kelly 璧勯噾绠＄悊鍚庣殑鏈€缁堣祫閲?
    kelly_roi: float            # Kelly ROI

    # 鍒嗗眰缁熻
    tier_stats: dict[str, TierStats]
    # 棰勬祴鍑嗙‘鐜囧垎灞?(涓嶅惈鎶曟敞锛岀函棰勬祴)
    tier_prediction_accuracy: dict[str, float]

    # 璇︽儏
    decisions: list[BetDecision]
    bankroll_history: list[dict]
    summary: dict


# 鈹€鈹€鈹€ Kelly 璁＄畻鍣?鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€

class KellyCalculator:
    """Kelly 鍑嗗垯璧勯噾绠＄悊"""

    @staticmethod
    def kelly_fraction(prob: float, odds: float) -> float:
        """
        璁＄畻 Kelly 姣斾緥

        f* = (p * b - q) / b
          p = 妯″瀷棰勬祴姒傜巼
          q = 1 - p
          b = 璧旂巼 - 1

        Args:
            prob: 妯″瀷棰勬祴璇ョ粨鏋滅殑姒傜巼 (0~1)
            odds: 灏忔暟璧旂巼 (濡?2.5)

        Returns:
            Kelly 寤鸿姣斾緥 (0~1)銆傝礋鍊艰〃绀轰笉鎶曘€?
        """
        if prob <= 0 or odds <= 1 or prob >= 1:
            return 0.0
        b = odds - 1.0
        q = 1.0 - prob
        f = (prob * b - q) / b
        return max(0.0, f)

    @staticmethod
    def expected_value(prob: float, odds: float) -> float:
        """鏈熸湜鍊?EV = p * odds - 1"""
        return prob * odds - 1.0

    @staticmethod
    def implied_prob(odds: float) -> float:
        """璧旂巼 鈫?闅愬惈姒傜巼 (涓嶅惈鍘昏竟闄呭寲)"""
        if odds <= 1:
            return 0.0
        return 1.0 / odds

    @staticmethod
    def edge(prob: float, odds: float) -> float:
        """杈归檯 = 妯″瀷姒傜巼 - 璧旂巼闅愬惈姒傜巼"""
        return prob - KellyCalculator.implied_prob(odds)


# 鈹€鈹€鈹€ 鏍稿績鎶曟敞绯荤粺 鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€

class ConfidenceBettingSystem:
    """
    缃俊搴﹀垎灞傛姇娉ㄧ郴缁?

    缁撳悎妯″瀷棰勬祴姒傜巼銆佺湡瀹炶禂鐜囥€並elly 璧勯噾绠＄悊鍜岀疆淇″害鍒嗗眰锛?
    瀹炵幇姝ｆ湡鏈涙姇娉ㄣ€?

    浣跨敤鏂瑰紡:
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
            initial_bankroll: 鍒濆璧勯噾
            min_edge: 鏈€灏忛棬妲涳紙妯″瀷姒傜巼 > 闅愬惈姒傜巼 + min_edge 鎵嶆姇锛?
            use_kelly: 鏄惁浣跨敤 Kelly 璧勯噾绠＄悊
            calibration_factors: 姒傜巼鏍″噯鍥犲瓙 per tier銆?
                渚嬪 {"VHigh": 0.85} 琛ㄧず VHigh 灞傜殑 60% 姒傜巼瀹為檯鍙湁 51% 鍙俊銆?
        """
        self.bankroll = initial_bankroll
        self.initial_bankroll = initial_bankroll
        self.max_bankroll = initial_bankroll
        self.min_bankroll = initial_bankroll
        self.min_edge = min_edge
        self.use_kelly = use_kelly
        self.calibration_factors = calibration_factors or {}

        # Edge 闂ㄦ鎸夊眰閫掑锛氱疆淇″害瓒婇珮锛岃姹傛洿楂?edge 鏉ヨˉ鍋挎牎鍑嗕笉纭畾鎬?
        self.min_edge_by_tier = {
            ConfidenceTier.LOW: 999.0,       # 姘歌繙涓嶆姇
            ConfidenceTier.MEDIUM: 0.05,     # 浣庝俊蹇冨繀椤绘湁 5% edge
            ConfidenceTier.HIGH: 0.04,       # 涓俊蹇?4%
            ConfidenceTier.VERY_HIGH: 0.03,  # 楂樹俊蹇?3%
            ConfidenceTier.ELITE: 0.02,      # 鏋侀珮 2%
            ConfidenceTier.MAX: 0.02,        # 鏈€楂?2%
        }

        self.kelly = KellyCalculator()
        self.decisions: list[BetDecision] = []
        self.bankroll_history: list[dict] = []
        self.iteration = 0

        self._log_bankroll("init")

    def _log_bankroll(self, event: str):
        """璁板綍璧勯噾鍙樺寲"""
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
        璇勪及鍗曞満姣旇禌锛屽仛鍑烘姇娉ㄥ喅绛?

        绛栫暐:
        1. 鎵炬ā鍨嬫鐜囨渶楂樼殑缁撴灉
        2. 璁＄畻 Kelly 寤鸿鍗犳瘮
        3. 鏍规嵁缃俊搴﹀垎灞傝皟鏁翠粨浣?
        4. 鍙湪 edge > min_edge 鏃舵姇娉?

        Returns:
            BetDecision锛堝惈鎶曟敞鍐崇瓥锛?
        """
        # 鎵惧嚭妯″瀷鏈€鐪嬪ソ鐨勭粨鏋?
        pred_outcome = max(model_probs, key=model_probs.get)
        raw_confidence = model_probs[pred_outcome]

        tier = get_confidence_tier(raw_confidence)

        # 鈹€鈹€ 鏍″噯淇 鈹€鈹€
        # 鏍″噯鍥犲瓙 = accuracy / avg_confidence per tier
        # >1.0 = 妯″瀷淇濆畧锛堥娴嬫鐜囦綆浜庡疄闄呰儨鐜囷級锛屼笂璋冩鐜?
        # <1.0 = 妯″瀷杩囪嚜淇★紙棰勬祴姒傜巼楂樹簬瀹為檯鑳滅巼锛夛紝涓嬭皟姒傜巼
        # 涓婇檺 1.5 闃叉杩囧害淇
        raw_cal = self.calibration_factors.get(tier.value, 1.0)
        cal_factor = min(raw_cal, 1.5)  # 涓婇檺 1.5 闃叉杩囧害淇
        model_prob = model_probs[pred_outcome] * cal_factor
        model_prob = min(model_prob, 0.92)  # 涓嶈秴杩?92%
        confidence = model_prob  # 鏍″噯鍚庣殑缃俊搴?

        # 鑾峰彇瀵瑰簲璧旂巼
        bet_odds = odds_series.get(pred_outcome, 0.0)
        odds_available = bet_odds > 0 and not np.isnan(bet_odds)

        # 璁＄畻 Kelly 鍜?edge锛堜娇鐢ㄦ牎鍑嗗悗鐨勬鐜囷級
        ev = self.kelly.expected_value(model_prob, bet_odds) if odds_available else 0.0
        implied_prob = self.kelly.implied_prob(bet_odds) if odds_available else 0.0
        edge_val = self.kelly.edge(model_prob, bet_odds) if odds_available else 0.0
        kelly_frac = self.kelly.kelly_fraction(model_prob, bet_odds) if odds_available else 0.0

        # 璇ュ眰鐨勬渶灏?edge 闂ㄦ锛堢疆淇″害瓒婁綆瑕佹眰瓒婇珮锛?
        tier_edge_threshold = self.min_edge_by_tier.get(tier, self.min_edge)

        # 鎶曟敞鍐崇瓥閫昏緫
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

            # 鍒嗗眰鍒嗘暟
            kelly_frac_tiered = kelly_frac * get_kelly_fraction(tier)

            # 涓婇檺绾︽潫锛堜繚瀹堬細涓嶈秴杩?tier 涓婇檺锛屼笖鍏ㄥ眬涓嶈秴杩?10%锛?
            max_stake = min(
                self.bankroll * 0.10,  # 鍏ㄥ眬涓婇檺 10%
                self.bankroll * get_max_stake_frac(tier),
            )

            if self.use_kelly:
                stake = min(
                    self.bankroll * kelly_frac_tiered,
                    max_stake,
                )
            else:
                # 绛夐鎶曟敞
                if tier in (ConfidenceTier.ELITE, ConfidenceTier.MAX, ConfidenceTier.VERY_HIGH):
                    flat = 20.0
                elif tier == ConfidenceTier.HIGH:
                    flat = 10.0
                else:
                    flat = 5.0
                stake = min(flat, self.bankroll * 0.05)

            bet_stake = round(max(stake, 0.0), 2)

        # 涓嶅湪姝ゅ缁撶畻 鈥?澶栭儴璋冪敤 settle()
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
            won=None,  # 寰呯粨绠?
            profit=0.0,
            odds_implied_prob=round(implied_prob, 4),
            edge=round(edge_val, 4),
        )

        return decision

    def settle_bet(self, decision: BetDecision) -> BetDecision:
        """
        缁撶畻鎶曟敞锛氭牴鎹疄闄呯粨鏋滄洿鏂扮泩浜?

        Modifies decision in-place (won, profit) and updates bankroll.
        """
        self.iteration += 1

        if decision.bet_on is None:
            decision.won = None
            decision.profit = 0.0
        elif decision.bet_on == decision.actual_outcome:
            # 璧簡
            decision.won = True
            decision.profit = decision.bet_stake * (decision.bet_odds - 1)
            self.bankroll += decision.profit
        else:
            # 杈撲簡
            decision.won = False
            decision.profit = -decision.bet_stake
            self.bankroll -= decision.bet_stake

        # 璺熻釜鏋佸€?
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
        浠庡巻鍙查娴嬫暟鎹绠楁瘡灞傜殑鏍″噯鍥犲瓙銆?

        鏍″噯鍥犲瓙 = accuracy / avg_confidence锛堟瘡灞傚垎鍒绠楋級
        鍚钩婊戦槻姝㈤櫎闆讹紝涓婇檺 max_factor 闃叉杩囧害淇銆?

        Args:
            y_true: list[str] 鈥?鐪熷疄缁撴灉 ['H','D','A',...]
            y_prob_list: list[dict] 鈥?妯″瀷棰勬祴姒傜巼
                         [{'H':0.6,'D':0.25,'A':0.15}, ...]
            tiers: list[str] 鈥?姣忓満瀵瑰簲鐨勫垎灞?['VHigh','Medium',...]
            max_factor: float 鈥?鏍″噯鍥犲瓙涓婇檺锛岄粯璁?1.5

        Returns:
            dict[str, float] 鈥?姣忓眰鐨勬牎鍑嗗洜瀛?
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
            # 骞虫粦锛氬鏋?accuracy 鎺ヨ繎 0 鎴?avg_conf 鎺ヨ繎 0锛岀敤 1.0
            if avg_conf < 0.01 or accuracy < 0.01:
                factors[tier] = 1.0
            else:
                factors[tier] = min(accuracy / avg_conf, max_factor)

        return factors

    def get_betting_stats(self) -> BettingResult:
        """姹囨€诲叏閮ㄦ姇娉ㄧ粺璁?""
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

        # 鈹€鈹€ 鎸夌疆淇″害鍒嗗眰缁熻鎶曟敞 鈹€鈹€
        tier_decisions = {}
        tier_pred_total = {}

        for d in self.decisions:
            # 鎶曟敞缁熻
            if d.bet_on is not None:
                tier_decisions.setdefault(d.tier, []).append(d)
            # 棰勬祴鍑嗙‘鐜囩粺璁★紙鎵€鏈夋瘮璧涳紝涓嶇鏄惁鎶曟敞锛?
            tier_pred_total.setdefault(d.tier, {"total": 0, "correct": 0})
            tier_pred_total[d.tier]["total"] += 1
            if d.predicted_outcome == d.actual_outcome:
                tier_pred_total[d.tier]["correct"] += 1

        # 鎶曟敞缁熻
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

        # 鏈€澶у洖鎾?
        max_drawdown = self._calc_max_drawdown()

        # 鍒嗗眰缁熻
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

        # 鍒嗗眰棰勬祴鍑嗙‘鐜囷紙鎵€鏈夋瘮璧涳級
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
        """璁＄畻 peak-to-trough 鏈€澶у洖鎾?""
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
        """鐢熸垚鍙鎽樿"""
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


# 鈹€鈹€鈹€ 鍥炴祴杩愯鍣?鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€

def run_tiered_backtest(
    df: pd.DataFrame,
    predictor,
    initial_bankroll: float = 10000.0,
    min_edge: float = 0.03,
    use_kelly: bool = True,
    verbose: bool = True,
) -> BettingResult:
    """
    鍦ㄥ凡鏈夌壒寰?棰勬祴鐨勬暟鎹笂璺戠疆淇″害鍒嗗眰鍥炴祴

    Args:
        df: 鍚壒寰佸垪 + result 鍒楃殑姣旇禌鏁版嵁锛堝凡 predict_proba 浜嗗悧锛熼€氬父鍦ㄥ閮ㄩ娴嬶級
        predictor: 宸茶缁冪殑 FootballPredictor 瀹炰緥
        initial_bankroll: 鍒濆璧勯噾
        min_edge: 鏈€灏?edge 闂ㄦ
        use_kelly: 鏄惁浣跨敤 Kelly
        verbose: 鏄惁鎵撳嵃杩涘害

    Returns:
        BettingResult 瀵硅薄
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
        # 鏋勫缓鐗瑰緛琛?
        feat_row = row[available].fillna(0).to_frame().T
        try:
            pred = predictor.predict(feat_row)
        except Exception as e:
            logger.warning(f"棰勬祴澶辫触 {row.get('home_team', '?')}: {e}")
            continue

        if isinstance(pred, list):
            pred = pred[0]

        model_probs = {
            "H": pred.home_win_prob,
            "D": pred.draw_prob,
            "A": pred.away_win_prob,
        }

        # 鑾峰彇璧旂巼锛堜粠鏁版嵁涓級
        odds_series = {
            "H": row.get("AvgH", row.get("B365H", 0)),
            "D": row.get("AvgD", row.get("B365D", 0)),
            "A": row.get("AvgA", row.get("B365A", 0)),
        }

        # 澶勭悊 NaN 璧旂巼
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
    y_prob: np.ndarray,            # shape (n, 3) 鈥?宸茶缁冪殑妯″瀷瀵瑰悇鍦烘瘮璧涚殑棰勬祴姒傜巼
    inv_label_map: dict,
    verbose: bool = True,
    **cbs_kwargs,
) -> BettingResult:
    """
    鐩存帴浼犲叆棰勬祴姒傜巼鐭╅樀锛岃烦杩囬噸鏂伴娴嬶紙鑺傜渷鏃堕棿锛?

    Args:
        df: 姣旇禌鏁版嵁锛堝惈璧旂巼鍒楀拰 result 鍒楋級
        y_prob: (n, 3) 棰勬祴姒傜巼鐭╅樀 [P(H), P(D), P(A)]
        inv_label_map: {0: "H", 1: "D", 2: "A"}
        **cbs_kwargs: 浼犵粰 ConfidenceBettingSystem 鐨勫弬鏁?

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


# 鈹€鈹€鈹€ 杈撳嚭鎵撳嵃 鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€

def _print_results(result: BettingResult):
    """缇庤鍦版墦鍗板洖娴嬬粨鏋?""
    s = result.summary

    print(f"\n{'='*60}")
    print(f"  缃俊搴﹀垎灞傛姇娉ㄥ洖娴嬬粨鏋?)
    print(f"{'='*60}")
    print(f"  鍏ㄥ眬缁熻:")
    print(f"    鎬绘瘮璧?    {s['total_matches']} 鍦?)
    print(f"    鎶曟敞鍦烘:  {s['total_bets']} ({s['bet_rate']})")
    print(f"    鑳滅巼:      {s['win_rate']}")
    print(f"    鎬绘姇娉ㄩ:  {s['total_staked']}")
    print(f"    鎬荤泩浜?    {s['total_profit']}")
    print(f"    ROI:       {s['roi']}")
    print(f"    骞冲潎璧旂巼:  {s['avg_odds']}")
    print(f"    鏈€澶у洖鎾?  {s['drawdown']}")
    print(f"\n  璧勯噾鍙樺寲:")
    print(f"    鍒濆璧勯噾:  {s.get('final_bankroll', result.initial_bankroll)}")
    print(f"    Kelly ROI: {s['kelly_roi']}")
    print(f"    璧勯噾鍙樺寲:  {s['bankroll_change']}")
    print(f"    鏈€澶у洖鎾?  {s['drawdown']}")

    print(f"\n  棰勬祴鍑嗙‘鐜囧垎灞?(鍏ㄩ儴 {result.total_matches} 鍦?:")
    print(f"  {'鍒嗗眰':12s} {'鍦烘':>6s} {'鍑嗙‘鐜?:>8s}")
    print(f"  {'鈹€'*28}")
    # 鎸夌疆淇″害浠庨珮鍒颁綆鎺掑簭
    tier_order = ["Max", "Elite", "VHigh", "High", "Medium", "Low"]
    for t in tier_order:
        if t in result.tier_prediction_accuracy:
            # 鎵惧埌璇ュ眰姣旇禌鏁?
            n_matches = sum(1 for d in result.decisions if d.tier == t)
            print(f"  {t:12s} {n_matches:>6d} {result.tier_prediction_accuracy[t]:>7.1%}")

    print(f"\n  鎶曟敞鍒嗗眰缁熻:")
    print(f"  {'鍒嗗眰':12s} {'鎶曟敞':>5s} {'鑳滅巼':>7s} {'ROI':>7s} {'鐩堜簭':>10s} {'鎶曟敞棰?:>10s}")
    print(f"  {'鈹€'*52}")
    for t in tier_order:
        if t in result.tier_stats:
            ts = result.tier_stats[t]
            profit_str = f"{ts.total_profit:+.0f}"
            staked_str = f"{ts.total_staked:.0f}"
            print(f"  {t:12s} {ts.total_bets:>5d} {ts.accuracy:>6.1%} {ts.roi:>6.2%} "
                  f"{profit_str:>10s} {staked_str:>10s}")

    print(f"\n  {'鈹€'*52}")
    print(f"  鍚堣: {result.total_bets:>5d}鎶?{result.win_rate:>6.1%} {result.roi:>6.2%} "
          f"{result.total_profit:+.0f} {result.total_staked:.0f}")


def export_results(result: BettingResult, path: str | Path | None = None) -> dict:
    """
    灏嗗洖娴嬬粨鏋滃鍑轰负鍙簭鍒楀寲瀛楀吀锛堝彲閫夊瓨 JSON锛?
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
            for d in result.decisions[-50:]  # 鍙繚鐣欐渶杩?50 鍦?
        ],
    }

    if path:
        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        logger.info(f"缁撴灉宸插鍑? {path}")

    return data
