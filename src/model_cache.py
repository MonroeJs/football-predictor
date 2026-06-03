"""
模型缓存 — 避免每次请求重新训练

保存训练好的模型到 models/ 目录，启动时预加载。
"""
from pathlib import Path
import pickle
import os

MODELS_DIR = Path(__file__).parent.parent / 'models'
MODELS_DIR.mkdir(exist_ok=True)

def save_model(model, league_key: str):
    """保存模型到文件"""
    path = MODELS_DIR / f'{league_key}_model.pkl'
    with open(path, 'wb') as f:
        pickle.dump(model, f)
    print(f'  Model saved: {path}')

def load_model(league_key: str):
    """从文件加载模型"""
    path = MODELS_DIR / f'{league_key}_model.pkl'
    if path.exists():
        with open(path, 'rb') as f:
            model = pickle.load(f)
        print(f'  Model loaded: {path}')
        return model
    return None

def has_model(league_key: str) -> bool:
    """检查模型是否存在"""
    return (MODELS_DIR / f'{league_key}_model.pkl').exists()
