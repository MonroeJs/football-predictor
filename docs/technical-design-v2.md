# 世界杯 2026 预测系统 — 技术方案 v2

## 一、架构变更

```
当前:                          改造后:
Flask + JSON 静态数据           Flask + SQLite + 定时任务
predictions → 每次全部重算       predictions → 缓存 + 增量更新
run_wc_odds.csv ← 手动编辑      run_wc_odds.csv ← 自动更新
                               + results.db ← 持久化结果
                               + cron 定时拉赔率
```

## 二、SQLite 数据库设计

### 表结构

```sql
-- 比赛表（从 CSV 导入，可刷新）
CREATE TABLE matches (
    id INTEGER PRIMARY KEY,
    date TEXT NOT NULL,           -- '2026-06-11'
    group_name TEXT NOT NULL,     -- 'A', 'B', ...
    home_team TEXT NOT NULL,
    away_team TEXT NOT NULL,
    b365h REAL,                   -- 最新赔率
    b365d REAL,
    b365a REAL,
    predicted_winner TEXT,        -- 预测结果
    confidence REAL,              -- 置信度 0-1
    tier TEXT,                    -- Max/Elite/VHigh/...
    suggested_stake REAL,         -- 建议投注额
    
    -- 结果追踪
    actual_winner TEXT,           -- 'H'/'D'/'A' (开赛后填入)
    home_goals INTEGER,           -- 实际主队进球
    away_goals INTEGER,           -- 实际客队进球
    result_confirmed INTEGER DEFAULT 0, -- 是否已确认
    
    -- 投注记录
    bet_placed INTEGER DEFAULT 0, -- 是否下注
    bet_amount REAL,              -- 实际下注金额
    bet_profit REAL,              -- 实际盈亏
    
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- 赔率变动日志
CREATE TABLE odds_history (
    id INTEGER PRIMARY KEY,
    match_id INTEGER,
    b365h_old REAL,
    b365d_old REAL,
    b365a_old REAL,
    b365h_new REAL,
    b365d_new REAL,
    b365a_new REAL,
    changed_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (match_id) REFERENCES matches(id)
);

-- 统计快照（定时保存，用于趋势图）
CREATE TABLE stats_snapshots (
    id INTEGER PRIMARY KEY,
    date TEXT NOT NULL,
    total_predictions INTEGER,
    correct_predictions INTEGER,
    accuracy REAL,
    total_bets REAL,
    total_profit REAL,
    snapshot_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
```

### 数据流

```
                 ┌──────────────┐
CSV ──导入──────▶│   matches    │◀── 结果录入（页面表单）
                 │  (SQLite)    │
                 └──────┬───────┘
                        │
           ┌────────────┼────────────┐
           ▼            ▼            ▼
    赔率更新脚本   准确率统计      API 输出
    (cron/手动)   (后端计算)    (JSON → 前端)
```

## 三、新增/修改 API

```python
# 现有 API 不变，新增：

POST /api/match/<id>/result      # 录入比赛结果
GET  /api/stats                  # 实时统计（准确率、盈亏）
GET  /api/history                # 历史预测记录
POST /api/refresh-odds           # 手动触发赔率更新

# 修改已有 API：
GET  /api/predictions            # 增加实际结果字段
GET  /wc2026                     # 增加统计面板数据
```

## 四、页面更新

### 新增 Tab：追踪

```
[今日推荐 | 全部赛程 | 日历 | 分组出线 | 📊 追踪]
                                            ↑ 新增
```

**追踪 Tab 内容：**
- 累计准确率卡片（总/按分级）
- 最近比赛结果列表（绿色=命中，红色=未中）
- 准确率趋势图（Chart.js 折线图）
- 投注盈亏汇总

### 赛程表的变更

每条比赛行增加操作：
- 未开始：显示预测和赔率
- 进行中/已结束：显示录入结果按钮
- 已录入：显示实际结果 + 命中/未中标记

## 五、赔率更新机制

### 手动触发
页面顶部按钮"刷新赔率" → POST `/api/refresh-odds`

### 定时自动
使用 Python `schedule` 库或 Windows 任务计划程序：
```
每天 10:00 和 14:00 自动拉取最新赔率
```

### 更新脚本
```python
# scripts/update_odds.py
# 1. 下载 football-data.co.uk/fixtures.csv
# 2. 匹配 WC 比赛
# 3. 更新 SQLite + 记录变动
# 4. 重新计算预测
```

## 六、实现步骤

```
步骤 1: SQLite 数据库初始化 + 模型   [30min]
步骤 2: CSV→SQLite 导入脚本         [30min]
步骤 3: 结果录入 API                [30min]
步骤 4: 追踪页面（统计+历史）         [60min]
步骤 5: 准确率计算 + 趋势图         [30min]
步骤 6: 赔率更新脚本                [45min]
步骤 7: 手动触发 + 定时任务          [30min]
步骤 8: 投注盈亏计算                [30min]
步骤 9: 联调测试                    [30min]
────────────────────────────
总计: ~5小时
```

## 七、风险

| 风险 | 缓解 |
|------|------|
| 开赛后 football-data 更新延迟 | 手动录入备用 |
| 同分多队情况复杂 | 简化为胜负平统计 |
| 数据库锁定 | SQLite WAL 模式 |

---

**审批**：⬜ 待大哥评审
