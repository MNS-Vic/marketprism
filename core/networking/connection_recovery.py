#!/usr/bin/env python3
"""
连接恢复机制
确保WebSocket连接断开重连后，所有订阅的数据流都能完整恢复
"""

import asyncio
import json
from datetime import datetime, timezone, timedelta
from dataclasses import dataclass, field
from typing import Dict, List, Set, Optional, Callable, Any
from enum import Enum
import structlog

logger = structlog.get_logger(__name__)


class HealthStatus(Enum):
    """健康状态枚举"""
    HEALTHY = "healthy"
    WARNING = "warning"
    CRITICAL = "critical"
    UNKNOWN = "unknown"


@dataclass
class DataFlowHealth:
    """数据流健康状态"""
    exchange: str
    market_type: str
    symbol: str
    last_update: Optional[datetime] = None
    message_count: int = 0
    error_count: int = 0
    status: HealthStatus = HealthStatus.UNKNOWN
    expected_interval: int = 10  # 期望的更新间隔（秒）
    
    def update_received(self):
        """记录收到更新"""
        self.last_update = datetime.now(timezone.utc)
        self.message_count += 1
        self.status = HealthStatus.HEALTHY
    
    def error_occurred(self):
        """记录错误"""
        self.error_count += 1
        if self.error_count > 5:
            self.status = HealthStatus.CRITICAL
        elif self.error_count > 2:
            self.status = HealthStatus.WARNING
    
    def check_health(self) -> HealthStatus:
        """检查健康状态"""
        if not self.last_update:
            self.status = HealthStatus.UNKNOWN
            return self.status
        
        # 检查是否长时间没有更新
        time_since_update = (datetime.now(timezone.utc) - self.last_update).total_seconds()
        
        if time_since_update > self.expected_interval * 3:
            self.status = HealthStatus.CRITICAL
        elif time_since_update > self.expected_interval * 2:
            self.status = HealthStatus.WARNING
        elif self.error_count > 5:
            self.status = HealthStatus.CRITICAL
        elif self.error_count > 2:
            self.status = HealthStatus.WARNING
        else:
            self.status = HealthStatus.HEALTHY
        
        return self.status


@dataclass
class SubscriptionState:
    """订阅状态"""
    exchange: str
    market_type: str
    symbols: Set[str] = field(default_factory=set)
    subscribed_at: Optional[datetime] = None
    is_active: bool = False
    connection_id: Optional[str] = None
    
    def add_symbol(self, symbol: str):
        """添加交易对"""
        self.symbols.add(symbol)
    
    def remove_symbol(self, symbol: str):
        """移除交易对"""
        self.symbols.discard(symbol)
    
    def mark_subscribed(self, connection_id: str):
        """标记为已订阅"""
        self.subscribed_at = datetime.now(timezone.utc)
        self.is_active = True
        self.connection_id = connection_id
    
    def mark_unsubscribed(self):
        """标记为未订阅"""
        self.is_active = False
        self.connection_id = None


class ConnectionRecoveryManager:
    """连接恢复管理器"""
    
    def __init__(self, websocket_manager):
        self.websocket_manager = websocket_manager
        self.logger = structlog.get_logger(__name__)
        
        # 订阅状态管理
        self.subscription_states: Dict[str, SubscriptionState] = {}
        
        # 数据流健康监控
        self.data_flow_health: Dict[str, DataFlowHealth] = {}
        
        # 恢复任务
        self.health_check_task: Optional[asyncio.Task] = None
        self.recovery_task: Optional[asyncio.Task] = None
        
        # 配置
        self.health_check_interval = 30  # 健康检查间隔（秒）
        self.recovery_check_interval = 60  # 恢复检查间隔（秒）
        
        # 控制标志
        self.is_running = False
    
    async def start(self):
        """启动恢复管理器"""
        if self.is_running:
            return
        
        self.is_running = True
        self.logger.info("启动连接恢复管理器")
        
        # 启动健康检查任务
        self.health_check_task = asyncio.create_task(self._health_check_loop())
        self.recovery_task = asyncio.create_task(self._recovery_loop())
    
    async def stop(self):
        """停止恢复管理器"""
        self.is_running = False
        
        # 取消任务
        tasks = [self.health_check_task, self.recovery_task]
        for task in tasks:
            if task and not task.done():
                task.cancel()
                try:
                    await task
                except asyncio.CancelledError:
                    pass
        
        self.logger.info("连接恢复管理器已停止")
    
    def register_subscription(self, exchange: str, market_type: str, symbols: List[str]) -> str:
        """注册订阅"""
        subscription_key = f"{exchange}_{market_type}"
        
        if subscription_key not in self.subscription_states:
            self.subscription_states[subscription_key] = SubscriptionState(
                exchange=exchange,
                market_type=market_type
            )
        
        # 添加交易对
        for symbol in symbols:
            self.subscription_states[subscription_key].add_symbol(symbol)
            
            # 初始化数据流健康监控
            health_key = f"{exchange}_{market_type}_{symbol}"
            if health_key not in self.data_flow_health:
                self.data_flow_health[health_key] = DataFlowHealth(
                    exchange=exchange,
                    market_type=market_type,
                    symbol=symbol
                )
        
        self.logger.info("注册订阅", 
                        exchange=exchange, 
                        market_type=market_type, 
                        symbols=symbols)
        
        return subscription_key
    
    def mark_subscription_active(self, subscription_key: str, connection_id: str):
        """标记订阅为活跃状态"""
        if subscription_key in self.subscription_states:
            self.subscription_states[subscription_key].mark_subscribed(connection_id)
            self.logger.info("订阅已激活", subscription_key=subscription_key)
    
    def mark_subscription_inactive(self, subscription_key: str):
        """标记订阅为非活跃状态"""
        if subscription_key in self.subscription_states:
            self.subscription_states[subscription_key].mark_unsubscribed()
            self.logger.warning("订阅已失效", subscription_key=subscription_key)
    
    def record_data_update(self, exchange: str, market_type: str, symbol: str):
        """记录数据更新"""
        health_key = f"{exchange}_{market_type}_{symbol}"
        if health_key in self.data_flow_health:
            self.data_flow_health[health_key].update_received()
    
    def record_data_error(self, exchange: str, market_type: str, symbol: str):
        """记录数据错误"""
        health_key = f"{exchange}_{market_type}_{symbol}"
        if health_key in self.data_flow_health:
            self.data_flow_health[health_key].error_occurred()
    
    async def _health_check_loop(self):
        """健康检查循环"""
        while self.is_running:
            try:
                await self._perform_health_check()
                await asyncio.sleep(self.health_check_interval)
            except asyncio.CancelledError:
                break
            except Exception as e:
                self.logger.error("健康检查异常", error=str(e))
                await asyncio.sleep(self.health_check_interval)
    
    async def _perform_health_check(self):
        """执行健康检查"""
        unhealthy_flows = []
        
        for health_key, health in self.data_flow_health.items():
            status = health.check_health()
            
            if status in [HealthStatus.CRITICAL, HealthStatus.WARNING]:
                unhealthy_flows.append((health_key, health))
                
                self.logger.warning("发现不健康的数据流",
                                  health_key=health_key,
                                  status=status.value,
                                  last_update=health.last_update,
                                  error_count=health.error_count)
        
        if unhealthy_flows:
            self.logger.warning(f"发现 {len(unhealthy_flows)} 个不健康的数据流")
            # 触发恢复机制
            await self._trigger_recovery(unhealthy_flows)
    
    async def _recovery_loop(self):
        """恢复检查循环"""
        while self.is_running:
            try:
                await self._check_and_recover_subscriptions()
                await asyncio.sleep(self.recovery_check_interval)
            except asyncio.CancelledError:
                break
            except Exception as e:
                self.logger.error("恢复检查异常", error=str(e))
                await asyncio.sleep(self.recovery_check_interval)
    
    async def _check_and_recover_subscriptions(self):
        """检查并恢复订阅"""
        for subscription_key, state in self.subscription_states.items():
            if not state.is_active:
                self.logger.warning("发现非活跃订阅，尝试恢复", subscription_key=subscription_key)
                await self._recover_subscription(subscription_key, state)
    
    async def _trigger_recovery(self, unhealthy_flows: List[tuple]):
        """触发恢复机制"""
        # 按交易所和市场类型分组
        recovery_groups = {}
        
        for health_key, health in unhealthy_flows:
            group_key = f"{health.exchange}_{health.market_type}"
            if group_key not in recovery_groups:
                recovery_groups[group_key] = []
            recovery_groups[group_key].append(health)
        
        # 对每个组执行恢复
        for group_key, health_list in recovery_groups.items():
            if group_key in self.subscription_states:
                await self._recover_subscription(group_key, self.subscription_states[group_key])
    
    async def _recover_subscription(self, subscription_key: str, state: SubscriptionState):
        """恢复订阅"""
        try:
            self.logger.info("开始恢复订阅", subscription_key=subscription_key)
            
            # 如果有现有连接，先关闭
            if state.connection_id:
                await self.websocket_manager.remove_connection(state.connection_id)
            
            # 重新创建连接
            from core.networking.websocket_manager import (
                create_binance_websocket_config,
                create_okx_websocket_config,
                WebSocketConnectionManager
            )
            
            symbols = list(state.symbols)
            
            # 创建配置
            if state.exchange == "binance":
                config = create_binance_websocket_config(state.market_type, symbols)
            elif state.exchange == "okx":
                config = create_okx_websocket_config(state.market_type, symbols)
            else:
                self.logger.error("不支持的交易所", exchange=state.exchange)
                return
            
            # 创建消息处理器
            async def message_handler(exchange: str, market_type: str, data: Dict[str, Any]):
                # 这里应该调用实际的消息处理逻辑
                # 暂时只记录数据更新
                if 'symbol' in data or 'instId' in data:
                    symbol = data.get('symbol') or data.get('instId')
                    if symbol:
                        self.record_data_update(exchange, market_type, symbol)
            
            # 创建连接
            connection_id = f"{subscription_key}_{int(datetime.now().timestamp())}"

            # 使用WebSocket管理器创建连接
            connection = await self.websocket_manager.create_connection(config)
            if connection:
                self.websocket_manager.connections[connection_id] = connection
            
            # 更新状态
            self.mark_subscription_active(subscription_key, connection_id)
            
            self.logger.info("订阅恢复成功", subscription_key=subscription_key)
            
        except Exception as e:
            self.logger.error("订阅恢复失败", 
                            subscription_key=subscription_key, 
                            error=str(e))
    
    def get_health_report(self) -> Dict[str, Any]:
        """获取健康报告"""
        report = {
            'timestamp': datetime.now(timezone.utc).isoformat(),
            'total_subscriptions': len(self.subscription_states),
            'active_subscriptions': sum(1 for s in self.subscription_states.values() if s.is_active),
            'total_data_flows': len(self.data_flow_health),
            'health_summary': {
                'healthy': 0,
                'warning': 0,
                'critical': 0,
                'unknown': 0
            },
            'subscriptions': {},
            'data_flows': {}
        }
        
        # 订阅状态
        for key, state in self.subscription_states.items():
            report['subscriptions'][key] = {
                'exchange': state.exchange,
                'market_type': state.market_type,
                'symbols': list(state.symbols),
                'is_active': state.is_active,
                'subscribed_at': state.subscribed_at.isoformat() if state.subscribed_at else None
            }
        
        # 数据流健康状态
        for key, health in self.data_flow_health.items():
            status = health.check_health()
            report['health_summary'][status.value] += 1
            
            report['data_flows'][key] = {
                'exchange': health.exchange,
                'market_type': health.market_type,
                'symbol': health.symbol,
                'status': status.value,
                'last_update': health.last_update.isoformat() if health.last_update else None,
                'message_count': health.message_count,
                'error_count': health.error_count
            }
        
        return report


# 全局连接恢复管理器实例
recovery_manager = None


def get_recovery_manager(websocket_manager=None):
    """获取连接恢复管理器实例"""
    global recovery_manager
    if recovery_manager is None and websocket_manager:
        recovery_manager = ConnectionRecoveryManager(websocket_manager)
    return recovery_manager
