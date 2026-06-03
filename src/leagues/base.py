"""
联赛抽象基类 — 所有联赛的通用接口

每个联赛需要实现:
  - load_matches()    → 加载并标准化比赛数据
  - get_predictions() → 运行预测
  - get_standings()   → 积分榜 (联赛) 或出线概率 (杯赛)
  - get_info()        → 联赛元信息
"""
from abc import ABC, abstractmethod
from pathlib import Path
from typing import Optional, Any
import pandas as pd
import numpy as np

from config import RAW_DIR


class BaseLeague(ABC):
    """联赛抽象基类"""

    # 类属性 — 子类覆盖
    key: str = ""               # 唯一标识，如 "epl", "j1", "wc2026"
    name: str = ""              # 显示名，如 "Premier League"
    country: str = ""           # 国家/地区
    league_type: str = "league" # "league" | "tournament"
    data_source: str = ""       # 数据来源描述
    has_ml_model: bool = False  # 是否已训练 ML 模型

    # 页面配置
    show_groups: bool = False   # 是否显示分组 (仅锦标赛)
    show_standings: bool = True # 是否显示积分榜
    show_goals: bool = False    # 是否显示进球数
    
    def __init__(self):
        self._matches: Optional[pd.DataFrame] = None
        self._predictions: Optional[list] = None

    # ─── 必须实现 ───

    @abstractmethod
    def load_matches(self) -> pd.DataFrame:
        """加载并返回标准化后的比赛数据"""
        ...

    @abstractmethod
    def get_predictions(self) -> list[dict]:
        """返回预测结果列表"""
        ...

    # ─── 可选实现 ───

    def get_standings(self) -> Optional[dict]:
        """联赛积分榜 / 锦标赛出线概率"""
        return None

    def get_info(self) -> dict:
        """联赛元信息"""
        return {
            'key': self.key,
            'name': self.name,
            'country': self.country,
            'type': self.league_type,
            'data_source': self.data_source,
            'has_ml_model': self.has_ml_model,
            'show_groups': self.show_groups,
            'show_standings': self.show_standings,
            'show_goals': self.show_goals,
        }

    def get_team_list(self) -> list[str]:
        """返回当前赛季参赛队伍"""
        if self._matches is not None and not self._matches.empty:
            teams = pd.unique(
                pd.concat([self._matches['home_team'], self._matches['away_team']])
            )
            return sorted(teams)
        return []

    # ─── 工具方法 ───

    def _to_serializable(self, obj: Any) -> Any:
        """将数据转为 JSON 可序列化格式"""
        if isinstance(obj, (np.integer,)):
            return int(obj)
        if isinstance(obj, (np.floating,)):
            return float(obj)
        if isinstance(obj, np.bool_):
            return bool(obj)
        if isinstance(obj, pd.Timestamp):
            return str(obj.date())
        return obj

    def _serialize_predictions(self, predictions: list[dict]) -> list[dict]:
        """序列化预测结果"""
        result = []
        for p in predictions:
            serialized = {}
            for k, v in p.items():
                serialized[k] = self._to_serializable(v)
            result.append(serialized)
        return result
