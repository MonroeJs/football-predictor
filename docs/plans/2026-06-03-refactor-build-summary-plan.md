# 执行计划：重构 _build_summary

## 目标
把 `_build_summary(self, *args)` 的 10 个 `*args` 改成命名参数。

## 改动

### 文件：`src/betting_system.py`

**改动 1 — `_build_summary` 签名（第 637 行）**
```python
# 旧
def _build_summary(self, *args) -> dict:
    tier_stats_dict, tier_pred_acc = args[-2], args[-1]
    total_matches, total_bets, total_staked, total_profit = args[0], args[1], args[2], args[3]
    roi, win_rate, avg_odds, kelly_roi = args[4], args[5], args[6], args[7]

# 新
def _build_summary(self, total_matches, total_bets, total_staked, total_profit,
                    roi, win_rate, avg_odds, kelly_roi,
                    max_drawdown, tier_stats, tier_prediction_accuracy) -> dict:
```
同时去掉负索引取值（args[-6], args[-8], args[-3]），直接用命名参数。

**改动 2 — 调用处 `get_betting_stats()`（第 592 行）**
```python
# 旧
summary = self._build_summary(
    total_matches, total_bets, total_staked, total_profit,
    roi, win_rate, avg_odds, kelly_roi, tier_stats, tier_pred_acc,
)

# 新
summary = self._build_summary(
    total_matches=total_matches,
    total_bets=total_bets,
    total_staked=total_staked,
    total_profit=total_profit,
    roi=roi,
    win_rate=win_rate,
    avg_odds=avg_odds,
    kelly_roi=kelly_roi,
    max_drawdown=max_drawdown,
    tier_stats=tier_stats,
    tier_prediction_accuracy=tier_pred_acc,
)
```

### 文件：`tests/test_betting_system.py`
不需要改，因为测试不调用 `_build_summary`（它是私有方法）。

### 验证
- `pytest tests/ -v` 全部通过（28 个）
- 没有 `*args` 出现在 `_build_summary` 中

## 不做
- ❌ 不改其他文件中的调用
- ❌ 不改 `BettingResult` 数据类
