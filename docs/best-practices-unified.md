# 🏆 MarketPrism 统一数据处理最佳实践

## 🎯 **概述**

本文档提供了MarketPrism统一交易数据标准化器的最佳实践指南，包括性能优化、错误处理、数据质量保证、监控告警等方面的实践经验。

## 🔧 **数据标准化最佳实践**

### **1. 标准化器使用原则**

```python
# ✅ 推荐：使用单例模式
class NormalizerManager:
    _instance = None
    _normalizer = None
    
    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._normalizer = DataNormalizer()
        return cls._instance
    
    def get_normalizer(self):
        return self._normalizer

# 使用方式
normalizer_manager = NormalizerManager()
normalizer = normalizer_manager.get_normalizer()

# ❌ 避免：频繁创建标准化器实例
# for data in data_list:
#     normalizer = DataNormalizer()  # 性能浪费
#     result = normalizer.normalize_binance_spot_trade(data)
```

### **2. 数据验证策略**

```python
def validate_input_data(data, data_type):
    """输入数据验证"""
    validation_rules = {
        "binance_spot": {
            "required_fields": ["e", "s", "t", "p", "q", "T", "m"],
            "field_types": {
                "p": (str, float),
                "q": (str, float),
                "T": int,
                "m": bool
            }
        },
        "okx": {
            "required_fields": ["data"],
            "nested_required": ["instId", "tradeId", "px", "sz", "side", "ts"]
        }
    }
    
    rules = validation_rules.get(data_type)
    if not rules:
        return False, f"未知数据类型: {data_type}"
    
    # 检查必需字段
    for field in rules["required_fields"]:
        if field not in data:
            return False, f"缺少必需字段: {field}"
    
    # 检查字段类型
    if "field_types" in rules:
        for field, expected_types in rules["field_types"].items():
            if field in data and not isinstance(data[field], expected_types):
                return False, f"字段类型错误: {field}"
    
    return True, "验证通过"

# 使用示例
def safe_normalize(normalizer, data, data_type):
    is_valid, message = validate_input_data(data, data_type)
    if not is_valid:
        print(f"数据验证失败: {message}")
        return None
    
    # 执行标准化
    if data_type == "binance_spot":
        return normalizer.normalize_binance_spot_trade(data)
    elif data_type == "okx":
        return normalizer.normalize_okx_trade(data)
```

### **3. 错误处理策略**

```python
import logging
from enum import Enum

class NormalizationError(Exception):
    """标准化错误基类"""
    pass

class DataValidationError(NormalizationError):
    """数据验证错误"""
    pass

class NormalizationResult(Enum):
    SUCCESS = "success"
    VALIDATION_ERROR = "validation_error"
    PROCESSING_ERROR = "processing_error"
    UNKNOWN_ERROR = "unknown_error"

def robust_normalize(normalizer, data, data_type, logger=None):
    """健壮的数据标准化处理"""
    if logger is None:
        logger = logging.getLogger(__name__)
    
    try:
        # 数据验证
        is_valid, validation_message = validate_input_data(data, data_type)
        if not is_valid:
            logger.warning(f"数据验证失败: {validation_message}")
            return None, NormalizationResult.VALIDATION_ERROR, validation_message
        
        # 执行标准化
        if data_type == "binance_spot":
            result = normalizer.normalize_binance_spot_trade(data)
        elif data_type == "binance_futures":
            result = normalizer.normalize_binance_futures_trade(data)
        elif data_type == "okx":
            result = normalizer.normalize_okx_trade(data)
        else:
            raise ValueError(f"不支持的数据类型: {data_type}")
        
        if result is None:
            logger.error(f"标准化返回None: {data}")
            return None, NormalizationResult.PROCESSING_ERROR, "标准化失败"
        
        logger.debug(f"标准化成功: {result.trade_id}")
        return result, NormalizationResult.SUCCESS, "成功"
        
    except DataValidationError as e:
        logger.error(f"数据验证异常: {e}")
        return None, NormalizationResult.VALIDATION_ERROR, str(e)
    except Exception as e:
        logger.error(f"标准化异常: {e}", exc_info=True)
        return None, NormalizationResult.UNKNOWN_ERROR, str(e)
```

## 📊 **性能优化最佳实践**

### **1. 批量处理优化**

```python
import asyncio
from concurrent.futures import ThreadPoolExecutor
from typing import List, Tuple

class BatchNormalizer:
    """批量标准化处理器"""
    
    def __init__(self, normalizer, max_workers=4):
        self.normalizer = normalizer
        self.max_workers = max_workers
        self.executor = ThreadPoolExecutor(max_workers=max_workers)
    
    def process_batch_sync(self, data_batch: List[Tuple[dict, str]], batch_size=1000):
        """同步批量处理"""
        results = []
        errors = []
        
        for i in range(0, len(data_batch), batch_size):
            batch = data_batch[i:i + batch_size]
            
            for data, data_type in batch:
                result, status, message = robust_normalize(self.normalizer, data, data_type)
                
                if status == NormalizationResult.SUCCESS:
                    results.append(result)
                else:
                    errors.append({
                        "data": data,
                        "data_type": data_type,
                        "error": message,
                        "status": status
                    })
        
        return results, errors
    
    async def process_batch_async(self, data_batch: List[Tuple[dict, str]]):
        """异步批量处理"""
        loop = asyncio.get_event_loop()
        
        tasks = []
        for data, data_type in data_batch:
            task = loop.run_in_executor(
                self.executor,
                robust_normalize,
                self.normalizer,
                data,
                data_type
            )
            tasks.append(task)
        
        results = await asyncio.gather(*tasks, return_exceptions=True)
        
        successful_results = []
        errors = []
        
        for i, result in enumerate(results):
            if isinstance(result, Exception):
                errors.append({
                    "index": i,
                    "error": str(result),
                    "data": data_batch[i][0]
                })
            elif result[1] == NormalizationResult.SUCCESS:
                successful_results.append(result[0])
            else:
                errors.append({
                    "index": i,
                    "error": result[2],
                    "status": result[1],
                    "data": data_batch[i][0]
                })
        
        return successful_results, errors

# 使用示例
batch_normalizer = BatchNormalizer(normalizer)

# 同步处理
results, errors = batch_normalizer.process_batch_sync(data_batch)

# 异步处理
# results, errors = await batch_normalizer.process_batch_async(data_batch)
```

### **2. 内存管理优化**

```python
import gc
from memory_profiler import profile

class MemoryEfficientProcessor:
    """内存高效的数据处理器"""
    
    def __init__(self, normalizer, memory_limit_mb=500):
        self.normalizer = normalizer
        self.memory_limit_bytes = memory_limit_mb * 1024 * 1024
        self.processed_count = 0
        self.gc_interval = 1000  # 每处理1000条数据执行一次垃圾回收
    
    def process_stream(self, data_stream):
        """流式处理数据"""
        for data_item in data_stream:
            try:
                # 处理单条数据
                result = self._process_single_item(data_item)
                
                if result:
                    yield result
                
                self.processed_count += 1
                
                # 定期垃圾回收
                if self.processed_count % self.gc_interval == 0:
                    gc.collect()
                    
            except Exception as e:
                print(f"处理数据项失败: {e}")
                continue
    
    def _process_single_item(self, data_item):
        """处理单条数据项"""
        data, data_type = data_item
        
        result, status, message = robust_normalize(self.normalizer, data, data_type)
        
        # 立即清理原始数据引用
        del data
        
        return result if status == NormalizationResult.SUCCESS else None

# 使用示例
processor = MemoryEfficientProcessor(normalizer)

# 流式处理大量数据
for normalized_trade in processor.process_stream(large_data_stream):
    # 立即处理结果，不存储在内存中
    process_trade_immediately(normalized_trade)
```

## 🔍 **数据质量保证**

### **1. 数据质量监控**

```python
from dataclasses import dataclass
from typing import Dict, List
import time

@dataclass
class QualityMetrics:
    """数据质量指标"""
    total_processed: int = 0
    successful_normalizations: int = 0
    validation_errors: int = 0
    processing_errors: int = 0
    unknown_errors: int = 0
    avg_processing_time: float = 0.0
    
    @property
    def success_rate(self) -> float:
        return self.successful_normalizations / self.total_processed if self.total_processed > 0 else 0
    
    @property
    def error_rate(self) -> float:
        return 1 - self.success_rate

class QualityMonitor:
    """数据质量监控器"""
    
    def __init__(self):
        self.metrics = QualityMetrics()
        self.processing_times = []
        self.error_samples = []
        self.max_error_samples = 100
    
    def record_processing(self, result, status, processing_time, data_sample=None):
        """记录处理结果"""
        self.metrics.total_processed += 1
        self.processing_times.append(processing_time)
        
        if status == NormalizationResult.SUCCESS:
            self.metrics.successful_normalizations += 1
        elif status == NormalizationResult.VALIDATION_ERROR:
            self.metrics.validation_errors += 1
            self._record_error_sample(data_sample, "validation_error")
        elif status == NormalizationResult.PROCESSING_ERROR:
            self.metrics.processing_errors += 1
            self._record_error_sample(data_sample, "processing_error")
        else:
            self.metrics.unknown_errors += 1
            self._record_error_sample(data_sample, "unknown_error")
        
        # 更新平均处理时间
        self.metrics.avg_processing_time = sum(self.processing_times) / len(self.processing_times)
    
    def _record_error_sample(self, data_sample, error_type):
        """记录错误样本"""
        if len(self.error_samples) >= self.max_error_samples:
            self.error_samples.pop(0)  # 移除最旧的样本
        
        self.error_samples.append({
            "timestamp": time.time(),
            "error_type": error_type,
            "data_sample": data_sample
        })
    
    def get_quality_report(self) -> Dict:
        """获取质量报告"""
        return {
            "metrics": {
                "total_processed": self.metrics.total_processed,
                "success_rate": f"{self.metrics.success_rate:.2%}",
                "error_rate": f"{self.metrics.error_rate:.2%}",
                "avg_processing_time_ms": f"{self.metrics.avg_processing_time * 1000:.2f}",
            },
            "error_breakdown": {
                "validation_errors": self.metrics.validation_errors,
                "processing_errors": self.metrics.processing_errors,
                "unknown_errors": self.metrics.unknown_errors,
            },
            "recent_errors": self.error_samples[-10:],  # 最近10个错误
            "performance": {
                "min_processing_time_ms": f"{min(self.processing_times) * 1000:.2f}" if self.processing_times else "N/A",
                "max_processing_time_ms": f"{max(self.processing_times) * 1000:.2f}" if self.processing_times else "N/A",
                "p95_processing_time_ms": f"{sorted(self.processing_times)[int(len(self.processing_times) * 0.95)] * 1000:.2f}" if len(self.processing_times) > 20 else "N/A"
            }
        }

# 使用示例
quality_monitor = QualityMonitor()

def monitored_normalize(normalizer, data, data_type):
    """带监控的标准化处理"""
    start_time = time.time()
    
    result, status, message = robust_normalize(normalizer, data, data_type)
    
    processing_time = time.time() - start_time
    quality_monitor.record_processing(result, status, processing_time, data)
    
    return result, status, message

# 定期获取质量报告
def print_quality_report():
    report = quality_monitor.get_quality_report()
    print("数据质量报告:")
    print(f"  成功率: {report['metrics']['success_rate']}")
    print(f"  平均处理时间: {report['metrics']['avg_processing_time_ms']}ms")
    print(f"  验证错误: {report['error_breakdown']['validation_errors']}")
```

## 🚨 **监控和告警**

### **1. 实时监控指标**

```python
import time
from collections import deque, defaultdict

class RealTimeMonitor:
    """实时监控器"""
    
    def __init__(self, window_size=300):  # 5分钟窗口
        self.window_size = window_size
        self.metrics_window = deque(maxlen=window_size)
        self.exchange_metrics = defaultdict(lambda: deque(maxlen=window_size))
        self.alert_thresholds = {
            "error_rate": 0.05,  # 5%错误率阈值
            "processing_time": 0.1,  # 100ms处理时间阈值
            "throughput": 100,  # 每秒100条数据阈值
        }
    
    def record_metric(self, exchange, success, processing_time):
        """记录指标"""
        timestamp = time.time()
        metric = {
            "timestamp": timestamp,
            "exchange": exchange,
            "success": success,
            "processing_time": processing_time
        }
        
        self.metrics_window.append(metric)
        self.exchange_metrics[exchange].append(metric)
        
        # 检查告警条件
        self._check_alerts()
    
    def _check_alerts(self):
        """检查告警条件"""
        current_time = time.time()
        
        # 检查整体错误率
        recent_metrics = [m for m in self.metrics_window if current_time - m["timestamp"] < 60]  # 最近1分钟
        if recent_metrics:
            error_rate = 1 - (sum(1 for m in recent_metrics if m["success"]) / len(recent_metrics))
            if error_rate > self.alert_thresholds["error_rate"]:
                self._trigger_alert("HIGH_ERROR_RATE", f"错误率: {error_rate:.2%}")
        
        # 检查处理时间
        if recent_metrics:
            avg_processing_time = sum(m["processing_time"] for m in recent_metrics) / len(recent_metrics)
            if avg_processing_time > self.alert_thresholds["processing_time"]:
                self._trigger_alert("HIGH_PROCESSING_TIME", f"平均处理时间: {avg_processing_time:.3f}s")
        
        # 检查吞吐量
        if len(recent_metrics) < self.alert_thresholds["throughput"] / 60:  # 每分钟期望的最小数据量
            self._trigger_alert("LOW_THROUGHPUT", f"吞吐量过低: {len(recent_metrics)}/min")
    
    def _trigger_alert(self, alert_type, message):
        """触发告警"""
        print(f"🚨 告警 [{alert_type}]: {message}")
        # 这里可以集成实际的告警系统，如发送邮件、Slack通知等
    
    def get_dashboard_data(self):
        """获取仪表板数据"""
        current_time = time.time()
        recent_metrics = [m for m in self.metrics_window if current_time - m["timestamp"] < 300]  # 最近5分钟
        
        if not recent_metrics:
            return {"status": "no_data"}
        
        # 按交易所统计
        exchange_stats = {}
        for exchange in self.exchange_metrics:
            exchange_recent = [m for m in self.exchange_metrics[exchange] if current_time - m["timestamp"] < 300]
            if exchange_recent:
                success_count = sum(1 for m in exchange_recent if m["success"])
                exchange_stats[exchange] = {
                    "total": len(exchange_recent),
                    "success": success_count,
                    "success_rate": success_count / len(exchange_recent),
                    "avg_processing_time": sum(m["processing_time"] for m in exchange_recent) / len(exchange_recent)
                }
        
        return {
            "status": "active",
            "overall": {
                "total_processed": len(recent_metrics),
                "success_rate": sum(1 for m in recent_metrics if m["success"]) / len(recent_metrics),
                "avg_processing_time": sum(m["processing_time"] for m in recent_metrics) / len(recent_metrics),
                "throughput_per_minute": len(recent_metrics)
            },
            "by_exchange": exchange_stats,
            "timestamp": current_time
        }

# 使用示例
monitor = RealTimeMonitor()

def monitored_process(normalizer, data, data_type, exchange):
    """带实时监控的处理"""
    start_time = time.time()
    
    result, status, message = robust_normalize(normalizer, data, data_type)
    
    processing_time = time.time() - start_time
    success = (status == NormalizationResult.SUCCESS)
    
    monitor.record_metric(exchange, success, processing_time)
    
    return result, status, message

# 定期获取仪表板数据
dashboard_data = monitor.get_dashboard_data()
print(f"实时监控数据: {dashboard_data}")
```

## 📝 **配置管理最佳实践**

### **1. 环境配置管理**

```python
import os
from dataclasses import dataclass
from typing import Optional

@dataclass
class NormalizationConfig:
    """标准化配置"""
    # 性能配置
    batch_size: int = 1000
    max_workers: int = 4
    memory_limit_mb: int = 500
    gc_interval: int = 1000
    
    # 质量配置
    max_error_samples: int = 100
    error_rate_threshold: float = 0.05
    processing_time_threshold: float = 0.1
    
    # 监控配置
    monitoring_window_size: int = 300
    alert_cooldown_seconds: int = 60
    
    # 日志配置
    log_level: str = "INFO"
    log_format: str = "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
    
    @classmethod
    def from_env(cls):
        """从环境变量加载配置"""
        return cls(
            batch_size=int(os.getenv("NORM_BATCH_SIZE", 1000)),
            max_workers=int(os.getenv("NORM_MAX_WORKERS", 4)),
            memory_limit_mb=int(os.getenv("NORM_MEMORY_LIMIT_MB", 500)),
            gc_interval=int(os.getenv("NORM_GC_INTERVAL", 1000)),
            max_error_samples=int(os.getenv("NORM_MAX_ERROR_SAMPLES", 100)),
            error_rate_threshold=float(os.getenv("NORM_ERROR_RATE_THRESHOLD", 0.05)),
            processing_time_threshold=float(os.getenv("NORM_PROCESSING_TIME_THRESHOLD", 0.1)),
            monitoring_window_size=int(os.getenv("NORM_MONITORING_WINDOW_SIZE", 300)),
            alert_cooldown_seconds=int(os.getenv("NORM_ALERT_COOLDOWN_SECONDS", 60)),
            log_level=os.getenv("NORM_LOG_LEVEL", "INFO"),
            log_format=os.getenv("NORM_LOG_FORMAT", "%(asctime)s - %(name)s - %(levelname)s - %(message)s")
        )

# 使用示例
config = NormalizationConfig.from_env()
batch_normalizer = BatchNormalizer(normalizer, max_workers=config.max_workers)
```

---

**文档版本**: v1.0  
**最后更新**: 2024-12-19  
**维护者**: MarketPrism开发团队
