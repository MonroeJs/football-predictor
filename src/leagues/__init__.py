"""
联赛注册中心

所有联赛继承 BaseLeague，注册到 REGISTRY 后可通过 key 获取。
"""
from typing import Optional

REGISTRY = {}

def register(cls):
    """装饰器：将联赛类注册到 REGISTRY"""
    key = cls.key
    REGISTRY[key] = cls
    return cls

def get_league(key: str):
    """获取联赛类"""
    cls = REGISTRY.get(key)
    if cls:
        return cls()
    return None

def list_leagues():
    """列出所有已注册联赛"""
    return {k: v.name for k, v in REGISTRY.items()}
