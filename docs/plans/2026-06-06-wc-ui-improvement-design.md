# 世界杯面板改版 — 增强分析 & UI 设计

**日期**: 2026-06-06
**状态**: 设计文档

## 目标

1. 全面改进比赛卡片 UI，展示更多有用信息
2. 增强推断依据分析，结合球队实力 + 球员能力 + 联赛表现
3. 集成球员阵容数据（Wikipedia）

## 数据流

```
Wikipedia API ─→ squad scraper ─→ data/wc_squads.json
                                      │
手动录入     ─→ player_ratings  ─→ data/wc_player_ratings.json
                                      │
Odds API     ─→ run_wc_odds.csv  ──── │ ─→ wc_predictor.py ─→ 增强分析文本
                                      │
TEAM_ELO     ──────────────────────── │ ─→ 推断依据引擎
```

## 组件设计

### 1. Squad Scraper (`scripts/fetch_wc_squads.py`)
- 从 Wikipedia 2026 FIFA World Cup squads 页面提取
- 结构：`{team: [{name, position, club, age, caps, goals}], ...}`
- 缓存到 `data/wc_squads.json`

### 2. Player Ratings (`data/wc_player_ratings.json`)
- 手动+半自动标注每队 3-5 名核心球员
- 结构：`{player_name: {rating: 85, role: 'FW', club: '...'}}`
- 评分标准：0-99（参考 FIFA 评分体系）
- 标注策略：先覆盖 48 队约 200 名球员

### 3. 推断依据引擎（`wc_predictor.py` 增强）
分析因素（按权重）：
- **市场赔率** → 隐含概率（权重最高，赔率反映市场共识）
- **Elo 评分差** → 历史实力差距
- **阵容深度** → 核心球员平均能力值（如果数据可用）
- **球员俱乐部级别** → 球员所在联赛等级（五大联赛 vs 其他）

输出结构化分析 JSON 和可读文本。

### 4. 比赛卡片 UI（`templates/dashboard.html`）

每个比赛卡片展示：
```
┌─ Teams ──────────────────────────┐
│ 🇲🇽 Mexico     1.36    │ 🇿🇦 S.Africa│
│  Elo:1963  68.4% 20.7% 10.9%   │  ── 概率进度条
│  ═══════════●──────────────     │
│  [VHigh] 投注30¥                │
├─ 关键球员 ───────────────────────┤
│  Ochoa 84·Lozano 83·Herrera 82  │
│  vs Williams 79·Zwane 78·...    │
├─ 推断依据 ────────────────────────┤
│  • 市场赔率: Mexico 68.4% 胜算    │
│  • Elo: Mexico 领先 163 分      │
│  • 阵容: Mexico 核心球员更强      │
└──────────────────────────────────┘
```

### 5. 布局改进

- 顶栏：联赛切换 + 今日日期 + 刷新按钮
- 比赛卡片：两栏/三栏网格布局
- 筛选：显示所有 / 仅推荐 / 按置信度排序
- 追踪：结果录入 + 历史统计

## 测试策略

1. Squad scraper：正确提取所有 48 队的 26 名球员
2. Player ratings：所有 48 队至少 3 名核心球员
3. 分析引擎：生成的文本包含赔率/Elo/阵容三个维度
4. UI 模板：渲染正确，响应式
