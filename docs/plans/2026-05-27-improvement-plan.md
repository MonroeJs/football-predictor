# 足球预测模型提升计划

## Step 1: 修泊松回测bug（低投入高回报）
- 排查全量回测 28% 的问题
- 检查滑窗回测中 attack/defense strength 的计算是否正确
- 检查 feature leakage

## Step 2: 加 xG 数据源（中投入高回报）
- 编写 FBref/Understat 爬虫
- xG, xGA, xPTS 等指标
- 整合到特征流水线

## Step 3: 深度特征工程
- 时序衰减加权（指数加权代替滚动平均）
- 主客场独立 Elo
- 联赛排名/积分榜位置
- 赛程密集度（距上场比赛天数）
- 连胜/连败走势特征
- 射门数据特征（射正率、转化率）
- 纪律特征（红黄牌累积）

## Step 4: 模型升级
- 超参数搜索（Optuna）
- 概率校准（Platt scaling）
- Meta-stacking ensemble
- LightGBM / CatBoost

## Step 5: 评估体系
- Brier score
- Ranked Probability Score
- ROI / Expected Profit
- Calibration curves
