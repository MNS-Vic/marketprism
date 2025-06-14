"""
OrderBook Integration - 订单簿管理器集成模块

将OrderBook Manager集成到现有的collector系统中
"""

from datetime import datetime, timezone
import asyncio
from typing import Dict, List, Optional, Any
import structlog

from .orderbook_manager import OrderBookManager
from .normalizer import DataNormalizer
from .nats_client import EnhancedMarketDataPublisher
from .data_types import (
    ExchangeConfig, Exchange, EnhancedOrderBook, OrderBookDelta,
    OrderBookUpdateType
)


class OrderBookIntegration:
    """订单簿管理器集成器"""
    
    def __init__(
        self, 
        config: ExchangeConfig, 
        normalizer: DataNormalizer,
        publisher: EnhancedMarketDataPublisher
    ):
        self.config = config
        self.normalizer = normalizer
        self.publisher = publisher
        self.logger = structlog.get_logger(__name__)
        
        # 创建OrderBook Manager
        self.orderbook_manager = OrderBookManager(config, normalizer)
        
        # 状态管理
        self.is_running = False
        self.symbols = config.symbols
        
        # 统计信息
        self.stats = {
            'full_orderbooks_published': 0,
            'delta_orderbooks_published': 0,
            'snapshots_published': 0,
            'updates_published': 0,
            'errors': 0
        }
    
    async def start(self) -> bool:
        """启动订单簿集成"""
        try:
            # 启动OrderBook Manager
            success = await self.orderbook_manager.start(self.symbols)
            if not success:
                return False
            
            self.is_running = True
            
            self.logger.info(
                "订单簿集成启动成功",
                exchange=self.config.exchange.value,
                symbols=self.symbols,
                depth_limit=self.config.depth_limit
            )
            return True
            
        except Exception as e:
            self.logger.error(
                "订单簿集成启动失败",
                exc_info=True,
                exchange=self.config.exchange.value
            )
            return False
    
    async def stop(self):
        """停止订单簿集成"""
        self.is_running = False
        await self.orderbook_manager.stop()
        
        self.logger.info(
            "订单簿集成已停止",
            exchange=self.config.exchange.value,
            stats=self.stats
        )
    
    async def process_websocket_update(self, symbol: str, raw_data: Dict[str, Any]) -> bool:
        """处理WebSocket增量更新"""
        if not self.is_running:
            return False
        
        try:
            # 使用OrderBook Manager处理更新
            enhanced_orderbook = await self.orderbook_manager.process_update(symbol, raw_data)
            
            if enhanced_orderbook:
                # 发布增强订单簿到全量流
                await self._publish_enhanced_orderbook(enhanced_orderbook)
                
                # 创建并发布增量数据到增量流
                await self._publish_orderbook_delta(enhanced_orderbook, raw_data)
                
                return True
            
            return False
            
        except Exception as e:
            self.stats['errors'] += 1
            self.logger.error(
                "处理WebSocket更新失败",
                symbol=symbol,
                exc_info=True,
                exchange=self.config.exchange.value
            )
            return False
    
    async def _publish_enhanced_orderbook(self, enhanced_orderbook: EnhancedOrderBook):
        """发布增强订单簿到全量流"""
        try:
            # 发布到全量订单簿流
            await self.publisher.publish_enhanced_orderbook(enhanced_orderbook)
            
            # 更新统计
            if enhanced_orderbook.update_type == OrderBookUpdateType.SNAPSHOT:
                self.stats['snapshots_published'] += 1
            else:
                self.stats['updates_published'] += 1
            
            self.stats['full_orderbooks_published'] += 1
            
            self.logger.debug(
                "发布增强订单簿成功",
                symbol=enhanced_orderbook.symbol_name,
                update_type=enhanced_orderbook.update_type.value,
                depth_levels=enhanced_orderbook.depth_levels
            )
            
        except Exception as e:
            self.stats['errors'] += 1
            self.logger.error(
                "发布增强订单簿失败",
                symbol=enhanced_orderbook.symbol_name,
                exc_info=True
            )
    
    async def _publish_orderbook_delta(self, enhanced_orderbook: EnhancedOrderBook, raw_data: Dict[str, Any]):
        """发布订单簿增量到增量流"""
        try:
            # 只有UPDATE类型才发布增量
            if enhanced_orderbook.update_type != OrderBookUpdateType.UPDATE:
                return
            
            # 提取增量变化
            bid_updates = enhanced_orderbook.bid_changes or []
            ask_updates = enhanced_orderbook.ask_changes or []
            
            # 如果没有变化，不发布
            if not bid_updates and not ask_updates:
                return
            
            # 创建OrderBookDelta
            delta = self.normalizer.create_orderbook_delta(
                exchange=enhanced_orderbook.exchange_name,
                symbol=enhanced_orderbook.symbol_name,
                update_id=enhanced_orderbook.last_update_id or 0,
                bid_updates=bid_updates,
                ask_updates=ask_updates,
                prev_update_id=enhanced_orderbook.prev_update_id
            )
            
            # 发布到增量流
            await self.publisher.publish_orderbook_delta(delta)
            
            self.stats['delta_orderbooks_published'] += 1
            
            self.logger.debug(
                "发布订单簿增量成功",
                symbol=delta.symbol_name,
                bid_changes=delta.total_bid_changes,
                ask_changes=delta.total_ask_changes
            )
            
        except Exception as e:
            self.stats['errors'] += 1
            self.logger.error(
                "发布订单簿增量失败",
                symbol=enhanced_orderbook.symbol_name,
                exc_info=True
            )
    
    async def get_current_orderbook(self, symbol: str) -> Optional[EnhancedOrderBook]:
        """获取当前订单簿"""
        return self.orderbook_manager.get_current_orderbook(symbol)
    
    async def trigger_snapshot_refresh(self, symbol: str) -> bool:
        """触发快照刷新"""
        try:
            # 直接调用OrderBook Manager的刷新方法
            await self.orderbook_manager._refresh_snapshot(symbol)
            
            # 获取刷新后的订单簿并发布
            current_orderbook = await self.get_current_orderbook(symbol)
            if current_orderbook:
                current_orderbook.update_type = OrderBookUpdateType.FULL_REFRESH
                await self._publish_enhanced_orderbook(current_orderbook)
                
            self.logger.info(
                "快照刷新成功",
                symbol=symbol
            )
            return True
            
        except Exception as e:
            self.logger.error(
                "触发快照刷新失败",
                symbol=symbol,
                exc_info=True
            )
            return False
    
    def get_integration_stats(self) -> Dict[str, Any]:
        """获取集成统计信息"""
        manager_stats = self.orderbook_manager.get_stats()
        
        return {
            'integration_stats': self.stats,
            'manager_stats': manager_stats,
            'is_running': self.is_running,
            'symbols': self.symbols,
            'config': {
                'exchange': self.config.exchange.value,
                'depth_limit': self.config.depth_limit,
                'snapshot_interval': self.config.snapshot_interval
            }
        }
    
    def get_symbol_status(self, symbol: str) -> Dict[str, Any]:
        """获取单个交易对的状态"""
        if symbol not in self.orderbook_manager.orderbook_states:
            return {'error': 'Symbol not managed'}
        
        state = self.orderbook_manager.orderbook_states[symbol]
        return {
            'symbol': symbol,
            'is_synced': state.is_synced,
            'last_update_id': state.last_update_id,
            'buffer_size': len(state.update_buffer),
            'error_count': state.error_count,
            'total_updates': state.total_updates,
            'last_snapshot_time': state.last_snapshot_time.isoformat(),
            'has_orderbook': state.local_orderbook is not None
        }
    
    async def health_check(self) -> Dict[str, Any]:
        """健康检查"""
        try:
            health_status = {
                'status': 'healthy',
                'timestamp': datetime.now(timezone.utc).isoformat(),
                'is_running': self.is_running,
                'exchange': self.config.exchange.value,
                'symbols_count': len(self.symbols),
                'synced_symbols': 0,
                'total_errors': self.stats['errors']
            }
            
            # 检查每个交易对的同步状态
            synced_count = 0
            symbol_statuses = {}
            
            for symbol in self.symbols:
                status = self.get_symbol_status(symbol)
                symbol_statuses[symbol] = status
                if status.get('is_synced', False):
                    synced_count += 1
            
            health_status['synced_symbols'] = synced_count
            health_status['symbol_statuses'] = symbol_statuses
            
            # 判断整体健康状态
            if synced_count == 0:
                health_status['status'] = 'unhealthy'
            elif synced_count < len(self.symbols):
                health_status['status'] = 'degraded'
            
            return health_status
            
        except Exception as e:
            return {
                'status': 'error',
                'timestamp': datetime.now(timezone.utc).isoformat(),
                'error': str(e)
            }


class OrderBookCollectorIntegration:
    """订单簿收集器集成 - 与现有collector的集成点"""
    
    def __init__(self):
        self.integrations: Dict[str, OrderBookIntegration] = {}
        self.logger = structlog.get_logger(__name__)
    
    async def add_exchange_integration(
        self, 
        config: ExchangeConfig, 
        normalizer: DataNormalizer,
        publisher: EnhancedMarketDataPublisher
    ) -> bool:
        """添加交易所集成"""
        try:
            integration = OrderBookIntegration(config, normalizer, publisher)
            success = await integration.start()
            
            if success:
                self.integrations[config.exchange.value] = integration
                self.logger.info(
                    "添加交易所集成成功",
                    exchange=config.exchange.value,
                    symbols=config.symbols
                )
                return True
            else:
                self.logger.error(
                    "添加交易所集成失败",
                    exchange=config.exchange.value
                )
                return False
                
        except Exception as e:
            self.logger.error(
                "添加交易所集成异常",
                exchange=config.exchange.value,
                exc_info=True
            )
            return False
    
    async def process_websocket_message(
        self, 
        exchange: str, 
        symbol: str, 
        raw_data: Dict[str, Any]
    ) -> bool:
        """处理WebSocket消息"""
        if exchange not in self.integrations:
            return False
        
        integration = self.integrations[exchange]
        return await integration.process_websocket_update(symbol, raw_data)
    
    async def get_current_orderbook(self, exchange: str, symbol: str) -> Optional[EnhancedOrderBook]:
        """获取当前订单簿"""
        if exchange not in self.integrations:
            return None
        
        integration = self.integrations[exchange]
        return await integration.get_current_orderbook(symbol)
    
    async def stop_all(self):
        """停止所有集成"""
        for integration in self.integrations.values():
            await integration.stop()
        
        self.integrations.clear()
        self.logger.info("所有订单簿集成已停止")
    
    def get_all_stats(self) -> Dict[str, Any]:
        """获取所有集成的统计信息"""
        all_stats = {}
        for exchange, integration in self.integrations.items():
            all_stats[exchange] = integration.get_integration_stats()
        
        return {
            'exchanges': all_stats,
            'total_integrations': len(self.integrations),
            'timestamp': datetime.now(timezone.utc).isoformat()
        }
    
    def get_statistics(self) -> Dict[str, Any]:
        """获取统计信息（别名）"""
        return self.get_all_stats()
    
    async def health_check_all(self) -> Dict[str, Any]:
        """所有集成的健康检查"""
        health_results = {}
        overall_status = 'healthy'
        
        for exchange, integration in self.integrations.items():
            health = await integration.health_check()
            health_results[exchange] = health
            
            # 更新整体状态
            if health['status'] == 'unhealthy':
                overall_status = 'unhealthy'
            elif health['status'] == 'degraded' and overall_status == 'healthy':
                overall_status = 'degraded'
        
        return {
            'overall_status': overall_status,
            'exchanges': health_results,
            'timestamp': datetime.now(timezone.utc).isoformat()
        } 