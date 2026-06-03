"""
机器学习模型 — 使用 scikit-learn + XGBoost 预测比赛结果
"""

import pickle
import os
from pathlib import Path

import pandas as pd
import numpy as np
from sklearn.ensemble import RandomForestClassifier, GradientBoostingClassifier
from sklearn.linear_model import LogisticRegression

# XGBoost 可选 — 未安装时降级
try:
    import xgboost as xgb
    _HAS_XGBOOST = True
except ImportError:
    _HAS_XGBOOST = False

# LightGBM 可选
try:
    import lightgbm as lgb
    _HAS_LIGHTGBM = True
except ImportError:
    _HAS_LIGHTGBM = False

# CatBoost 可选
try:
    from catboost import CatBoostClassifier
    _HAS_CATBOOST = True
except ImportError:
    _HAS_CATBOOST = False
from sklearn.model_selection import (
    TimeSeriesSplit, cross_val_score, train_test_split,
)
from sklearn.metrics import (
    accuracy_score, classification_report, confusion_matrix,
)
from sklearn.preprocessing import StandardScaler
from dataclasses import dataclass

from config import ML_CONFIG, MODELS_DIR, TRAIN_CONFIG
from src.utils import logger
from src.features import get_feature_columns


@dataclass
class MLPrediction:
    """ML 模型预测结果"""
    predicted: str           # H/D/A
    home_win_prob: float
    draw_prob: float
    away_win_prob: float
    confidence: float        # 最高概率


class FootballPredictor:
    """足球比赛 ML 预测器"""

    def __init__(self, model_type: str = "random_forest", league: str | None = None):
        """
        Args:
            model_type: "random_forest" | "logistic_regression" | "gradient_boosting"
            league: 联赛代码，用于保存/加载专用模型
        """
        self.model_type = model_type
        self.league = league
        self.model = None
        self.scaler = StandardScaler()
        self.feature_names = get_feature_columns()
        self.label_map = {"H": 0, "D": 1, "A": 2}
        self.inv_label_map = {0: "H", 1: "D", 2: "A"}
        self.is_fitted = False
        self._version = 1  # 模型版本，用于向后兼容

    def _create_model(self):
        """根据配置创建模型"""
        if self.model_type == "random_forest":
            return RandomForestClassifier(**ML_CONFIG["random_forest"])
        elif self.model_type == "logistic_regression":
            return LogisticRegression(**ML_CONFIG["logistic_regression"])
        elif self.model_type == "gradient_boosting":
            return GradientBoostingClassifier(**ML_CONFIG["gradient_boosting"])
        elif self.model_type == "xgboost":
            if not _HAS_XGBOOST:
                raise ImportError("xgboost 未安装")
            return xgb.XGBClassifier(**ML_CONFIG.get("xgboost", {}))
        elif self.model_type == "lightgbm":
            if not _HAS_LIGHTGBM:
                raise ImportError("lightgbm 未安装")
            return lgb.LGBMClassifier(**ML_CONFIG.get("lightgbm", {}))
        elif self.model_type == "catboost":
            if not _HAS_CATBOOST:
                raise ImportError("catboost 未安装")
            return CatBoostClassifier(**ML_CONFIG.get("catboost", {}))
        else:
            raise ValueError(f"不支持的模型: {self.model_type}")

    def _prepare_data(
        self,
        df: pd.DataFrame,
    ) -> tuple[np.ndarray, np.ndarray]:
        """准备特征矩阵和目标向量"""
        missing = [c for c in self.feature_names if c not in df.columns]
        if missing:
            logger.warning(f"缺失特征列: {missing}")

        available = [c for c in self.feature_names if c in df.columns]
        X = df[available].fillna(0).values
        y = df["result"].map(self.label_map).values
        self._used_features = available

        return X, y

    def train(
        self,
        df: pd.DataFrame,
        use_tscv: bool = True,
    ) -> dict:
        """
        训练模型

        Args:
            df: 含特征列的比赛数据
            use_tscv: 是否使用时序交叉验证

        Returns:
            训练结果字典
        """
        tag = f"[{self.league}] " if self.league else ""
        logger.info(f"{tag}训练模型: {self.model_type}")
        X, y = self._prepare_data(df)

        if len(X) < 100:
            logger.error(f"{tag}训练数据不足: {len(X)} 条")
            return {"error": "数据不足"}

        if use_tscv:
            tscv = TimeSeriesSplit(n_splits=min(5, len(X) // 100))
            needs_scale = self.model_type in ("logistic_regression",)
            if needs_scale:
                cv_X = self.scaler.fit_transform(X)
            else:
                cv_X = X
            try:
                cv_scores = cross_val_score(
                    self._create_model(), cv_X, y,
                    cv=tscv, scoring="accuracy",
                )
                logger.info(
                    f"{tag}时序交叉验证准确率: {cv_scores.mean():.2%} ± {cv_scores.std():.2%}"
                )
            except Exception as e:
                logger.warning(f"{tag}交叉验证失败: {e}")

        # 对部分模型缩放特征
        needs_scale = self.model_type in ("logistic_regression",)
        if needs_scale:
            X_scaled = self.scaler.fit_transform(X)
            X_train, X_test, y_train, y_test = train_test_split(
                X_scaled, y, test_size=ML_CONFIG["test_size"],
                random_state=ML_CONFIG["random_state"],
                shuffle=False,
            )
        else:
            X_train, X_test, y_train, y_test = train_test_split(
                X, y, test_size=ML_CONFIG["test_size"],
                random_state=ML_CONFIG["random_state"],
                shuffle=False,
            )

        self.model = self._create_model()
        self.model.fit(X_train, y_train)

        # 评估
        y_pred = self.model.predict(X_test)
        y_prob = self.model.predict_proba(X_test)

        accuracy = accuracy_score(y_test, y_pred)
        report = classification_report(
            y_test, y_pred,
            target_names=["Home Win", "Draw", "Away Win"],
            output_dict=True,
        )
        cm = confusion_matrix(y_test, y_pred)

        self.is_fitted = True
        self.feature_importances_ = (
            self.model.feature_importances_
            if hasattr(self.model, "feature_importances_")
            else None
        )

        result = {
            "accuracy": round(accuracy, 4),
            "classification_report": report,
            "confusion_matrix": cm.tolist(),
            "test_samples": len(y_test),
        }

        if self.feature_importances_ is not None:
            used_feats = getattr(self, '_used_features', self.feature_names)
            fi_df = pd.DataFrame({
                "feature": used_feats,
                "importance": self.feature_importances_,
            }).sort_values("importance", ascending=False)
            result["feature_importance"] = fi_df.to_dict("records")

        logger.info(f"{tag}ML 模型测试集准确率: {accuracy:.2%}")
        return result

    def predict(self, features: dict | pd.DataFrame) -> MLPrediction | list[MLPrediction]:
        """
        预测单场或多场比赛

        Args:
            features: 特征字典或 DataFrame

        Returns:
            单个或列表预测结果
        """
        if not self.is_fitted:
            raise RuntimeError("模型尚未训练，请先调用 train()")

        if isinstance(features, dict):
            features = pd.DataFrame([features])

        # 确保特征列齐全
        available = [c for c in self.feature_names if c in features.columns]
        X = features[available].fillna(0).values
        self._used_features = available

        needs_scale = self.model_type in ("logistic_regression",)
        if needs_scale:
            X = self.scaler.transform(X)
        y_prob = self.model.predict_proba(X)

        results = []
        for probs in y_prob:
            pred_idx = np.argmax(probs)
            results.append(MLPrediction(
                predicted=self.inv_label_map[pred_idx],
                home_win_prob=round(float(probs[0]), 4),
                draw_prob=round(float(probs[1]), 4),
                away_win_prob=round(float(probs[2]), 4),
                confidence=round(float(probs[pred_idx]), 4),
            ))

        return results[0] if len(results) == 1 else results

    # ── 模型持久化 ──

    def get_model_path(self) -> Path:
        """返回模型文件路径"""
        league = self.league or "all"
        return MODELS_DIR / f"{league}_{self.model_type}_v{self._version}.pkl"

    def save(self, path: str | Path | None = None) -> Path:
        """保存模型到文件"""
        save_path = Path(path) if path else self.get_model_path()
        save_path.parent.mkdir(parents=True, exist_ok=True)

        payload = {
            "model_type": self.model_type,
            "league": self.league,
            "model": self.model,
            "scaler": self.scaler,
            "feature_names": self.feature_names,
            "label_map": self.label_map,
            "inv_label_map": self.inv_label_map,
            "is_fitted": self.is_fitted,
            "_version": self._version,
            "_used_features": getattr(self, '_used_features', self.feature_names),
        }
        with open(save_path, "wb") as f:
            pickle.dump(payload, f)

        logger.info(f"模型已保存: {save_path}")
        return save_path

    @classmethod
    def load(cls, league: str, model_type: str = "random_forest") -> "FootballPredictor | None":
        """从文件加载模型"""
        # 尝试最新版本号
        for v in range(5, 0, -1):
            path = MODELS_DIR / f"{league}_{model_type}_v{v}.pkl"
            if path.exists():
                try:
                    with open(path, "rb") as f:
                        payload = pickle.load(f)
                    inst = cls(model_type=payload["model_type"], league=payload.get("league"))
                    inst.model = payload["model"]
                    inst.scaler = payload["scaler"]
                    inst.feature_names = payload["feature_names"]
                    inst.label_map = payload["label_map"]
                    inst.inv_label_map = payload["inv_label_map"]
                    inst.is_fitted = payload["is_fitted"]
                    inst._version = payload.get("_version", 1)
                    inst._used_features = payload.get("_used_features", payload["feature_names"])
                    logger.info(f"模型已加载: {path}")
                    return inst
                except Exception as e:
                    logger.warning(f"加载模型失败 {path}: {e}")
        return None

    def get_feature_importance(self) -> list[dict]:
        """返回特征重要性排名"""
        if not self.is_fitted or self.feature_importances_ is None:
            return []
        used_feats = getattr(self, '_used_features', self.feature_names)
        fi_df = pd.DataFrame({
            "feature": used_feats,
            "importance": self.feature_importances_,
        }).sort_values("importance", ascending=False)
        return fi_df.to_dict("records")


class EnsemblePredictor:
    """集成预测器：组合多个模型的预测结果"""

    def __init__(self, predictors: list[FootballPredictor]):
        self.predictors = [p for p in predictors if p.is_fitted]
        if not self.predictors:
            raise ValueError("至少需要一个已训练的模型")
        self.model_types = [p.model_type for p in self.predictors]
        logger.info(f"集成预测器: {len(self.predictors)} 个模型 ({', '.join(self.model_types)})")

    def predict(self, features: dict | pd.DataFrame) -> MLPrediction:
        """
        集成预测：所有模型投票 + 概率平均

        Returns:
            平均概率后的 MLPrediction
        """
        predictions = []
        for p in self.predictors:
            pred = p.predict(features)
            predictions.append(pred)

        n = len(predictions)
        avg_h = sum(p.home_win_prob for p in predictions) / n
        avg_d = sum(p.draw_prob for p in predictions) / n
        avg_a = sum(p.away_win_prob for p in predictions) / n

        # 投票
        votes = {"H": 0, "D": 0, "A": 0}
        for pred in predictions:
            votes[pred.predicted] += 1
        majority = max(votes, key=votes.get)

        best_prob = max(avg_h, avg_d, avg_a)

        return MLPrediction(
            predicted=majority if votes[majority] > n // 2 else (
                "H" if avg_h == best_prob else ("D" if avg_d == best_prob else "A")
            ),
            home_win_prob=round(avg_h, 4),
            draw_prob=round(avg_d, 4),
            away_win_prob=round(avg_a, 4),
            confidence=round(best_prob, 4),
        )


def compare_models(
    df: pd.DataFrame,
    models: list[str] | None = None,
    league: str | None = None,
) -> dict[str, dict]:
    """
    对比多个模型的性能

    Args:
        df: 含特征的比赛数据
        models: 模型列表
        league: 联赛代码（可选）

    Returns:
        {模型名: 训练结果}
    """
    models = models or ["random_forest", "logistic_regression", "gradient_boosting", "xgboost", "lightgbm", "catboost"]
    results = {}

    for model_type in models:
        tag = f"[{league}]" if league else ""
        logger.info(f"\n=== {tag} 训练模型: {model_type} ===")
        predictor = FootballPredictor(model_type=model_type, league=league)
        result = predictor.train(df, use_tscv=True)
        results[model_type] = result

    return results


def train_per_league(
    df: pd.DataFrame,
    models: list[str] | None = None,
    save: bool = True,
) -> dict[str, dict[str, FootballPredictor]]:
    """
    按联赛分别训练所有模型

    Args:
        df: 含联赛列和特征列的数据
        models: 模型类型列表
        save: 是否保存到文件

    Returns:
        {联赛: {模型类型: FootballPredictor}}
    """
    from config import LEAGUES

    models = models or TRAIN_CONFIG["ensemble"]
    result = {}

    for league_key in LEAGUES:
        league_df = df[df["league"] == league_key].copy()
        if len(league_df) < 200:
            logger.warning(f"[{league_key}] 数据不足 ({len(league_df)} 条)，跳过")
            continue

        logger.info(f"\n{'='*50}")
        logger.info(f"训练 {league_key} ({LEAGUES[league_key]['name']})")
        logger.info(f"{'='*50}")

        league_models = {}
        for model_type in models:
            predictor = FootballPredictor(model_type=model_type, league=league_key)
            train_result = predictor.train(league_df, use_tscv=True)

            if "error" not in train_result:
                league_models[model_type] = predictor
                if save:
                    predictor.save()
            else:
                logger.warning(f"[{league_key}] {model_type} 训练失败")

        result[league_key] = league_models

    return result


def load_per_league_models(league: str | None = None) -> dict[str, FootballPredictor]:
    """加载已保存的 per-league 模型"""
    from config import LEAGUES
    models_config = TRAIN_CONFIG["ensemble"]

    all_models = {}
    leagues = [league] if league else list(LEAGUES.keys())

    for l in leagues:
        for model_type in models_config:
            predictor = FootballPredictor.load(l, model_type)
            if predictor:
                all_models[f"{l}_{model_type}"] = predictor

    return all_models
