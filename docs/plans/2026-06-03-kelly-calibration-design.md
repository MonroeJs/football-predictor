# 设计方案：修复 Kelly 校准因子导致投注不触发的问题

## 问题

`ConfidenceBettingSystem.evaluate_bet()` 中的校准逻辑：

```python
raw_cal = self.calibration_factors.get(tier.value, 1.0)
cal_factor = min(raw_cal, 1.0)  # ❌ NEVER amplify
model_prob = model_probs[pred_outcome] * cal_factor
```

- `min(raw_cal, 1.0)` 强制校准因子只能降不能升
- 模型是保守型的（预测 64% 但实际胜率 76%），实际需要因子 **> 1.0**
- 结果：概率被压低 → edge 负 → Kelly 不触发 → 0 次投注

## 目标

让校准因子 > 1.0 生效，使模型概率能正确校准到实际胜率水平，从而产生正 edge，触发 Kelly 投注。

## 改动范围

### 文件：`src/betting_system.py`

**1. `ConfidenceBettingSystem.evaluate_bet()` — 去掉 cap**

```python
# 旧
cal_factor = min(raw_cal, 1.0)

# 新
cal_factor = raw_cal  # 允许 > 1.0
```

同时去掉注释中的 "NEVER amplify" 和 "cal_factor > 1 说明模型保守，维持原值" 的误导逻辑。

**2. 新增方法 `compute_calibration_factors(y_true, y_prob, tiers)`**

参数：
- `y_true`: 真实结果标签 (H/D/A)
- `y_prob`: 模型预测概率 (N×3 array)
- `tiers`: 每场比赛的分层标签

返回值：dict[str, float] — 每层校准因子（accuracy / avg_confidence）

计算方法：
- 对每个 tier，计算 accuracy（正确预测比例）和 avg_confidence（平均最高概率）
- calibration_factor = accuracy / avg_confidence（含平滑防止除零）

**3. 新增方法 `calibrate_probabilities(self, model_probs, tier, calibration_factors)`**（可选，逻辑简单可以不单独抽方法）

### 文件：新增 `tests/test_calibration.py`

测试内容：
- `test_calibrate_increases_prob` — 校准因子 1.2 → 概率从 0.6 变为 0.72
- `test_calibrate_decreases_prob` — 校准因子 0.8 → 概率从 0.6 变为 0.48
- `test_calibrate_no_change` — 校准因子 1.0 → 不变
- `test_compute_calibration_factors` — 模拟数据验证计算逻辑

## 不做（YAGNI）

- ❌ 不改模型训练代码
- ❌ 不改 backtest 脚本（只修 betting_system 本身）
- ❌ 不加 Platt Scaling / isotonic regression（阶段 C 的活）
- ❌ 不改变投注决策逻辑（只修校准因子问题）

## 风险

- 校准因子 > 1.0 可能过度修正，导致过度自信投注
- 解决方案：校准因子上限 cap 在 1.5（防止极端值）
- 校准因子应该从训练数据计算，不用回测数据（防 look-ahead bias）
