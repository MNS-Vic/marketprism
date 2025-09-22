"""
日志抽样器 - 高频数据日志抽样策略
避免高频数据日志刷屏，同时保持可观测性
"""

import time
from typing import Dict, Tuple
from dataclasses import dataclass
from threading import Lock


@dataclass
class SamplingConfig:
    """抽样配置"""
    count_interval: int = 100  # 每N条记录1条
    time_interval: float = 1.0  # 每秒最多记录K条
    always_log_errors: bool = True  # 错误总是记录
    always_log_first: bool = True  # 首次总是记录


class LogSampler:
    """
    日志抽样器
    
    支持两种抽样策略的组合：
    1. 计数抽样：每N条记录1条
    2. 时间窗限频：每秒最多K条
    
    关键事件（错误、首次连接等）总是记录
    """
    
    def __init__(self, default_config: SamplingConfig = None):
        self.default_config = default_config or SamplingConfig()
        self.configs: Dict[str, SamplingConfig] = {}
        
        # 状态跟踪：{key: (count, last_log_time, first_logged)}
        self.states: Dict[str, Tuple[int, float, bool]] = {}
        self.lock = Lock()
    
    def set_config(self, key: str, config: SamplingConfig):
        """为特定key设置抽样配置"""
        with self.lock:
            self.configs[key] = config
    
    def get_config(self, key: str) -> SamplingConfig:
        """获取key的抽样配置"""
        return self.configs.get(key, self.default_config)
    
    def should_log(self, key: str, is_error: bool = False) -> bool:
        """
        判断是否应该记录日志
        
        Args:
            key: 抽样键（如 "trade.binance_spot.spot.BTCUSDT"）
            is_error: 是否为错误日志
            
        Returns:
            bool: 是否应该记录
        """
        if is_error:
            return True  # 错误总是记录
        
        config = self.get_config(key)
        current_time = time.time()
        
        with self.lock:
            if key not in self.states:
                self.states[key] = (0, 0.0, False)
            
            count, last_log_time, first_logged = self.states[key]
            
            # 首次总是记录
            if config.always_log_first and not first_logged:
                self.states[key] = (1, current_time, True)
                return True
            
            # 更新计数
            count += 1
            
            # 检查计数抽样
            count_should_log = (count % config.count_interval == 0)
            
            # 检查时间窗限频
            time_should_log = (current_time - last_log_time) >= config.time_interval
            
            # 两个条件都满足才记录（取交集）
            should_log = count_should_log and time_should_log
            
            if should_log:
                self.states[key] = (count, current_time, first_logged)
            else:
                self.states[key] = (count, last_log_time, first_logged)
            
            return should_log
    
    def get_stats(self) -> Dict[str, Dict]:
        """获取抽样统计信息"""
        with self.lock:
            stats = {}
            for key, (count, last_log_time, first_logged) in self.states.items():
                config = self.get_config(key)
                stats[key] = {
                    'total_count': count,
                    'last_log_time': last_log_time,
                    'first_logged': first_logged,
                    'config': {
                        'count_interval': config.count_interval,
                        'time_interval': config.time_interval
                    }
                }
            return stats
    
    def reset_stats(self):
        """重置统计信息"""
        with self.lock:
            self.states.clear()


# 全局抽样器实例
_global_sampler = None
_sampler_lock = Lock()


def get_log_sampler() -> LogSampler:
    """获取全局日志抽样器实例"""
    global _global_sampler
    if _global_sampler is None:
        with _sampler_lock:
            if _global_sampler is None:
                # 默认配置
                default_config = SamplingConfig(
                    count_interval=100,  # 每100条记录1条
                    time_interval=1.0,   # 每秒最多1条
                    always_log_errors=True,
                    always_log_first=True
                )
                _global_sampler = LogSampler(default_config)
    return _global_sampler


def configure_sampling(data_type: str, exchange: str, market_type: str, 
                      count_interval: int = 100, time_interval: float = 1.0):
    """
    配置特定数据类型的抽样参数
    
    Args:
        data_type: 数据类型 (trade, orderbook等)
        exchange: 交易所
        market_type: 市场类型
        count_interval: 计数间隔
        time_interval: 时间间隔
    """
    sampler = get_log_sampler()
    key = f"{data_type}.{exchange}.{market_type}"
    config = SamplingConfig(
        count_interval=count_interval,
        time_interval=time_interval,
        always_log_errors=True,
        always_log_first=True
    )
    sampler.set_config(key, config)


def should_log_data_processing(data_type: str, exchange: str, market_type: str, 
                              symbol: str = None, is_error: bool = False) -> bool:
    """
    判断数据处理日志是否应该记录
    
    Args:
        data_type: 数据类型
        exchange: 交易所
        market_type: 市场类型  
        symbol: 交易对（可选，用于更细粒度控制）
        is_error: 是否为错误
        
    Returns:
        bool: 是否应该记录
    """
    sampler = get_log_sampler()
    
    # 构建抽样键
    if symbol:
        key = f"{data_type}.{exchange}.{market_type}.{symbol}"
    else:
        key = f"{data_type}.{exchange}.{market_type}"
    
    return sampler.should_log(key, is_error)
