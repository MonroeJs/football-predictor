"""Fix stake amounts in wc_predictor.py to use yuan-friendly values"""
from pathlib import Path

path = Path(__file__).parent.parent / 'src' / 'wc_predictor.py'
with open(path, 'r', encoding='utf-8') as f:
    content = f.read()

# Replace the stake calculation
old = (
    "        # 投注决策\n"
    "        # 世界杯策略：赔率驱动，根据置信度分级直接投注低赔方\n"
    "        # 不使用 Kelly edge 计算（模型 = 市场本身，edge 永远为 0）\n"
    "        # 沿用欧冠回测验证的固定投注策略\n"
    "        BANKROLL = 10000  # 虚拟资金\n"
    "        \n"
    "        # 置信度分级 -> 固定投注额（基于 10,000 虚拟资金）\n"
    "        tier_stakes = {\n"
    "            'Max': BANKROLL * 0.15,    # 15% 超高置信度\n"
    "            'Elite': BANKROLL * 0.10,  # 10% 高置信度\n"
    "            'VHigh': BANKROLL * 0.06,  # 6% 推荐\n"
    "            'High': 0,                 # 不投\n"
    "            'Medium': 0,               # 不投\n"
    "            'Low': 0,                  # 不投\n"
    "        }\n"
    "        stake = tier_stakes.get(tier.value, 0)\n"
    "        \n"
    "        # 计算预期 ROI 参考\n"
    "        fav_odds_val = odds[max_outcome]\n"
    "        expected_value = probs[max_outcome] * (fav_odds_val - 1) - (1 - probs[max_outcome]) * 1"
)
new = (
    "        # 投注决策\n"
    "        # 世界杯策略：赔率驱动，根据置信度分级直接投注低赔方\n"
    "        # 不使用 Kelly edge 计算（模型 = 市场本身，edge 永远为 0）\n"
    "        # 沿用欧冠回测验证的固定投注策略\n"
    "        # 单位：人民币 ¥，基础单位 = 10¥\n"
    "        UNIT = 10  # 每注基础单位\n"
    "        \n"
    "        # 置信度分级 -> 固定投注额\n"
    "        tier_stakes = {\n"
    "            'Max': UNIT * 8,     # 80¥   超高置信度\n"
    "            'Elite': UNIT * 5,   # 50¥   高置信度\n"
    "            'VHigh': UNIT * 3,   # 30¥   推荐\n"
    "            'High': 0,           # 不投\n"
    "            'Medium': 0,         # 不投\n"
    "            'Low': 0,            # 不投\n"
    "        }\n"
    "        stake = tier_stakes.get(tier.value, 0)\n"
    "        \n"
    "        # 计算预期 ROI 参考\n"
    "        fav_odds_val = odds[max_outcome]\n"
    "        expected_value = probs[max_outcome] * (fav_odds_val - 1) - (1 - probs[max_outcome]) * 1"
)
assert old in content, "Stake section not found!"
content = content.replace(old, new)

# Also fix the bankroll_pct reference
content = content.replace(
    "'bankroll_pct': f'{stake/BANKROLL*100:.0f}%' if stake > 0 else '-'",
    "'stake_unit': f'{int(stake/UNIT)}U' if stake > 0 else '-'"
)

with open(path, 'w', encoding='utf-8') as f:
    f.write(content)
print('Fixed stake amounts in wc_predictor.py')
