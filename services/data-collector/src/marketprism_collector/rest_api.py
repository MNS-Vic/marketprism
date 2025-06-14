"""
REST API Module - OrderBook Manager REST API接口

为OrderBook Manager提供HTTP REST API接口，支持：
1. 获取当前订单簿
2. 获取订单簿统计信息
3. 触发快照刷新
4. 健康检查
5. 监控和管理接口
"""

from datetime import datetime, timezone
import json
from typing import Dict, List, Optional, Any
from aiohttp import web, ClientSession
import structlog
from decimal import Decimal

from .orderbook_integration import OrderBookCollectorIntegration
from .data_types import EnhancedOrderBook, OrderBookDelta, Exchange


class OrderBookRestAPI:
    """OrderBook Manager REST API"""
    
    def __init__(self, orderbook_integration: OrderBookCollectorIntegration):
        self.integration = orderbook_integration
        self.logger = structlog.get_logger(__name__)
        
        # 统计信息
        self.api_stats = {
            'requests_total': 0,
            'requests_by_endpoint': {},
            'errors_total': 0,
            'start_time': datetime.now(timezone.utc)
        }
    
    def setup_routes(self, app: web.Application):
        """设置REST API路由"""
        # 订单簿相关接口
        app.router.add_get('/api/v1/orderbook/{exchange}/{symbol}', self.get_orderbook)
        app.router.add_get('/api/v1/orderbook/{exchange}/{symbol}/snapshot', self.get_orderbook_snapshot)
        app.router.add_post('/api/v1/orderbook/{exchange}/{symbol}/refresh', self.refresh_orderbook)
        
        # 统计和监控接口
        app.router.add_get('/api/v1/orderbook/stats', self.get_all_stats)
        app.router.add_get('/api/v1/orderbook/stats/{exchange}', self.get_exchange_stats)
        app.router.add_get('/api/v1/orderbook/health', self.health_check)
        app.router.add_get('/api/v1/orderbook/status/{exchange}/{symbol}', self.get_symbol_status)
        
        # 管理接口
        app.router.add_get('/api/v1/orderbook/exchanges', self.list_exchanges)
        app.router.add_get('/api/v1/orderbook/symbols/{exchange}', self.list_symbols)
        
        # API统计接口
        app.router.add_get('/api/v1/orderbook/api/stats', self.get_api_stats)
        
        self.logger.info("OrderBook REST API路由已设置")
    
    async def get_orderbook(self, request: web.Request) -> web.Response:
        """获取当前订单簿"""
        await self._record_request('get_orderbook')
        
        try:
            exchange = request.match_info['exchange']
            symbol = request.match_info['symbol']
            
            # 获取查询参数
            depth = int(request.query.get('depth', 20))
            format_type = request.query.get('format', 'enhanced')  # enhanced, legacy, simple
            
            # 获取当前订单簿
            orderbook = await self.integration.get_current_orderbook(exchange, symbol)
            
            if not orderbook:
                return web.json_response(
                    {'error': f'Orderbook not found for {exchange}:{symbol}'},
                    status=404
                )
            
            # 根据格式类型返回数据
            if format_type == 'simple':
                response_data = self._format_simple_orderbook(orderbook, depth)
            elif format_type == 'legacy':
                response_data = self._format_legacy_orderbook(orderbook, depth)
            else:  # enhanced
                response_data = self._format_enhanced_orderbook(orderbook, depth)
            
            # 手动序列化复杂对象
            serialized_data = self._serialize_complex_object(response_data)
            return web.json_response(serialized_data)
            
        except ValueError as e:
            return web.json_response({'error': f'Invalid parameter: {str(e)}'}, status=400)
        except Exception as e:
            await self._record_error()
            self.logger.error("获取订单簿失败", exc_info=True, exchange=exchange, symbol=symbol)
            return web.json_response({'error': 'Internal server error'}, status=500)
    
    async def get_orderbook_snapshot(self, request: web.Request) -> web.Response:
        """获取订单簿快照（强制刷新）"""
        await self._record_request('get_orderbook_snapshot')
        
        try:
            exchange = request.match_info['exchange']
            symbol = request.match_info['symbol']
            
            # 触发快照刷新
            if exchange in self.integration.integrations:
                integration = self.integration.integrations[exchange]
                success = await integration.trigger_snapshot_refresh(symbol)
                
                if success:
                    # 获取刷新后的订单簿
                    orderbook = await integration.get_current_orderbook(symbol)
                    if orderbook:
                        response_data = self._format_enhanced_orderbook(orderbook)
                        # 手动序列化复杂对象
                        serialized_data = self._serialize_complex_object(response_data)
                        return web.json_response(serialized_data)
               
                return web.json_response(
                    {'error': 'Failed to refresh snapshot'},
                    status=500
                )
           
            return web.json_response(
                {'error': f'Exchange {exchange} not found'},
                status=404
            )
           
        except Exception as e:
            await self._record_error()
            self.logger.error("获取订单簿快照失败", exc_info=True)
            return web.json_response({'error': 'Internal server error'}, status=500)
    
    async def refresh_orderbook(self, request: web.Request) -> web.Response:
        """刷新订单簿"""
        await self._record_request('refresh_orderbook')
        
        try:
            exchange = request.match_info['exchange']
            symbol = request.match_info['symbol']
            
            if exchange in self.integration.integrations:
                integration = self.integration.integrations[exchange]
                success = await integration.trigger_snapshot_refresh(symbol)
                
                return web.json_response({
                    'success': success,
                    'message': 'Snapshot refresh triggered' if success else 'Failed to trigger refresh',
                    'timestamp': datetime.now(timezone.utc).isoformat()
                })
           
            return web.json_response(
                {'error': f'Exchange {exchange} not found'},
                status=404
            )
           
        except Exception as e:
            await self._record_error()
            self.logger.error("刷新订单簿失败", exc_info=True)
            return web.json_response({'error': 'Internal server error'}, status=500)
    
    async def get_all_stats(self, request: web.Request) -> web.Response:
        """获取所有统计信息"""
        await self._record_request('get_all_stats')
        
        try:
            stats = self.integration.get_all_stats()
            # 手动序列化复杂对象
            serialized_stats = self._serialize_complex_object(stats)
            return web.json_response(serialized_stats)
            
        except Exception as e:
            await self._record_error()
            self.logger.error("获取统计信息失败", exc_info=True)
            return web.json_response({'error': f'Internal server error: {str(e)}'}, status=500)
    
    async def get_exchange_stats(self, request: web.Request) -> web.Response:
        """获取特定交易所统计信息"""
        await self._record_request('get_exchange_stats')
        
        try:
            exchange = request.match_info['exchange']
            
            if exchange in self.integration.integrations:
                integration = self.integration.integrations[exchange]
                stats = integration.get_integration_stats()
                # 手动序列化复杂对象
                serialized_stats = self._serialize_complex_object(stats)
                return web.json_response(serialized_stats)
            
            return web.json_response(
                {'error': f'Exchange {exchange} not found'},
                status=404
            )
           
        except Exception as e:
            await self._record_error()
            self.logger.error("获取交易所统计信息失败", exc_info=True)
            return web.json_response({'error': 'Internal server error'}, status=500)
    
    async def health_check(self, request: web.Request) -> web.Response:
        """健康检查"""
        await self._record_request('health_check')
        
        try:
            health = await self.integration.health_check_all()
            
            # 根据健康状态设置HTTP状态码
            status_code = 200
            if health['overall_status'] == 'unhealthy':
                status_code = 503
            elif health['overall_status'] == 'degraded':
                status_code = 206
            
            # 手动序列化复杂对象
            serialized_health = self._serialize_complex_object(health)
            return web.json_response(serialized_health, status=status_code)
            
        except Exception as e:
            await self._record_error()
            self.logger.error("健康检查失败", exc_info=True)
            return web.json_response(
                {
                    'overall_status': 'error',
                    'error': f'Health check failed: {str(e)}',
                    'timestamp': datetime.now(timezone.utc).isoformat()
                },
                status=500
            )
    
    async def get_symbol_status(self, request: web.Request) -> web.Response:
        """获取交易对状态"""
        await self._record_request('get_symbol_status')
        
        try:
            exchange = request.match_info['exchange']
            symbol = request.match_info['symbol']
            
            if exchange in self.integration.integrations:
                integration = self.integration.integrations[exchange]
                status = integration.get_symbol_status(symbol)
                # 手动序列化复杂对象
                serialized_status = self._serialize_complex_object(status)
                return web.json_response(serialized_status)
            
            return web.json_response(
                {'error': f'Exchange {exchange} not found'},
                status=404
            )
           
        except Exception as e:
            await self._record_error()
            self.logger.error("获取交易对状态失败", exc_info=True)
            return web.json_response({'error': 'Internal server error'}, status=500)
    
    async def list_exchanges(self, request: web.Request) -> web.Response:
        """列出所有交易所"""
        await self._record_request('list_exchanges')
        
        try:
            exchanges = list(self.integration.integrations.keys())
            return web.json_response({
                'exchanges': exchanges,
                'count': len(exchanges),
                'timestamp': datetime.now(timezone.utc).isoformat()
            })
            
        except Exception as e:
            await self._record_error()
            self.logger.error("列出交易所失败", exc_info=True)
            return web.json_response({'error': 'Internal server error'}, status=500)
    
    async def list_symbols(self, request: web.Request) -> web.Response:
        """列出交易所的所有交易对"""
        await self._record_request('list_symbols')
        
        try:
            exchange = request.match_info['exchange']
            
            if exchange in self.integration.integrations:
                integration = self.integration.integrations[exchange]
                symbols = integration.symbols
                return web.json_response({
                    'exchange': exchange,
                    'symbols': symbols,
                    'count': len(symbols),
                    'timestamp': datetime.now(timezone.utc).isoformat()
                })
            
            return web.json_response(
                {'error': f'Exchange {exchange} not found'},
                status=404
            )
           
        except Exception as e:
            await self._record_error()
            self.logger.error("列出交易对失败", exc_info=True)
            return web.json_response({'error': 'Internal server error'}, status=500)
    
    async def get_api_stats(self, request: web.Request) -> web.Response:
        """获取API统计信息"""
        await self._record_request('get_api_stats')
        
        try:
            uptime = datetime.now(timezone.utc) - self.api_stats['start_time']
            
            stats = {
                'api_stats': self.api_stats.copy(),
                'uptime_seconds': uptime.total_seconds(),
                'uptime_human': str(uptime),
                'timestamp': datetime.now(timezone.utc).isoformat()
            }
            
            # 手动序列化复杂对象
            serialized_stats = self._serialize_complex_object(stats)
            return web.json_response(serialized_stats)
            
        except Exception as e:
            await self._record_error()
            self.logger.error("获取API统计信息失败", exc_info=True)
            return web.json_response({'error': 'Internal server error'}, status=500)
    
    def get_stats(self) -> Dict[str, Any]:
        """获取统计信息（同步方法）"""
        uptime = datetime.now(timezone.utc) - self.api_stats['start_time']
        return {
            'api_stats': self.api_stats.copy(),
            'uptime_seconds': uptime.total_seconds(),
            'uptime_human': str(uptime),
            'timestamp': datetime.now(timezone.utc).isoformat()
        }
    
    def _format_simple_orderbook(self, orderbook: EnhancedOrderBook, depth: int = 20) -> Dict[str, Any]:
        """格式化为简单订单簿格式"""
        return {
            'symbol': orderbook.symbol_name,
            'exchange': orderbook.exchange_name,
            'timestamp': orderbook.timestamp.isoformat(),
            'bids': [[str(level.price), str(level.quantity)] for level in orderbook.bids[:depth]]
            ,'asks': [[str(level.price), str(level.quantity)] for level in orderbook.asks[:depth]]
        }
    
    def _format_legacy_orderbook(self, orderbook: EnhancedOrderBook, depth: int = 20) -> Dict[str, Any]:
        """格式化为传统订单簿格式"""
        return {
            'exchange_name': orderbook.exchange_name,
            'symbol_name': orderbook.symbol_name,
            'last_update_id': orderbook.last_update_id,
            'bids': [{'price': str(level.price), 'quantity': str(level.quantity)} for level in orderbook.bids[:depth]]
            ,'asks': [{'price': str(level.price), 'quantity': str(level.quantity)} for level in orderbook.asks[:depth]]
            ,'timestamp': orderbook.timestamp.isoformat()
            ,'collected_at': orderbook.collected_at.isoformat()
        }
    
    def _format_enhanced_orderbook(self, orderbook: EnhancedOrderBook, depth: int = 20) -> Dict[str, Any]:
        """格式化为增强订单簿格式"""
        data = {
            'exchange_name': orderbook.exchange_name,
            'symbol_name': orderbook.symbol_name,
            'last_update_id': orderbook.last_update_id,
            'update_type': orderbook.update_type.value,
            'depth_levels': orderbook.depth_levels,
            'is_valid': orderbook.is_valid,
            'bids': [{'price': str(level.price), 'quantity': str(level.quantity)} for level in orderbook.bids[:depth]]
            ,'asks': [{'price': str(level.price), 'quantity': str(level.quantity)} for level in orderbook.asks[:depth]]
            ,'timestamp': orderbook.timestamp.isoformat()
            ,'collected_at': orderbook.collected_at.isoformat()
            ,'processed_at': orderbook.processed_at.isoformat()
        }
        
        # 添加同步状态信息
        exchange = orderbook.exchange_name
        symbol = orderbook.symbol_name
        if exchange in self.integration.integrations:
            integration = self.integration.integrations[exchange]
            if hasattr(integration, 'orderbook_manager') and integration.orderbook_manager:
                manager = integration.orderbook_manager
                if symbol in manager.orderbook_states:
                    state = manager.orderbook_states[symbol]
                    data['is_synced'] = state.is_synced
                    data['sync_status'] = {
                        'is_synced': state.is_synced,
                        'error_count': state.error_count,
                        'total_updates': state.total_updates,
                        'buffer_size': len(state.update_buffer),
                        'sync_in_progress': state.sync_in_progress
                    }
        
        # 添加可选字段
        if orderbook.first_update_id is not None:
            data['first_update_id'] = orderbook.first_update_id
        if orderbook.prev_update_id is not None:
            data['prev_update_id'] = orderbook.prev_update_id
        if orderbook.checksum is not None:
            data['checksum'] = orderbook.checksum
        if orderbook.validation_errors:
            data['validation_errors'] = orderbook.validation_errors
        
        return data
    
    async def _record_request(self, endpoint: str):
        """记录请求统计"""
        self.api_stats['requests_total'] += 1
        if endpoint not in self.api_stats['requests_by_endpoint']:
            self.api_stats['requests_by_endpoint'][endpoint] = 0
        self.api_stats['requests_by_endpoint'][endpoint] += 1
    
    async def _record_error(self):
        """记录错误统计"""
        self.api_stats['errors_total'] += 1
    
    def _json_serializer(self, obj):
        """JSON序列化器"""
        if isinstance(obj, datetime):
            return obj.isoformat() + 'Z'
        elif isinstance(obj, Decimal):
            return str(obj)
        elif hasattr(obj, '__dict__'):
            # 如果是对象，转换为字典
            return obj.__dict__
        elif isinstance(obj, (list, tuple)):
            return [self._json_serializer(item) for item in obj]
        elif isinstance(obj, dict):
            return {key: self._json_serializer(value) for key, value in obj.items()}
        else:
            return str(obj)
    
    def _serialize_complex_object(self, obj, visited=None):
        """序列化复杂对象 - TDD修复：防止无限递归"""
        # 防止循环引用
        if visited is None:
            visited = set()
        
        # 检查循环引用
        obj_id = id(obj)
        if obj_id in visited:
            return "<recursive reference>"
        
        # 基本类型处理
        if isinstance(obj, datetime):
            return obj.isoformat() + 'Z'
        elif isinstance(obj, Decimal):
            return str(obj)
        elif isinstance(obj, (str, int, float, bool, type(None))):
            return obj
        elif isinstance(obj, dict):
            visited.add(obj_id)
            try:
                result = {key: self._serialize_complex_object(value, visited) for key, value in obj.items()}
                visited.remove(obj_id)
                return result
            except:
                visited.discard(obj_id)
                return "<dict serialization error>"
        elif isinstance(obj, (list, tuple)):
            visited.add(obj_id)
            try:
                result = [self._serialize_complex_object(item, visited) for item in obj]
                visited.remove(obj_id)
                return result
            except:
                visited.discard(obj_id)
                return "<list serialization error>"
        elif hasattr(obj, '__dict__'):
            # 特殊情况处理：跳过Mock对象和其他问题对象
            obj_type = type(obj).__name__
            if any(mock_type in obj_type for mock_type in ['Mock', 'AsyncMock', 'MagicMock']):
                return f"<{obj_type} object>"
            
            # 处理普通对象
            visited.add(obj_id)
            try:
                # 只序列化公共属性，跳过私有属性
                result = {}
                for key, value in obj.__dict__.items():
                    if not key.startswith('_'):  # 跳过私有属性
                        result[key] = self._serialize_complex_object(value, visited)
                visited.remove(obj_id)
                return result
            except:
                visited.discard(obj_id)
                return f"<{obj_type} serialization error>"
        else:
            # 其他类型转为字符串
            return str(obj)


class OrderBookWebSocketAPI:
    """OrderBook WebSocket API (未来扩展)"""
    
    def __init__(self, orderbook_integration: OrderBookCollectorIntegration):
        self.integration = orderbook_integration
        self.logger = structlog.get_logger(__name__)
        self.connections: Dict[str, Any] = {}
    
    async def setup_websocket_routes(self, app: web.Application):
        """设置WebSocket路由"""
        # 为未来的WebSocket实时推送预留
        app.router.add_get('/ws/orderbook/{exchange}/{symbol}', self.websocket_handler)
        self.logger.info("OrderBook WebSocket API路由已设置")
    
    async def websocket_handler(self, request: web.Request):
        """WebSocket处理器（未来实现）"""
        # 未来可以实现实时订单簿推送
        return web.Response(text="WebSocket API coming soon", status=501) 