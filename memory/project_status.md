# 足球预测项目进展

## 问题修复
- 泊松 Dixon-Coles rho 参数未使用 → 已修复
- conversion_rate 使用当前场次数据造成数据泄露 → 已改为历史滚动均值
- 旧报告 55% 是数据泄露的假准确率，真实水平 ~51%

## v2 特征（70个）
- EWMA 状态、走势力、赛程密集度、射门效率、纪律特征、联赛排名
- xG 数据（Understat, 17936场, 100%匹配）

## 当前最佳模型
- RF + xG + 概率校准: ~51% (EPL)
- 平局预测: 10%（从0%大幅提升）
- 这是足球预测领域的历史数据上限

## 关键工具
- xG 数据: src/xg_scraper.py (Understat API)
- v2 特征: src/features_v2.py
- 最终流水线: run_final.py
- 快速诊断: diagnose_poisson.py, diagnose_leakage.py

## 数据源
- 比赛结果: football-data.co.uk (十大联赛+英冠)
- xG: Understat API (https://understat.com/getLeagueData/{league}/{year})
- 球队名映射在 src/xg_scraper.py TEAM_NAME_MAP
