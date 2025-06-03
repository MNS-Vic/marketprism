"""
预测模型管理 - Week 5 Day 9
提供机器学习模型管理、预测生成和模型评估功能
"""

import asyncio
import logging
import math
import statistics
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import Enum
from typing import Dict, List, Optional, Any, Tuple
from concurrent.futures import ThreadPoolExecutor
import json
import random

# 配置日志
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class ModelType(Enum):
    """模型类型"""
    LINEAR_REGRESSION = "linear_regression"
    LSTM = "lstm"
    RANDOM_FOREST = "random_forest"
    SVM = "svm"
    ENSEMBLE = "ensemble"
    TRANSFORMER = "transformer"
    XGB = "xgboost"
    ARIMA = "arima"


class PredictionType(Enum):
    """预测类型"""
    PRICE_PREDICTION = "price_prediction"
    TREND_DIRECTION = "trend_direction"
    VOLATILITY_FORECAST = "volatility_forecast"
    VOLUME_PREDICTION = "volume_prediction"
    SUPPORT_RESISTANCE = "support_resistance"
    RISK_FORECAST = "risk_forecast"


class ModelStatus(Enum):
    """模型状态"""
    TRAINING = "training"
    TRAINED = "trained"
    DEPLOYED = "deployed"
    RETRAINING = "retraining"
    DEPRECATED = "deprecated"
    ERROR = "error"


class TimeHorizon(Enum):
    """预测时间范围"""
    MINUTES_5 = "5min"
    MINUTES_15 = "15min"
    HOUR_1 = "1h"
    HOURS_4 = "4h"
    DAY_1 = "1d"
    WEEK_1 = "1w"
    MONTH_1 = "1m"


@dataclass
class ModelConfiguration:
    """模型配置"""
    model_id: str
    model_type: ModelType
    prediction_type: PredictionType
    time_horizon: TimeHorizon
    features: List[str]
    parameters: Dict[str, Any]
    training_data_size: int = 1000
    retrain_frequency: timedelta = timedelta(days=7)
    target_accuracy: float = 0.75


@dataclass
class Prediction:
    """预测结果"""
    prediction_id: str
    model_id: str
    symbol: str
    prediction_type: PredictionType
    timestamp: datetime
    predicted_value: float
    confidence: float
    time_horizon: TimeHorizon
    features_used: Dict[str, float]
    actual_value: Optional[float] = None
    error: Optional[float] = None
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "prediction_id": self.prediction_id,
            "model_id": self.model_id,
            "symbol": self.symbol,
            "prediction_type": self.prediction_type.value,
            "timestamp": self.timestamp.isoformat(),
            "predicted_value": self.predicted_value,
            "confidence": self.confidence,
            "time_horizon": self.time_horizon.value,
            "features_used": self.features_used,
            "actual_value": self.actual_value,
            "error": self.error
        }


@dataclass
class ModelPerformance:
    """模型性能"""
    model_id: str
    accuracy: float
    precision: float
    recall: float
    f1_score: float
    mae: float  # 平均绝对误差
    rmse: float  # 均方根误差
    last_updated: datetime
    total_predictions: int
    correct_predictions: int


@dataclass
class ModelMetadata:
    """模型元数据"""
    model_id: str
    configuration: ModelConfiguration
    status: ModelStatus
    created_at: datetime
    last_trained: Optional[datetime] = None
    next_retrain: Optional[datetime] = None
    performance: Optional[ModelPerformance] = None
    version: str = "1.0"


@dataclass
class FeatureImportance:
    """特征重要性"""
    feature_name: str
    importance_score: float
    model_id: str
    timestamp: datetime


@dataclass
class ModelEnsemble:
    """模型集成"""
    ensemble_id: str
    component_models: List[str]
    weights: List[float]
    combination_method: str  # "weighted_average", "voting", "stacking"
    performance: Optional[ModelPerformance] = None


class PredictiveModeling:
    """预测模型管理"""
    
    def __init__(self):
        self.models: Dict[str, ModelMetadata] = {}
        self.predictions: List[Prediction] = []
        self.model_ensembles: Dict[str, ModelEnsemble] = {}
        self.feature_importance: Dict[str, List[FeatureImportance]] = {}
        self.training_data: Dict[str, List[Dict[str, Any]]] = {}
        self.executor = ThreadPoolExecutor(max_workers=6)
        
        # 初始化默认模型
        self._initialize_default_models()
        logger.info("预测模型管理系统初始化完成")
    
    def _initialize_default_models(self):
        """初始化默认模型"""
        
        # 价格预测模型
        price_model_config = ModelConfiguration(
            model_id="btc_price_lstm",
            model_type=ModelType.LSTM,
            prediction_type=PredictionType.PRICE_PREDICTION,
            time_horizon=TimeHorizon.HOUR_1,
            features=["close_price", "volume", "rsi", "ma_20", "ma_50", "bollinger_upper", "bollinger_lower"],
            parameters={
                "hidden_layers": 2,
                "neurons_per_layer": 50,
                "dropout": 0.2,
                "learning_rate": 0.001,
                "epochs": 100
            },
            target_accuracy=0.75
        )
        
        # 趋势方向预测模型
        trend_model_config = ModelConfiguration(
            model_id="trend_direction_rf",
            model_type=ModelType.RANDOM_FOREST,
            prediction_type=PredictionType.TREND_DIRECTION,
            time_horizon=TimeHorizon.HOURS_4,
            features=["rsi", "macd", "sma_ratio", "volume_ratio", "price_change_1h", "volatility"],
            parameters={
                "n_estimators": 100,
                "max_depth": 10,
                "min_samples_split": 5,
                "random_state": 42
            },
            target_accuracy=0.70
        )
        
        # 波动率预测模型
        volatility_model_config = ModelConfiguration(
            model_id="volatility_forecast_xgb",
            model_type=ModelType.XGB,
            prediction_type=PredictionType.VOLATILITY_FORECAST,
            time_horizon=TimeHorizon.DAY_1,
            features=["historical_vol", "returns_squared", "volume", "price_range", "trading_activity"],
            parameters={
                "n_estimators": 200,
                "learning_rate": 0.1,
                "max_depth": 6,
                "subsample": 0.8
            },
            target_accuracy=0.65
        )
        
        # 支撑阻力位预测模型
        support_resistance_config = ModelConfiguration(
            model_id="support_resistance_ensemble",
            model_type=ModelType.ENSEMBLE,
            prediction_type=PredictionType.SUPPORT_RESISTANCE,
            time_horizon=TimeHorizon.DAY_1,
            features=["pivot_points", "fibonacci_levels", "volume_profile", "previous_highs", "previous_lows"],
            parameters={
                "base_models": ["linear_regression", "svm", "random_forest"],
                "combination_method": "weighted_average"
            },
            target_accuracy=0.60
        )
        
        configs = [price_model_config, trend_model_config, volatility_model_config, support_resistance_config]
        
        for config in configs:
            metadata = ModelMetadata(
                model_id=config.model_id,
                configuration=config,
                status=ModelStatus.TRAINED,
                created_at=datetime.now(),
                last_trained=datetime.now() - timedelta(days=1),
                next_retrain=datetime.now() + timedelta(days=6),
                version="1.0"
            )
            
            # 模拟模型性能
            performance = ModelPerformance(
                model_id=config.model_id,
                accuracy=random.uniform(0.65, 0.85),
                precision=random.uniform(0.60, 0.80),
                recall=random.uniform(0.65, 0.85),
                f1_score=random.uniform(0.60, 0.80),
                mae=random.uniform(0.05, 0.15),
                rmse=random.uniform(0.08, 0.20),
                last_updated=datetime.now(),
                total_predictions=random.randint(500, 2000),
                correct_predictions=random.randint(400, 1600)
            )
            
            metadata.performance = performance
            self.models[config.model_id] = metadata
    
    def create_model(self, config: ModelConfiguration) -> bool:
        """创建新模型"""
        try:
            if config.model_id in self.models:
                logger.warning(f"模型已存在: {config.model_id}")
                return False
            
            metadata = ModelMetadata(
                model_id=config.model_id,
                configuration=config,
                status=ModelStatus.TRAINING,
                created_at=datetime.now(),
                version="1.0"
            )
            
            self.models[config.model_id] = metadata
            
            # 异步训练模型
            self.executor.submit(self._train_model, config.model_id)
            
            logger.info(f"创建模型: {config.model_id}")
            return True
            
        except Exception as e:
            logger.error(f"创建模型失败: {e}")
            return False
    
    def _train_model(self, model_id: str):
        """训练模型 (模拟)"""
        try:
            if model_id not in self.models:
                return
            
            model = self.models[model_id]
            model.status = ModelStatus.TRAINING
            
            # 模拟训练过程
            import time
            time.sleep(2)  # 模拟训练时间
            
            # 生成模拟性能指标
            performance = ModelPerformance(
                model_id=model_id,
                accuracy=random.uniform(0.60, 0.85),
                precision=random.uniform(0.55, 0.80),
                recall=random.uniform(0.60, 0.85),
                f1_score=random.uniform(0.55, 0.80),
                mae=random.uniform(0.05, 0.20),
                rmse=random.uniform(0.08, 0.25),
                last_updated=datetime.now(),
                total_predictions=0,
                correct_predictions=0
            )
            
            model.performance = performance
            model.status = ModelStatus.TRAINED
            model.last_trained = datetime.now()
            model.next_retrain = datetime.now() + model.configuration.retrain_frequency
            
            # 生成特征重要性
            self._generate_feature_importance(model_id)
            
            logger.info(f"模型训练完成: {model_id} - 准确率: {performance.accuracy:.2%}")
            
        except Exception as e:
            logger.error(f"模型训练失败: {e}")
            if model_id in self.models:
                self.models[model_id].status = ModelStatus.ERROR
    
    def _generate_feature_importance(self, model_id: str):
        """生成特征重要性 (模拟)"""
        try:
            model = self.models[model_id]
            features = model.configuration.features
            
            # 生成随机重要性得分并归一化
            importance_scores = [random.uniform(0.1, 1.0) for _ in features]
            total_score = sum(importance_scores)
            normalized_scores = [score / total_score for score in importance_scores]
            
            feature_importances = []
            for feature, score in zip(features, normalized_scores):
                importance = FeatureImportance(
                    feature_name=feature,
                    importance_score=round(score, 3),
                    model_id=model_id,
                    timestamp=datetime.now()
                )
                feature_importances.append(importance)
            
            self.feature_importance[model_id] = feature_importances
            
        except Exception as e:
            logger.error(f"生成特征重要性失败: {e}")
    
    def make_prediction(self, model_id: str, symbol: str, features: Dict[str, float]) -> Optional[Prediction]:
        """生成预测"""
        try:
            if model_id not in self.models:
                logger.warning(f"模型不存在: {model_id}")
                return None
            
            model = self.models[model_id]
            if model.status != ModelStatus.TRAINED:
                logger.warning(f"模型未训练: {model_id}")
                return None
            
            # 检查特征是否完整
            required_features = set(model.configuration.features)
            provided_features = set(features.keys())
            
            if not required_features.issubset(provided_features):
                missing_features = required_features - provided_features
                logger.warning(f"缺少特征: {missing_features}")
                return None
            
            # 模拟预测过程
            predicted_value, confidence = self._simulate_prediction(model, features)
            
            prediction = Prediction(
                prediction_id=f"pred_{model_id}_{symbol}_{int(datetime.now().timestamp())}",
                model_id=model_id,
                symbol=symbol,
                prediction_type=model.configuration.prediction_type,
                timestamp=datetime.now(),
                predicted_value=predicted_value,
                confidence=confidence,
                time_horizon=model.configuration.time_horizon,
                features_used=features
            )
            
            self.predictions.append(prediction)
            
            # 保留最近5000个预测
            if len(self.predictions) > 5000:
                self.predictions = self.predictions[-5000:]
            
            logger.info(f"生成预测: {model_id} - {symbol} - 值: {predicted_value}, 置信度: {confidence:.2%}")
            return prediction
            
        except Exception as e:
            logger.error(f"生成预测失败: {e}")
            return None
    
    def _simulate_prediction(self, model: ModelMetadata, features: Dict[str, float]) -> Tuple[float, float]:
        """模拟预测过程"""
        
        # 根据模型类型和预测类型生成不同的预测值
        prediction_type = model.configuration.prediction_type
        
        if prediction_type == PredictionType.PRICE_PREDICTION:
            # 基于当前价格进行小幅调整
            current_price = features.get("close_price", 100.0)
            price_change = random.uniform(-0.05, 0.05)  # ±5%
            predicted_value = current_price * (1 + price_change)
            confidence = random.uniform(0.6, 0.9)
            
        elif prediction_type == PredictionType.TREND_DIRECTION:
            # 预测方向 (1: 上涨, 0: 下跌)
            rsi = features.get("rsi", 50)
            volume_ratio = features.get("volume_ratio", 1.0)
            
            # 简单规则：RSI > 50 且成交量放大倾向于上涨
            trend_signal = 1 if rsi > 50 and volume_ratio > 1.2 else 0
            predicted_value = trend_signal
            confidence = min(0.95, 0.5 + abs(rsi - 50) / 100 + (volume_ratio - 1) * 0.3)
            
        elif prediction_type == PredictionType.VOLATILITY_FORECAST:
            # 预测波动率
            historical_vol = features.get("historical_vol", 0.02)
            volume = features.get("volume", 1000000)
            
            # 基于历史波动率和成交量调整
            vol_adjustment = random.uniform(0.8, 1.5)
            volume_factor = min(2.0, volume / 1000000)  # 成交量因子
            predicted_value = historical_vol * vol_adjustment * (1 + volume_factor * 0.1)
            confidence = random.uniform(0.55, 0.85)
            
        elif prediction_type == PredictionType.SUPPORT_RESISTANCE:
            # 预测支撑/阻力位
            current_price = features.get("close_price", 100.0)
            price_range = current_price * 0.05  # 5%范围
            
            if random.random() > 0.5:
                # 预测阻力位
                predicted_value = current_price + random.uniform(0, price_range)
            else:
                # 预测支撑位
                predicted_value = current_price - random.uniform(0, price_range)
            
            confidence = random.uniform(0.5, 0.8)
            
        else:
            # 默认预测
            predicted_value = random.uniform(50, 150)
            confidence = random.uniform(0.5, 0.8)
        
        return round(predicted_value, 4), round(confidence, 3)
    
    def update_prediction_actual(self, prediction_id: str, actual_value: float) -> bool:
        """更新预测的实际值"""
        try:
            prediction = next((p for p in self.predictions if p.prediction_id == prediction_id), None)
            if not prediction:
                logger.warning(f"预测不存在: {prediction_id}")
                return False
            
            prediction.actual_value = actual_value
            prediction.error = abs(prediction.predicted_value - actual_value)
            
            # 更新模型性能
            self._update_model_performance(prediction.model_id, prediction)
            
            logger.info(f"更新预测实际值: {prediction_id} - 误差: {prediction.error}")
            return True
            
        except Exception as e:
            logger.error(f"更新预测实际值失败: {e}")
            return False
    
    def _update_model_performance(self, model_id: str, prediction: Prediction):
        """更新模型性能"""
        try:
            if model_id not in self.models or not self.models[model_id].performance:
                return
            
            performance = self.models[model_id].performance
            performance.total_predictions += 1
            
            # 计算是否预测正确 (基于预测类型)
            if prediction.prediction_type == PredictionType.TREND_DIRECTION:
                # 方向预测：检查方向是否正确
                predicted_direction = prediction.predicted_value > 0.5
                actual_direction = prediction.actual_value > 0.5
                if predicted_direction == actual_direction:
                    performance.correct_predictions += 1
            else:
                # 数值预测：误差在10%以内算正确
                relative_error = abs(prediction.error) / max(abs(prediction.actual_value), 0.01)
                if relative_error <= 0.1:
                    performance.correct_predictions += 1
            
            # 更新准确率
            performance.accuracy = performance.correct_predictions / performance.total_predictions
            
            # 重新计算MAE和RMSE
            recent_predictions = [p for p in self.predictions if p.model_id == model_id and p.actual_value is not None]
            if recent_predictions:
                errors = [p.error for p in recent_predictions]
                performance.mae = statistics.mean(errors)
                performance.rmse = math.sqrt(statistics.mean([e**2 for e in errors]))
            
            performance.last_updated = datetime.now()
            
        except Exception as e:
            logger.error(f"更新模型性能失败: {e}")
    
    def create_ensemble(self, ensemble_id: str, model_ids: List[str], weights: List[float] = None, 
                       combination_method: str = "weighted_average") -> bool:
        """创建模型集成"""
        try:
            # 验证模型存在
            missing_models = [mid for mid in model_ids if mid not in self.models]
            if missing_models:
                logger.warning(f"模型不存在: {missing_models}")
                return False
            
            # 默认权重
            if weights is None:
                weights = [1.0 / len(model_ids)] * len(model_ids)
            
            if len(weights) != len(model_ids):
                logger.warning("权重数量与模型数量不匹配")
                return False
            
            # 归一化权重
            total_weight = sum(weights)
            normalized_weights = [w / total_weight for w in weights]
            
            ensemble = ModelEnsemble(
                ensemble_id=ensemble_id,
                component_models=model_ids,
                weights=normalized_weights,
                combination_method=combination_method
            )
            
            self.model_ensembles[ensemble_id] = ensemble
            
            logger.info(f"创建模型集成: {ensemble_id} - 包含 {len(model_ids)} 个模型")
            return True
            
        except Exception as e:
            logger.error(f"创建模型集成失败: {e}")
            return False
    
    def make_ensemble_prediction(self, ensemble_id: str, symbol: str, features: Dict[str, float]) -> Optional[Prediction]:
        """使用集成模型进行预测"""
        try:
            if ensemble_id not in self.model_ensembles:
                logger.warning(f"集成模型不存在: {ensemble_id}")
                return None
            
            ensemble = self.model_ensembles[ensemble_id]
            individual_predictions = []
            
            # 获取各个模型的预测
            for model_id in ensemble.component_models:
                prediction = self.make_prediction(model_id, symbol, features)
                if prediction:
                    individual_predictions.append(prediction)
            
            if not individual_predictions:
                logger.warning("集成模型中没有可用的预测")
                return None
            
            # 组合预测结果
            if ensemble.combination_method == "weighted_average":
                weighted_values = []
                weighted_confidences = []
                
                for i, pred in enumerate(individual_predictions):
                    if i < len(ensemble.weights):
                        weight = ensemble.weights[i]
                        weighted_values.append(pred.predicted_value * weight)
                        weighted_confidences.append(pred.confidence * weight)
                
                combined_value = sum(weighted_values)
                combined_confidence = sum(weighted_confidences)
                
            elif ensemble.combination_method == "voting":
                # 适用于分类问题
                votes = [p.predicted_value for p in individual_predictions]
                combined_value = max(set(votes), key=votes.count)  # 众数
                combined_confidence = statistics.mean([p.confidence for p in individual_predictions])
                
            else:
                # 简单平均
                combined_value = statistics.mean([p.predicted_value for p in individual_predictions])
                combined_confidence = statistics.mean([p.confidence for p in individual_predictions])
            
            # 创建集成预测
            ensemble_prediction = Prediction(
                prediction_id=f"ensemble_{ensemble_id}_{symbol}_{int(datetime.now().timestamp())}",
                model_id=ensemble_id,
                symbol=symbol,
                prediction_type=individual_predictions[0].prediction_type,  # 假设所有模型预测同一类型
                timestamp=datetime.now(),
                predicted_value=round(combined_value, 4),
                confidence=round(combined_confidence, 3),
                time_horizon=individual_predictions[0].time_horizon,
                features_used=features
            )
            
            self.predictions.append(ensemble_prediction)
            
            logger.info(f"集成预测完成: {ensemble_id} - {symbol} - 值: {combined_value}")
            return ensemble_prediction
            
        except Exception as e:
            logger.error(f"集成预测失败: {e}")
            return None
    
    def get_model_performance_report(self, model_id: str) -> Optional[Dict[str, Any]]:
        """获取模型性能报告"""
        try:
            if model_id not in self.models:
                logger.warning(f"模型不存在: {model_id}")
                return None
            
            model = self.models[model_id]
            model_predictions = [p for p in self.predictions if p.model_id == model_id]
            
            # 统计预测分布
            prediction_types = {}
            for pred in model_predictions:
                pred_type = pred.prediction_type.value
                if pred_type not in prediction_types:
                    prediction_types[pred_type] = 0
                prediction_types[pred_type] += 1
            
            # 计算平均置信度
            avg_confidence = statistics.mean([p.confidence for p in model_predictions]) if model_predictions else 0
            
            # 最近预测的准确率
            recent_predictions = [p for p in model_predictions if p.actual_value is not None][-100:]  # 最近100个
            recent_accuracy = len([p for p in recent_predictions if abs(p.error / max(abs(p.actual_value), 0.01)) <= 0.1]) / len(recent_predictions) if recent_predictions else 0
            
            report = {
                "model_id": model_id,
                "model_type": model.configuration.model_type.value,
                "status": model.status.value,
                "created_at": model.created_at.isoformat(),
                "last_trained": model.last_trained.isoformat() if model.last_trained else None,
                "performance": {
                    "accuracy": model.performance.accuracy if model.performance else 0,
                    "mae": model.performance.mae if model.performance else 0,
                    "rmse": model.performance.rmse if model.performance else 0,
                    "total_predictions": model.performance.total_predictions if model.performance else 0
                },
                "prediction_statistics": {
                    "total_predictions": len(model_predictions),
                    "average_confidence": round(avg_confidence, 3),
                    "recent_accuracy": round(recent_accuracy, 3),
                    "prediction_type_distribution": prediction_types
                },
                "feature_importance": [
                    {"feature": fi.feature_name, "importance": fi.importance_score}
                    for fi in self.feature_importance.get(model_id, [])
                ]
            }
            
            return report
            
        except Exception as e:
            logger.error(f"获取模型性能报告失败: {e}")
            return None
    
    def get_modeling_stats(self) -> Dict[str, Any]:
        """获取建模统计信息"""
        try:
            # 模型状态分布
            status_distribution = {}
            for status in ModelStatus:
                status_distribution[status.value] = len([m for m in self.models.values() if m.status == status])
            
            # 预测类型分布
            prediction_type_distribution = {}
            for pred_type in PredictionType:
                prediction_type_distribution[pred_type.value] = len([p for p in self.predictions if p.prediction_type == pred_type])
            
            # 平均性能指标
            performances = [m.performance for m in self.models.values() if m.performance]
            avg_accuracy = statistics.mean([p.accuracy for p in performances]) if performances else 0
            avg_mae = statistics.mean([p.mae for p in performances]) if performances else 0
            
            stats = {
                "total_models": len(self.models),
                "active_models": len([m for m in self.models.values() if m.status == ModelStatus.TRAINED]),
                "model_ensembles": len(self.model_ensembles),
                "total_predictions": len(self.predictions),
                "predictions_with_actuals": len([p for p in self.predictions if p.actual_value is not None]),
                "model_status_distribution": status_distribution,
                "prediction_type_distribution": prediction_type_distribution,
                "average_model_accuracy": round(avg_accuracy, 3),
                "average_mae": round(avg_mae, 4),
                "model_types": {
                    model_type.value: len([m for m in self.models.values() if m.configuration.model_type == model_type])
                    for model_type in ModelType
                },
                "recent_prediction_count": len([p for p in self.predictions if (datetime.now() - p.timestamp).days < 1])
            }
            
            return stats
            
        except Exception as e:
            logger.error(f"获取建模统计失败: {e}")
            return {}


# 生成模拟预测的辅助函数
def generate_sample_predictions(modeling: PredictiveModeling, count: int = 40):
    """生成示例预测"""
    symbols = ["BTC/USDT", "ETH/USDT", "BNB/USDT", "SOL/USDT", "XRP/USDT"]
    model_ids = list(modeling.models.keys())
    
    for i in range(count):
        symbol = random.choice(symbols)
        model_id = random.choice(model_ids)
        
        # 生成模拟特征数据
        model = modeling.models[model_id]
        features = {}
        
        for feature in model.configuration.features:
            if feature == "close_price":
                features[feature] = random.uniform(100, 50000)
            elif feature == "volume":
                features[feature] = random.uniform(500000, 5000000)
            elif feature == "rsi":
                features[feature] = random.uniform(20, 80)
            elif "ma_" in feature:
                features[feature] = random.uniform(100, 50000)
            elif "bollinger" in feature:
                features[feature] = random.uniform(100, 52000)
            elif "volatility" in feature:
                features[feature] = random.uniform(0.01, 0.1)
            elif "ratio" in feature:
                features[feature] = random.uniform(0.5, 2.0)
            else:
                features[feature] = random.uniform(0, 1)
        
        # 生成预测
        prediction = modeling.make_prediction(model_id, symbol, features)
        
        # 模拟一些预测有实际值更新
        if prediction and random.random() < 0.4:  # 40%的预测会有实际值
            if prediction.prediction_type == PredictionType.PRICE_PREDICTION:
                actual_value = prediction.predicted_value * random.uniform(0.95, 1.05)
            elif prediction.prediction_type == PredictionType.TREND_DIRECTION:
                actual_value = random.choice([0, 1])
            elif prediction.prediction_type == PredictionType.VOLATILITY_FORECAST:
                actual_value = prediction.predicted_value * random.uniform(0.8, 1.2)
            else:
                actual_value = prediction.predicted_value * random.uniform(0.9, 1.1)
            
            modeling.update_prediction_actual(prediction.prediction_id, actual_value)
    
    # 创建一些集成模型
    if len(model_ids) >= 2:
        ensemble_models = random.sample(model_ids, 2)
        modeling.create_ensemble("price_ensemble", ensemble_models, [0.6, 0.4])
        
        # 为集成模型生成一些预测
        for _ in range(5):
            symbol = random.choice(symbols)
            features = {
                "close_price": random.uniform(100, 50000),
                "volume": random.uniform(500000, 5000000),
                "rsi": random.uniform(20, 80),
                "ma_20": random.uniform(100, 50000),
                "ma_50": random.uniform(100, 50000)
            }
            modeling.make_ensemble_prediction("price_ensemble", symbol, features)