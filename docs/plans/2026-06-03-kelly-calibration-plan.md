# 执行计划：修复 Kelly 校准因子

基于设计文档 `docs/plans/2026-06-03-kelly-calibration-design.md`

## 任务 1：修复校准因子 cap + 新增方法

**文件：** `src/betting_system.py`

**改动 1 — `evaluate_bet()` 中去掉 cap（约第 235 行）**
```python
# 旧
cal_factor = min(raw_cal, 1.0)  # NEVER amplify

# 新
cal_factor = raw_cal  # 允许 > 1.0（已由外部 cap 在 1.5 控制）
```

同时更新相关注释。

**改动 2 — 新增 `compute_calibration_factors()` 类方法**

```python
@staticmethod
def compute_calibration_factors(y_true, y_prob, tiers, max_factor=1.5):
    """
    从回测数据计算每层的校准因子。
    
    校准因子 = accuracy / avg_confidence（每层分别计算）
    含平滑防止除零，上限 max_factor 防止过度修正。
    
    Args:
        y_true: list[str] — 真实结果 ['H','D','A',...]
        y_prob: list[dict] — 模型概率 [{'H':0.6,'D':0.25,'A':0.15}, ...]
        tiers: list[str] — 每场的分层 ['VHigh','Medium',...]
        max_factor: float — 上限，默认 1.5
    
    Returns:
        dict[str, float] — {'VHigh': 1.18, 'Elite': 1.14, ...}
    """
```

**验证：**
- 本地 `pytest tests/ -v` 全部通过

## 任务 2：新增校准测试

**文件：** `tests/test_calibration.py`

测试内容：
1. `test_calibrate_increases_prob` — 因子 1.2 时概率从 0.6 升到 0.72
2. `test_calibrate_decreases_prob` — 因子 0.8 时概率从 0.6 降到 0.48
3. `test_calibrate_no_change` — 因子 1.0 不变
4. `test_calibrate_capped` — 因子 2.0 被 cap 到 1.5
5. `test_compute_calibration_factors` — 模拟数据验证计算
6. `test_compute_calibration_smoothing` — 单场比赛防止除零

**TDD 流程：** 先写测试 → 确认 fail（方法不存在）→ 实现 → 确认 pass

**验证：**
- `pytest tests/ -v` 全部通过
