"""
MarketPrism日志系统迁移示例

展示如何将现有代码迁移到新的统一日志系统。
"""

# ============================================================================
# 迁移前：原始代码（存在的问题）
# ============================================================================

class BinanceSpotManagerOld:
    """迁移前的Binance现货管理器 - 存在日志问题"""
    
    def __init__(self, symbols, config):
        # ❌ 问题1：直接使用structlog，格式不统一
        import structlog
        self.logger = structlog.get_logger(f"collector.orderbook_managers.binance_spot")
        
        # ❌ 问题2：过度使用emoji，影响生产环境
        self.logger.info("🏭 Binance现货订单簿管理器初始化完成", symbols=symbols)
    
    async def _process_message(self, symbol: str, update: dict):
        """处理消息 - 原始版本"""
        try:
            # ❌ 问题3：DEBUG级别滥用，每条消息都记录
            self.logger.debug(f"🔍 开始处理单个消息: {symbol}")
            self.logger.debug(f"🔍 消息内容: U={update.get('U')}, u={update.get('u')}")
            
            # 处理逻辑...
            await self._apply_update(symbol, update)
            
            # ❌ 问题4：成功日志过于频繁，造成日志洪水
            self.logger.debug(f"✅ 单个消息处理完成: {symbol}")
            
        except Exception as e:
            # ❌ 问题5：错误日志格式不统一
            self.logger.error(f"❌ 处理单个消息时发生异常: {e}", symbol=symbol, exc_info=True)
    
    async def _connect_websocket(self):
        """WebSocket连接 - 原始版本"""
        try:
            # ❌ 问题6：连接日志重复，没有去重
            self.logger.info("🚀 启动Binance WebSocket客户端")
            # 连接逻辑...
            self.logger.info("✅ Binance WebSocket连接成功")
            
        except Exception as e:
            # ❌ 问题7：错误处理不标准化
            self.logger.error(f"❌ Binance WebSocket连接失败: {e}")


# ============================================================================
# 迁移后：使用统一日志系统（解决所有问题）
# ============================================================================

from core.observability.logging.unified_log_manager import get_managed_logger
from core.observability.logging.unified_logger import ComponentType


class BinanceSpotManagerNew:
    """迁移后的Binance现货管理器 - 使用统一日志系统"""
    
    def __init__(self, symbols, config):
        # ✅ 改进1：使用统一日志管理器，格式自动标准化
        self.logger = get_managed_logger(
            component=ComponentType.ORDERBOOK_MANAGER,
            exchange="binance",
            market_type="spot"
        )
        
        # ✅ 改进2：使用标准化启动日志，自动处理emoji和格式
        self.logger.startup(
            "Binance spot orderbook manager initialized",
            symbols=symbols,
            config_loaded=True
        )
    
    async def _process_message(self, symbol: str, update: dict):
        """处理消息 - 改进版本"""
        try:
            # ✅ 改进3：数据处理日志自动优化级别和频率
            self.logger.data_processed(
                "Processing orderbook update",
                symbol=symbol,
                update_id=update.get('u'),
                first_update_id=update.get('U')
            )
            
            # 处理逻辑...
            await self._apply_update(symbol, update)
            
            # ✅ 改进4：成功日志自动去重和批量处理
            # 不需要显式记录每次成功，系统会自动聚合
            
        except Exception as e:
            # ✅ 改进5：标准化错误处理，自动分类和格式化
            self.logger.error(
                "Failed to process orderbook update",
                error=e,
                symbol=symbol,
                operation="message_processing"
            )
    
    async def _connect_websocket(self):
        """WebSocket连接 - 改进版本"""
        # ✅ 改进6：使用操作上下文管理器，自动记录开始/结束
        with self.logger.operation_context("websocket_connection"):
            try:
                # 连接逻辑...
                
                # ✅ 改进7：连接成功日志自动去重
                self.logger.connection_success(
                    "WebSocket connection established",
                    target="binance_spot",
                    url="wss://stream.binance.com:9443/ws"
                )
                
            except Exception as e:
                # ✅ 改进8：标准化连接错误处理
                self.logger.connection_failure(
                    "WebSocket connection failed",
                    error=e,
                    target="binance_spot"
                )
                raise
    
    async def _performance_monitoring(self):
        """性能监控 - 新增功能"""
        # ✅ 新功能：标准化性能指标记录
        metrics = {
            "messages_processed": self.stats.get('messages_processed', 0),
            "processing_rate": self.stats.get('processing_rate', 0.0),
            "error_rate": self.stats.get('error_rate', 0.0),
            "memory_usage_mb": self._get_memory_usage()
        }
        
        self.logger.performance(
            "Orderbook manager performance metrics",
            metrics=metrics
        )
    
    async def _health_check(self):
        """健康检查 - 新增功能"""
        # ✅ 新功能：智能健康检查日志
        is_healthy = (
            self.websocket_connected and
            self.error_rate < 0.05 and
            self.last_message_time > time.time() - 60
        )
        
        self.logger.health_check(
            "Orderbook manager health status",
            healthy=is_healthy,
            websocket_connected=self.websocket_connected,
            error_rate=self.error_rate,
            last_message_age=time.time() - self.last_message_time
        )


# ============================================================================
# 迁移工具和辅助函数
# ============================================================================

def migrate_existing_logger(old_logger, component: ComponentType, 
                          exchange: str = None, market_type: str = None):
    """迁移现有logger到统一系统的辅助函数"""
    
    # 创建新的托管logger
    new_logger = get_managed_logger(
        component=component,
        exchange=exchange,
        market_type=market_type
    )
    
    # 记录迁移事件
    new_logger.startup(
        "Logger migrated to unified logging system",
        old_logger_name=getattr(old_logger, 'name', 'unknown'),
        migration_time=time.time()
    )
    
    return new_logger


class LoggingMigrationHelper:
    """日志迁移助手类"""
    
    @staticmethod
    def convert_emoji_message(message: str) -> str:
        """转换emoji消息为标准格式"""
        emoji_mapping = {
            "🏭": "[INIT]",
            "🚀": "[START]", 
            "✅": "[SUCCESS]",
            "❌": "[ERROR]",
            "⚠️": "[WARNING]",
            "🔍": "[DEBUG]",
            "📊": "[DATA]",
            "🔧": "[CONFIG]",
            "💓": "[HEARTBEAT]",
            "🔌": "[CONNECTION]",
            "🛑": "[STOP]"
        }
        
        for emoji, replacement in emoji_mapping.items():
            message = message.replace(emoji, replacement)
        
        return message.strip()
    
    @staticmethod
    def extract_log_context(old_log_call: str) -> dict:
        """从旧的日志调用中提取上下文信息"""
        import re
        
        context = {}
        
        # 提取symbol
        symbol_match = re.search(r'symbol[=:][\s]*([A-Z]+)', old_log_call)
        if symbol_match:
            context['symbol'] = symbol_match.group(1)
        
        # 提取错误信息
        error_match = re.search(r'error[=:][\s]*([^,\}]+)', old_log_call)
        if error_match:
            context['error_info'] = error_match.group(1)
        
        return context
    
    @staticmethod
    def suggest_new_log_call(old_call: str, component: ComponentType) -> str:
        """建议新的日志调用方式"""
        
        # 分析旧调用
        if "启动" in old_call or "初始化" in old_call:
            return f"logger.startup('Component initialized', **context)"
        
        elif "连接成功" in old_call:
            return f"logger.connection_success('Connection established', **context)"
        
        elif "连接失败" in old_call:
            return f"logger.connection_failure('Connection failed', error=e, **context)"
        
        elif "处理完成" in old_call or "成功" in old_call:
            return f"logger.data_processed('Operation completed', **context)"
        
        elif "失败" in old_call or "异常" in old_call:
            return f"logger.error('Operation failed', error=e, **context)"
        
        elif "警告" in old_call:
            return f"logger.warning('Warning condition detected', **context)"
        
        else:
            return f"# TODO: Analyze and convert: {old_call}"


# ============================================================================
# 迁移验证和测试
# ============================================================================

async def test_logging_migration():
    """测试日志迁移效果"""
    
    # 创建新的logger
    logger = get_managed_logger(
        ComponentType.ORDERBOOK_MANAGER,
        exchange="binance",
        market_type="spot"
    )
    
    # 测试各种日志类型
    logger.startup("Test component started")
    
    logger.connection_success("Test connection established", target="test_server")
    
    for i in range(100):
        # 测试去重功能 - 这些重复日志会被自动处理
        logger.data_processed(f"Processing message {i}", message_id=i)
    
    logger.performance("Test performance metrics", {
        "processed_messages": 100,
        "processing_rate": 50.0,
        "error_count": 0
    })
    
    logger.health_check("System health check", healthy=True)
    
    try:
        raise ValueError("Test error")
    except Exception as e:
        logger.error("Test error handling", error=e)
    
    logger.shutdown("Test component stopped")
    
    # 获取统计信息
    stats = logger.get_local_statistics()
    print("Migration test statistics:", stats)


# ============================================================================
# 使用示例和最佳实践
# ============================================================================

class BestPracticesExample:
    """日志系统最佳实践示例"""
    
    def __init__(self):
        # ✅ 最佳实践1：在初始化时创建logger
        self.logger = get_managed_logger(
            ComponentType.ORDERBOOK_MANAGER,
            exchange="example",
            market_type="spot"
        )
    
    async def example_operation(self):
        """示例操作 - 展示最佳实践"""
        
        # ✅ 最佳实践2：使用操作上下文管理器
        with self.logger.operation_context("example_operation"):
            
            # ✅ 最佳实践3：记录关键业务事件
            self.logger.data_processed(
                "Starting data processing",
                batch_size=100,
                source="websocket"
            )
            
            # 模拟处理
            for i in range(100):
                # ✅ 最佳实践4：高频操作使用批量日志
                if i % 20 == 0:  # 每20次记录一次
                    self.logger.data_processed(
                        "Batch processing progress",
                        processed=i,
                        total=100,
                        progress_percent=i
                    )
            
            # ✅ 最佳实践5：记录性能指标
            self.logger.performance(
                "Operation completed",
                {
                    "total_processed": 100,
                    "duration_seconds": 2.5,
                    "throughput": 40.0
                }
            )


if __name__ == "__main__":
    import asyncio
    
    # 配置全局日志系统
    from core.observability.logging.unified_log_manager import configure_global_logging, LogConfiguration
    
    config = LogConfiguration(
        global_level="INFO",
        enable_performance_mode=True,
        enable_deduplication=True,
        use_emoji=False  # 生产环境建议关闭
    )
    
    configure_global_logging(config)
    
    # 运行测试
    asyncio.run(test_logging_migration())
