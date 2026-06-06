# 世界杯赔率更新 — Odds API 集成

**日期**: 2026-06-06
**状态**: 设计文档（待批准）

## 目标

用 [the-odds-api.com](https://the-odds-api.com) 的真实博彩赔率替换 `run_wc_odds.csv` 中的模拟赔率。

## 架构

```
Odds API (Paddy Power)          run_wc_odds.csv          WC Predictor
┌─────────────────┐    fetch    ┌──────────────────┐   reads    ┌──────────────┐
│ 72 matches      │ ──────────→ │ date,group,home,  │ ─────────→ │ app.py       │
│ Paddy Power h2h │            │ away,B365H/D/A    │           │ wc_2026.py   │
│ JSON response   │            │ (B365 = 泛称)      │           │ 面板/预测     │
└─────────────────┘            └──────────────────┘           └──────────────┘
       │                               ↑
       │ 一次执行                        │ 保留 CSV 格式，项目其他逻辑不动
       ▼                               │
┌─────────────────┐                    │
│ fetch_wc_odds.py │ ──────────────────┘
│ (新脚本)         │  生成新的 run_wc_odds.csv
│ = fetch + map   │
│   + write CSV   │
└─────────────────┘
```

## 关键设计决策

### 1. 选哪个庄家

Paddy Power — 72/72 场全覆盖，信誉好， odds 与其他大庄一致。

备选：可以用多庄均值（更抗偏差）。但初版用单庄简单可靠，后续可升级。

### 2. 列名保留 B365

`run_wc_odds.csv` 的列名是 `B365H/B365D/B365A`，wc_2026.py 直接读这些列。
虽然实际来源是 Paddy Power，但列名不改，因为：
- 不改任何现有代码
- 列名只是占位符，消费者只看数值

### 3. 队名映射

| API (Paddy Power) | CSV (现有) |
|---|---|
| Bosnia & Herzegovina | Bosnia |
| Curaçao | Curacao |
| Czech Republic | Czechia |
| 其他 45 队 | 完全一致 |

映射写在 `fetch_wc_odds.py` 的 `TEAM_NAME_MAP` 字典里。

### 4. API Key 管理

存在项目根 `.env`，用 `python-dotenv` 或 `os.getenv` 加载。
`.env` 已加入 `.gitignore`。

### 5. 回退机制

如果 API 调用失败，保留现有 CSV 不变，报错但不中断。

## 测试策略

1. **API 连通性** — 调用 API 返回 200
2. **队名映射** — 所有 48 支队都能正确映射
3. **CSV 输出** — 输出完整的 72 行 CSV，格式与现有一致
4. **集成验证** — 新 CSV 喂给 `wc_2026.py` 能正常出预测

## 执行计划

1. 写 `scripts/fetch_wc_odds.py` — 获取 API 数据 + 队名映射 + 生成 CSV
2. 运行生成 `run_wc_odds.csv`
3. 启动 Flask app 验证面板正确显示新赔率
4. 清理测试文件
