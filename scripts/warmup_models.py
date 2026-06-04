"""
模型预热脚本 — 在后台训练所有 ML 模型并缓存
启动时运行，训练完成后页面秒加载
"""
import sys, warnings, threading, time
warnings.filterwarnings('ignore')
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

from src.model_cache import save_model, has_model
from config import TRAIN_SEASONS, CURRENT_SEASON_CODE


def train_epl():
    """训练英超模型"""
    print('[Warmup] Training EPL model...')
    from src.leagues.utils import download_european
    from src.ml_models import FootballPredictor
    from src.features_v2 import build_features_v2
    
    t0 = time.time()
    all_seasons = sorted(set(TRAIN_SEASONS + [CURRENT_SEASON_CODE]))
    df = download_european(all_seasons, 'E0')
    if df.empty:
        print('[Warmup] EPL: no data')
        return None
    
    print(f'[Warmup] EPL: {len(df)} matches loaded')
    X_train, y_train, _ = build_features_v2(df)
    if X_train is None:
        print('[Warmup] EPL: feature build failed')
        return None
    
    print(f'[Warmup] EPL: training on {len(X_train)} samples...')
    predictor = FootballPredictor(model_type='catboost')
    predictor.fit(X_train, y_train)
    save_model(predictor, 'epl')
    print(f'[Warmup] EPL: done in {time.time()-t0:.0f}s')


def train_j1():
    """训练 J1 模型"""
    print('[Warmup] Training J1 model...')
    from src.leagues.j_league import JLeague
    
    t0 = time.time()
    league = JLeague()
    df = league.load_matches()
    if df.empty:
        print('[Warmup] J1: no data')
        return None
    
    # Build simple features
    from src.features import build_features
    from src.ml_models import FootballPredictor
    
    df_feat = build_features(df)
    if 'league' not in df_feat.columns:
        df_feat['league'] = 'J1'
    
    feature_cols = [c for c in df_feat.columns if c.startswith(('form_', 'elo_', 'gd_', 'avg_'))
                   and c not in ('home_goals', 'away_goals')]
    feature_cols = [c for c in feature_cols if c in df_feat.columns]
    
    if len(feature_cols) < 3 or len(df_feat) < 100:
        print(f'[Warmup] J1: not enough features ({len(feature_cols)})')
        return None
    
    # Use built-in features target
    from src.features import build_features as bf
    # Create target from result column
    result_map = {'H': 2, 'D': 1, 'A': 0}
    y = df_feat['result'].map(result_map).fillna(-1).astype(int).values
    valid = y >= 0
    y = y[valid]
    df_feat = df_feat[valid]
    X = df_feat[feature_cols].fillna(0)[valid].values
    
    print(f'[Warmup] J1: training on {len(X)} samples, {len(feature_cols)} features...')
    predictor = FootballPredictor(model_type='catboost')
    predictor.fit(X, y)
    save_model(predictor, 'j1')
    print(f'[Warmup] J1: done in {time.time()-t0:.0f}s')


def warmup_all(background=True):
    """预热所有模型"""
    def _run():
        try:
            if not has_model('epl'):
                train_epl()
            else:
                print('[Warmup] EPL model already cached')
        except Exception as e:
            print(f'[Warmup] EPL model error (skipped): {e}')
        
        try:
            if not has_model('j1'):
                train_j1()
            else:
                print('[Warmup] J1 model already cached')
        except Exception as e:
            print(f'[Warmup] J1 model error (skipped): {e}')
    
    if background:
        t = threading.Thread(target=_run, daemon=True)
        t.start()
        print('[Warmup] Started background training...')
        return t
    else:
        _run()


if __name__ == '__main__':
    warmup_all(background=False)
