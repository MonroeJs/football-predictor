# 足球预测分析脚本 — 设计文档

## 概述

五大联赛（EPL, La Liga, Serie A, Bundesliga, Ligue 1）足球比赛预测分析脚本。第一版聚焦历史数据回测，使用泊松分布和 ML 模型进行比赛结果预测。

## 技术栈

- Python 3.13
- pandas, numpy — 数据处理
- scikit-learn — 机器学习
- requests — 数据获取
- matplotlib, seaborn — 可视化（第二版）

## 项目结构

```
football-predictor/
├── data/
│   ├── raw/                 # 原始数据集
│   └── processed/           # 清洗后的特征数据
├── src/
│   ├── __init__.py
│   ├── data_loader.py       # 数据加载与清洗
│   ├── features.py          # 特征工程
│   ├── poisson.py           # 泊松分布预测
│   ├── ml_models.py         # scikit-learn 模型
│   ├── backtest.py          # 回测评估
│   └── utils.py             # 工具函数
├── notebooks/
│   └── analysis.ipynb       # Jupyter Notebook
├── predict.py               # CLI 入口
├── config.py                # 全局配置
├── requirements.txt
└── docs/plans/
    └── 2026-05-17-football-predictor-design.md
```

## 核心模块

### data_loader.py
- 读取 CSV/JSON 格式的历史比赛数据
- 标准化字段：联赛、赛季、日期、主队、客队、主队进球、客队进球
- 数据校验与清洗

### features.py
- 近期状态特征（近5场胜率、场均进球/失球）
- 主客场差异化统计
- Elo 评分计算
- 对赛往绩特征
- 攻击力/防守力指数

### poisson.py
- 基于泊松分布计算预期进球
- 生成比分概率矩阵（0-0 到 5-5+）
- 汇总为胜平负概率

### ml_models.py
- 逻辑回归（baseline）
- 随机森林（主力模型）
- 特征重要性分析
- 概率校准

### backtest.py
- 滑动窗口回测
- 准确率、精确率、召回率、F1
- 混淆矩阵
- 模拟投注收益曲线

## 数据源策略

第一版使用公开数据集 + 内置模拟测试数据确保可运行。
后续可接入 football-data.org API 或 FBref 爬虫补充。

## 回测方法

使用时间序列滑动窗口：
- 训练窗口：前 380 场比赛（约1个赛季）
- 测试窗口：下 38 场比赛（1轮）
- 滑动步长：19 场比赛（半轮）
