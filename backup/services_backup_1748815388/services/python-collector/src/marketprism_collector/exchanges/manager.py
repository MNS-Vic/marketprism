"""
Exchange Manager - 企业级交易所适配器统一管理器

基于TDD发现的设计问题，提供统一的多交易所管理机制
支持：生命周期管理、健康监控、数据聚合、错误处理
"""

from typing import Dict, List, Optional, Any, Callable, Union
import asyncio
import logging
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from datetime import datetime
import threading

from .base import ExchangeAdapter
from .factory import ExchangeFactory, get_factory
from ..types import NormalizedTrade, NormalizedOrderBook, NormalizedTicker


@dataclass
class ExchangeHealth:
    """交易所健康状况"""
    exchange_name: str
    is_healthy: bool
    last_check: datetime
    error_count: int = 0
    last_error: Optional[str] = None
    uptime_percent: float = 100.0
    avg_response_time: float = 0.0


class ExchangeManager:
    """
    交易所适配器统一管理器 - TDD驱动的企业级设计
    
    功能特性：
    - 多交易所生命周期管理
    - 统一数据获取接口
    - 健康监控和故障检测
    - 自动故障恢复
    - 性能监控和统计
    - 并发数据处理
    """
    
    def __init__(self, factory: Optional[ExchangeFactory] = None):
        self.factory = factory or get_factory()
        self.logger = logging.getLogger(__name__)
        
        # 适配器管理
        self._adapters: Dict[str, ExchangeAdapter] = {}
        self._adapter_configs: Dict[str, Dict[str, Any]] = {}
        
        # 健康监控
        self._health_status: Dict[str, ExchangeHealth] = {}
        self._health_check_interval = 60  # 秒
        self._health_check_task: Optional[asyncio.Task] = None
        
        # 性能统计
        self._stats: Dict[str, Dict[str, Any]] = {}
        
        # 事件回调
        self._event_callbacks: Dict[str, List[Callable]] = {
            'adapter_added': [],
            'adapter_removed': [],
            'adapter_failed': [],
            'adapter_recovered': []
        }
        
        # 线程池
        self._thread_pool = ThreadPoolExecutor(max_workers=10, thread_name_prefix="ExchangeManager")
        self._lock = threading.RLock()
        
        self.logger.info("交易所管理器已初始化")
    
    def add_adapter(self, exchange_name: str, config: Optional[Dict[str, Any]] = None, 
                   adapter: Optional[ExchangeAdapter] = None) -> bool:
        """添加交易所适配器"""
        try:
            with self._lock:
                if exchange_name in self._adapters:
                    self.logger.warning("交易所 %s 适配器已存在，将替换", exchange_name)
                
                # 创建或使用提供的适配器
                if adapter is None:
                    adapter = self.factory.create_adapter(exchange_name, config)
                
                self._adapters[exchange_name] = adapter
                self._adapter_configs[exchange_name] = config or {}
                
                # 初始化健康状态
                self._health_status[exchange_name] = ExchangeHealth(
                    exchange_name=exchange_name,
                    is_healthy=True,
                    last_check=datetime.now()
                )
                
                # 初始化统计
                self._stats[exchange_name] = {
                    'requests_total': 0,
                    'requests_successful': 0,
                    'requests_failed': 0,
                    'avg_response_time': 0.0,
                    'last_activity': None
                }
                
                self._trigger_event('adapter_added', exchange_name, adapter)
                self.logger.info("已添加交易所适配器: %s", exchange_name)
                return True
                
        except Exception as e:
            self.logger.error("添加交易所适配器失败 %s: %s", exchange_name, str(e))
            return False
    
    def remove_adapter(self, exchange_name: str) -> bool:
        """移除交易所适配器"""
        try:
            with self._lock:
                if exchange_name not in self._adapters:
                    self.logger.warning("交易所 %s 适配器不存在", exchange_name)
                    return False
                
                adapter = self._adapters.pop(exchange_name)
                self._adapter_configs.pop(exchange_name, None)
                self._health_status.pop(exchange_name, None)
                self._stats.pop(exchange_name, None)
                
                # 停止适配器（如果有停止方法）
                if hasattr(adapter, 'stop'):
                    adapter.stop()
                
                self._trigger_event('adapter_removed', exchange_name, adapter)
                self.logger.info("已移除交易所适配器: %s", exchange_name)
                return True
                
        except Exception as e:
            self.logger.error("移除交易所适配器失败 %s: %s", exchange_name, str(e))
            return False
    
    def get_adapter(self, exchange_name: str) -> Optional[ExchangeAdapter]:
        """获取指定交易所适配器"""
        with self._lock:
            return self._adapters.get(exchange_name)
    
    def get_all_adapters(self) -> Dict[str, ExchangeAdapter]:
        """获取所有适配器"""
        with self._lock:
            return self._adapters.copy()
    
    def get_active_exchanges(self) -> List[str]:
        """获取活跃的交易所列表"""
        with self._lock:
            return [name for name, health in self._health_status.items() if health.is_healthy]
    
    def start_all(self) -> Dict[str, bool]:
        """启动所有适配器"""
        results = {}
        with self._lock:
            for exchange_name, adapter in self._adapters.items():
                try:
                    if hasattr(adapter, 'start'):
                        adapter.start()
                    results[exchange_name] = True
                    self.logger.info("已启动交易所适配器: %s", exchange_name)
                except Exception as e:
                    results[exchange_name] = False
                    self.logger.error("启动交易所适配器失败 %s: %s", exchange_name, str(e))
        
        # 启动健康检查
        self._start_health_monitoring()
        return results
    
    def stop_all(self) -> Dict[str, bool]:
        """停止所有适配器"""
        results = {}
        
        # 停止健康检查
        self._stop_health_monitoring()
        
        with self._lock:
            for exchange_name, adapter in self._adapters.items():
                try:
                    if hasattr(adapter, 'stop'):
                        adapter.stop()
                    results[exchange_name] = True
                    self.logger.info("已停止交易所适配器: %s", exchange_name)
                except Exception as e:
                    results[exchange_name] = False
                    self.logger.error("停止交易所适配器失败 %s: %s", exchange_name, str(e))
        
        return results
    
    def restart_adapter(self, exchange_name: str) -> bool:
        """重启指定适配器"""
        adapter = self.get_adapter(exchange_name)
        if adapter is None:
            return False
        
        try:
            # 停止
            if hasattr(adapter, 'stop'):
                adapter.stop()
            
            # 重新创建
            config = self._adapter_configs.get(exchange_name, {})
            new_adapter = self.factory.create_adapter(exchange_name, config, use_cache=False)
            
            # 替换
            with self._lock:
                self._adapters[exchange_name] = new_adapter
            
            # 启动
            if hasattr(new_adapter, 'start'):
                new_adapter.start()
            
            self.logger.info("已重启交易所适配器: %s", exchange_name)
            return True
            
        except Exception as e:
            self.logger.error("重启交易所适配器失败 %s: %s", exchange_name, str(e))
            return False
    
    def get_trades_from_all(self, symbol: str, **kwargs) -> Dict[str, Any]:
        """从所有交易所获取交易数据"""
        return self._execute_on_all_adapters('get_trades', symbol=symbol, **kwargs)
    
    def get_orderbook_from_all(self, symbol: str, **kwargs) -> Dict[str, Any]:
        """从所有交易所获取订单簿数据"""
        return self._execute_on_all_adapters('get_orderbook', symbol=symbol, **kwargs)
    
    def get_ticker_from_all(self, symbol: str, **kwargs) -> Dict[str, Any]:
        """从所有交易所获取行情数据"""
        return self._execute_on_all_adapters('get_ticker', symbol=symbol, **kwargs)
    
    def subscribe_trades_all(self, symbol: str, callback: Callable, **kwargs) -> Dict[str, bool]:
        """在所有交易所订阅交易数据"""
        return self._execute_on_all_adapters('subscribe_trades', symbol=symbol, callback=callback, **kwargs)
    
    def subscribe_orderbook_all(self, symbol: str, callback: Callable, **kwargs) -> Dict[str, bool]:
        """在所有交易所订阅订单簿数据"""
        return self._execute_on_all_adapters('subscribe_orderbook', symbol=symbol, callback=callback, **kwargs)
    
    def get_health_status(self) -> Dict[str, ExchangeHealth]:
        """获取所有交易所健康状态"""
        with self._lock:
            return self._health_status.copy()
    
    def get_performance_stats(self) -> Dict[str, Dict[str, Any]]:
        """获取所有交易所性能统计"""
        with self._lock:
            return self._stats.copy()
    
    def check_adapter_health(self, exchange_name: str) -> bool:
        """检查指定适配器健康状态"""
        adapter = self.get_adapter(exchange_name)
        if adapter is None:
            return False
        
        try:
            # 简单健康检查 - 尝试获取服务器时间或基本信息
            if hasattr(adapter, 'get_server_time'):
                adapter.get_server_time()
            elif hasattr(adapter, 'ping'):
                adapter.ping()
            else:
                # 默认检查 - 尝试获取某个基础数据
                adapter.get_ticker('BTC/USDT')
            
            # 更新健康状态
            with self._lock:
                if exchange_name in self._health_status:
                    health = self._health_status[exchange_name]
                    health.is_healthy = True
                    health.last_check = datetime.now()
                    health.error_count = 0
                    health.last_error = None
            
            return True
            
        except Exception as e:
            # 更新健康状态
            with self._lock:
                if exchange_name in self._health_status:
                    health = self._health_status[exchange_name]
                    health.is_healthy = False
                    health.last_check = datetime.now()
                    health.error_count += 1
                    health.last_error = str(e)
            
            self.logger.warning("交易所 %s 健康检查失败: %s", exchange_name, str(e))
            return False
    
    def add_event_callback(self, event_type: str, callback: Callable):
        """添加事件回调"""
        if event_type in self._event_callbacks:
            self._event_callbacks[event_type].append(callback)
    
    def _execute_on_all_adapters(self, method_name: str, **kwargs) -> Dict[str, Any]:
        """在所有适配器上执行方法"""
        results = {}
        futures = {}
        
        # 获取健康的适配器
        healthy_adapters = {}
        with self._lock:
            for name, adapter in self._adapters.items():
                if self._health_status.get(name, {}).get('is_healthy', True):
                    healthy_adapters[name] = adapter
        
        # 并发执行
        for exchange_name, adapter in healthy_adapters.items():
            if hasattr(adapter, method_name):
                future = self._thread_pool.submit(
                    self._safe_execute_method, adapter, method_name, exchange_name, **kwargs
                )
                futures[exchange_name] = future
        
        # 收集结果
        for exchange_name, future in futures.items():
            try:
                results[exchange_name] = future.result(timeout=30)  # 30秒超时
            except Exception as e:
                results[exchange_name] = {'error': str(e)}
                self.logger.error("执行 %s.%s 失败: %s", exchange_name, method_name, str(e))
        
        return results
    
    def _safe_execute_method(self, adapter: ExchangeAdapter, method_name: str, 
                           exchange_name: str, **kwargs) -> Any:
        """安全执行适配器方法"""
        start_time = datetime.now()
        try:
            method = getattr(adapter, method_name)
            result = method(**kwargs)
            
            # 更新统计
            response_time = (datetime.now() - start_time).total_seconds()
            self._update_stats(exchange_name, True, response_time)
            
            return result
            
        except Exception as e:
            # 更新统计
            response_time = (datetime.now() - start_time).total_seconds()
            self._update_stats(exchange_name, False, response_time)
            raise
    
    def _update_stats(self, exchange_name: str, success: bool, response_time: float):
        """更新统计信息"""
        with self._lock:
            if exchange_name in self._stats:
                stats = self._stats[exchange_name]
                stats['requests_total'] += 1
                if success:
                    stats['requests_successful'] += 1
                else:
                    stats['requests_failed'] += 1
                
                # 更新平均响应时间
                current_avg = stats['avg_response_time']
                total_requests = stats['requests_total']
                stats['avg_response_time'] = ((current_avg * (total_requests - 1)) + response_time) / total_requests
                stats['last_activity'] = datetime.now()
    
    def _start_health_monitoring(self):
        """启动健康监控"""
        if self._health_check_task is None or self._health_check_task.done():
            self._health_check_task = asyncio.create_task(self._health_check_loop())
    
    def _stop_health_monitoring(self):
        """停止健康监控"""
        if self._health_check_task and not self._health_check_task.done():
            self._health_check_task.cancel()
    
    async def _health_check_loop(self):
        """健康检查循环"""
        while True:
            try:
                exchanges = list(self._adapters.keys())
                for exchange_name in exchanges:
                    self.check_adapter_health(exchange_name)
                
                await asyncio.sleep(self._health_check_interval)
                
            except asyncio.CancelledError:
                break
            except Exception as e:
                self.logger.error("健康检查循环错误: %s", str(e))
                await asyncio.sleep(5)
    
    def _trigger_event(self, event_type: str, *args, **kwargs):
        """触发事件回调"""
        if event_type in self._event_callbacks:
            for callback in self._event_callbacks[event_type]:
                try:
                    callback(*args, **kwargs)
                except Exception as e:
                    self.logger.error("事件回调执行失败 %s: %s", event_type, str(e))
    
    def __del__(self):
        """清理资源"""
        try:
            self._stop_health_monitoring()
            self._thread_pool.shutdown(wait=False)
        except:
            pass