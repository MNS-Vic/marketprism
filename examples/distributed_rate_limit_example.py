"""
MarketPrism 分布式速率限制使用示例

这个示例展示了如何在MarketPrism项目中使用分布式速率限制系统，
解决多进程共享API速率限制的问题。

场景模拟：
1. 多个数据收集器进程
2. 监控服务
3. 交易服务
4. 分析服务

每个服务都需要调用交易所API，但必须共享总的速率限制。
"""

import asyncio
import logging
import time
import random
from typing import List, Dict, Any
import os
import sys

# 添加项目路径
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core.reliability.distributed_rate_limit_coordinator import (
    DistributedRateLimitCoordinator,
    ExchangeType,
    RequestType,
    RateLimitRequest,
    create_redis_coordinator,
    create_memory_coordinator
)

from core.reliability.distributed_rate_limit_adapter import (
    DistributedRateLimitAdapter,
    DistributedRateLimitConfig,
    acquire_api_permit,
    get_rate_limit_status,
    rate_limited
)

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


class MockExchangeAPI:
    """模拟交易所API"""
    
    def __init__(self, exchange: str):
        self.exchange = exchange
        self.request_count = 0
    
    @rate_limited("binance", "rest_public", weight=1)
    async def get_ticker(self, symbol: str) -> Dict[str, Any]:
        """获取价格信息"""
        self.request_count += 1
        # 模拟API响应时间
        await asyncio.sleep(random.uniform(0.1, 0.3))
        
        return {
            "symbol": symbol,
            "price": random.uniform(100, 50000),
            "timestamp": time.time(),
            "exchange": self.exchange
        }
    
    @rate_limited("binance", "rest_public", weight=5)
    async def get_orderbook(self, symbol: str) -> Dict[str, Any]:
        """获取订单簿（高权重请求）"""
        self.request_count += 1
        await asyncio.sleep(random.uniform(0.2, 0.5))
        
        return {
            "symbol": symbol,
            "bids": [[random.uniform(100, 1000), random.uniform(1, 10)] for _ in range(10)],
            "asks": [[random.uniform(100, 1000), random.uniform(1, 10)] for _ in range(10)],
            "timestamp": time.time(),
            "exchange": self.exchange
        }
    
    @rate_limited("binance", "order", weight=1)
    async def place_order(self, symbol: str, side: str, amount: float, price: float) -> Dict[str, Any]:
        """下单（订单请求）"""
        self.request_count += 1
        await asyncio.sleep(random.uniform(0.1, 0.2))
        
        return {
            "order_id": f"order_{int(time.time() * 1000000)}",
            "symbol": symbol,
            "side": side,
            "amount": amount,
            "price": price,
            "status": "filled",
            "timestamp": time.time(),
            "exchange": self.exchange
        }


class DataCollectorService:
    """数据收集服务"""
    
    def __init__(self, service_id: str, symbols: List[str], priority: int = 3):
        self.service_id = service_id
        self.symbols = symbols
        self.priority = priority
        self.api = MockExchangeAPI("binance")
        self.adapter = None
        self.collected_data = []
        self.stats = {
            "requests_made": 0,
            "requests_granted": 0,
            "requests_denied": 0,
            "data_collected": 0
        }
    
    async def initialize(self):
        """初始化服务"""
        config = DistributedRateLimitConfig(
            enabled=True,
            storage_type="memory",  # 在实际部署中应该使用Redis
            service_name=f"data_collector_{self.service_id}",
            priority=self.priority
        )
        
        self.adapter = DistributedRateLimitAdapter(config)
        await self.adapter.initialize()
        
        logger.info(f"数据收集服务 {self.service_id} 已初始化")
    
    async def collect_ticker_data(self):
        """收集价格数据"""
        while True:
            try:
                symbol = random.choice(self.symbols)
                
                # 直接使用API（已包含速率限制装饰器）
                self.stats["requests_made"] += 1
                
                try:
                    ticker_data = await self.api.get_ticker(symbol)
                    self.collected_data.append(ticker_data)
                    self.stats["requests_granted"] += 1
                    self.stats["data_collected"] += 1
                    
                    logger.info(f"[{self.service_id}] 收集到 {symbol} 价格: {ticker_data['price']:.2f}")
                    
                except Exception as e:
                    self.stats["requests_denied"] += 1
                    logger.warning(f"[{self.service_id}] 请求被限制: {e}")
                
                # 随机间隔
                await asyncio.sleep(random.uniform(1, 3))
                
            except Exception as e:
                logger.error(f"[{self.service_id}] 数据收集错误: {e}")
                await asyncio.sleep(5)
    
    async def collect_orderbook_data(self):
        """收集订单簿数据（较少频率，但权重更高）"""
        while True:
            try:
                symbol = random.choice(self.symbols)
                
                self.stats["requests_made"] += 1
                
                try:
                    orderbook_data = await self.api.get_orderbook(symbol)
                    self.collected_data.append(orderbook_data)
                    self.stats["requests_granted"] += 1
                    self.stats["data_collected"] += 1
                    
                    logger.info(f"[{self.service_id}] 收集到 {symbol} 订单簿数据")
                    
                except Exception as e:
                    self.stats["requests_denied"] += 1
                    logger.warning(f"[{self.service_id}] 订单簿请求被限制: {e}")
                
                # 订单簿数据收集频率较低
                await asyncio.sleep(random.uniform(5, 10))
                
            except Exception as e:
                logger.error(f"[{self.service_id}] 订单簿收集错误: {e}")
                await asyncio.sleep(10)
    
    async def run(self):
        """运行服务"""
        await self.initialize()
        
        # 并发执行数据收集任务
        tasks = [
            asyncio.create_task(self.collect_ticker_data()),
            asyncio.create_task(self.collect_orderbook_data())
        ]
        
        await asyncio.gather(*tasks, return_exceptions=True)
    
    async def get_stats(self) -> Dict[str, Any]:
        """获取统计信息"""
        if self.adapter:
            adapter_status = await self.adapter.get_status()
            return {
                "service_id": self.service_id,
                "service_stats": self.stats,
                "adapter_status": adapter_status["adapter_status"],
                "collected_data_count": len(self.collected_data)
            }
        return {"service_id": self.service_id, "service_stats": self.stats}


class TradingService:
    """交易服务"""
    
    def __init__(self, service_id: str, symbols: List[str]):
        self.service_id = service_id
        self.symbols = symbols
        self.api = MockExchangeAPI("binance")
        self.adapter = None
        self.orders = []
        self.stats = {
            "orders_attempted": 0,
            "orders_successful": 0,
            "orders_failed": 0
        }
    
    async def initialize(self):
        """初始化交易服务"""
        config = DistributedRateLimitConfig(
            enabled=True,
            storage_type="memory",
            service_name=f"trading_service_{self.service_id}",
            priority=10  # 交易服务最高优先级
        )
        
        self.adapter = DistributedRateLimitAdapter(config)
        await self.adapter.initialize()
        
        logger.info(f"交易服务 {self.service_id} 已初始化")
    
    async def execute_trades(self):
        """执行交易"""
        while True:
            try:
                symbol = random.choice(self.symbols)
                side = random.choice(["buy", "sell"])
                amount = random.uniform(0.001, 0.1)
                price = random.uniform(100, 50000)
                
                self.stats["orders_attempted"] += 1
                
                try:
                    order_result = await self.api.place_order(symbol, side, amount, price)
                    self.orders.append(order_result)
                    self.stats["orders_successful"] += 1
                    
                    logger.info(f"[{self.service_id}] 订单成功: {side} {amount} {symbol} @ {price}")
                    
                except Exception as e:
                    self.stats["orders_failed"] += 1
                    logger.warning(f"[{self.service_id}] 订单失败: {e}")
                
                # 交易间隔
                await asyncio.sleep(random.uniform(2, 8))
                
            except Exception as e:
                logger.error(f"[{self.service_id}] 交易执行错误: {e}")
                await asyncio.sleep(5)
    
    async def run(self):
        """运行交易服务"""
        await self.initialize()
        await self.execute_trades()
    
    async def get_stats(self) -> Dict[str, Any]:
        """获取统计信息"""
        if self.adapter:
            adapter_status = await self.adapter.get_status()
            return {
                "service_id": self.service_id,
                "service_stats": self.stats,
                "adapter_status": adapter_status["adapter_status"],
                "orders_count": len(self.orders)
            }
        return {"service_id": self.service_id, "service_stats": self.stats}


class MonitoringService:
    """监控服务"""
    
    def __init__(self):
        self.services: List[Any] = []
        self.adapter = None
    
    async def initialize(self):
        """初始化监控服务"""
        config = DistributedRateLimitConfig(
            enabled=True,
            storage_type="memory",
            service_name="monitoring_service",
            priority=5  # 中等优先级
        )
        
        self.adapter = DistributedRateLimitAdapter(config)
        await self.adapter.initialize()
        
        logger.info("监控服务已初始化")
    
    def register_service(self, service):
        """注册要监控的服务"""
        self.services.append(service)
    
    async def monitor_rate_limits(self):
        """监控速率限制状态"""
        while True:
            try:
                # 获取全局速率限制状态
                global_status = await get_rate_limit_status()
                
                # 打印系统状态
                print("\n" + "="*80)
                print("速率限制系统状态报告")
                print("="*80)
                
                if "coordinator_status" in global_status:
                    coord_status = global_status["coordinator_status"]
                    print(f"协调器状态:")
                    print(f"  - 总请求数: {coord_status.get('total_requests', 0)}")
                    print(f"  - 成功请求数: {coord_status.get('granted_requests', 0)}")
                    print(f"  - 拒绝请求数: {coord_status.get('denied_requests', 0)}")
                    print(f"  - 成功率: {coord_status.get('success_rate', 0):.2%}")
                    print(f"  - 运行时间: {coord_status.get('uptime_seconds', 0):.1f}秒")
                
                if "bucket_statuses" in global_status:
                    bucket_statuses = global_status["bucket_statuses"]
                    print(f"\n令牌桶状态:")
                    for exchange, exchange_buckets in bucket_statuses.items():
                        print(f"  {exchange.upper()}:")
                        for request_type, bucket_info in exchange_buckets.items():
                            utilization = bucket_info.get("utilization", 0)
                            current_tokens = bucket_info.get("current_tokens", 0)
                            capacity = bucket_info.get("capacity", 0)
                            print(f"    {request_type}: {utilization:.1%} 使用率 "
                                  f"({current_tokens:.0f}/{capacity} 令牌)")
                
                print(f"\n活跃客户端数: {global_status.get('active_clients', 0)}")
                
                # 获取各服务状态
                print(f"\n服务状态:")
                for service in self.services:
                    try:
                        service_stats = await service.get_stats()
                        service_id = service_stats["service_id"]
                        stats = service_stats["service_stats"]
                        
                        total_requests = stats.get("requests_made", 0) or stats.get("orders_attempted", 0)
                        successful = stats.get("requests_granted", 0) or stats.get("orders_successful", 0)
                        failed = stats.get("requests_denied", 0) or stats.get("orders_failed", 0)
                        
                        success_rate = successful / total_requests if total_requests > 0 else 0
                        
                        print(f"  {service_id}: {successful}/{total_requests} 成功 "
                              f"({success_rate:.1%}) [{failed} 失败]")
                    except Exception as e:
                        print(f"  {service.service_id}: 状态获取失败 - {e}")
                
                print("="*80)
                
                await asyncio.sleep(10)  # 每10秒报告一次
                
            except Exception as e:
                logger.error(f"监控错误: {e}")
                await asyncio.sleep(5)
    
    async def run(self):
        """运行监控服务"""
        await self.initialize()
        await self.monitor_rate_limits()


class SystemCoordinator:
    """系统协调器"""
    
    def __init__(self):
        self.data_collectors: List[DataCollectorService] = []
        self.trading_services: List[TradingService] = []
        self.monitoring_service = MonitoringService()
    
    async def setup_services(self):
        """设置所有服务"""
        symbols = ["BTCUSDT", "ETHUSDT", "ADAUSDT", "DOTUSDT", "LINKUSDT"]
        
        # 创建数据收集服务（不同优先级）
        for i in range(3):
            priority = [8, 6, 4][i]  # 递减优先级
            collector = DataCollectorService(
                service_id=f"collector_{i+1}",
                symbols=symbols[:3],  # 每个收集器监控部分符号
                priority=priority
            )
            self.data_collectors.append(collector)
            self.monitoring_service.register_service(collector)
        
        # 创建交易服务（最高优先级）
        for i in range(2):
            trading_service = TradingService(
                service_id=f"trader_{i+1}",
                symbols=symbols[:2]  # 交易服务关注主要符号
            )
            self.trading_services.append(trading_service)
            self.monitoring_service.register_service(trading_service)
        
        logger.info(f"系统设置完成: {len(self.data_collectors)} 个数据收集器, "
                   f"{len(self.trading_services)} 个交易服务")
    
    async def run_system(self, duration: int = 60):
        """运行整个系统"""
        logger.info(f"启动系统，运行 {duration} 秒...")
        
        # 启动所有服务
        tasks = []
        
        # 数据收集服务
        for collector in self.data_collectors:
            tasks.append(asyncio.create_task(collector.run()))
        
        # 交易服务
        for trader in self.trading_services:
            tasks.append(asyncio.create_task(trader.run()))
        
        # 监控服务
        tasks.append(asyncio.create_task(self.monitoring_service.run()))
        
        # 运行指定时间
        try:
            await asyncio.wait_for(
                asyncio.gather(*tasks, return_exceptions=True),
                timeout=duration
            )
        except asyncio.TimeoutError:
            logger.info("系统运行时间到达，正在停止...")
        finally:
            # 取消所有任务
            for task in tasks:
                task.cancel()
            
            # 等待任务清理
            await asyncio.gather(*tasks, return_exceptions=True)
    
    async def generate_final_report(self):
        """生成最终报告"""
        print("\n" + "="*80)
        print("最终系统报告")
        print("="*80)
        
        # 全局状态
        try:
            global_status = await get_rate_limit_status()
            
            if "coordinator_status" in global_status:
                coord_status = global_status["coordinator_status"]
                print(f"全局统计:")
                print(f"  - 总请求处理: {coord_status.get('total_requests', 0)}")
                print(f"  - 成功请求: {coord_status.get('granted_requests', 0)}")
                print(f"  - 拒绝请求: {coord_status.get('denied_requests', 0)}")
                print(f"  - 整体成功率: {coord_status.get('success_rate', 0):.2%}")
            
            print(f"\n令牌桶最终状态:")
            if "bucket_statuses" in global_status:
                bucket_statuses = global_status["bucket_statuses"]
                for exchange, exchange_buckets in bucket_statuses.items():
                    for request_type, bucket_info in exchange_buckets.items():
                        utilization = bucket_info.get("utilization", 0)
                        print(f"  {exchange} {request_type}: {utilization:.1%} 最终使用率")
            
        except Exception as e:
            print(f"无法获取全局状态: {e}")
        
        # 各服务详细统计
        print(f"\n服务详细统计:")
        
        # 数据收集服务
        print(f"\n数据收集服务:")
        total_data_collected = 0
        for collector in self.data_collectors:
            try:
                stats = await collector.get_stats()
                service_stats = stats["service_stats"]
                data_count = stats.get("collected_data_count", 0)
                total_data_collected += data_count
                
                success_rate = (service_stats.get("requests_granted", 0) / 
                               max(service_stats.get("requests_made", 1), 1))
                
                print(f"  {collector.service_id}:")
                print(f"    - 数据收集: {data_count} 条")
                print(f"    - 请求成功率: {success_rate:.1%}")
                print(f"    - 总请求: {service_stats.get('requests_made', 0)}")
                
            except Exception as e:
                print(f"  {collector.service_id}: 统计获取失败 - {e}")
        
        # 交易服务
        print(f"\n交易服务:")
        total_orders = 0
        for trader in self.trading_services:
            try:
                stats = await trader.get_stats()
                service_stats = stats["service_stats"]
                orders_count = stats.get("orders_count", 0)
                total_orders += orders_count
                
                success_rate = (service_stats.get("orders_successful", 0) / 
                               max(service_stats.get("orders_attempted", 1), 1))
                
                print(f"  {trader.service_id}:")
                print(f"    - 完成订单: {orders_count} 个")
                print(f"    - 订单成功率: {success_rate:.1%}")
                print(f"    - 尝试订单: {service_stats.get('orders_attempted', 0)}")
                
            except Exception as e:
                print(f"  {trader.service_id}: 统计获取失败 - {e}")
        
        print(f"\n系统总结:")
        print(f"  - 总数据收集量: {total_data_collected} 条")
        print(f"  - 总订单处理量: {total_orders} 个")
        print(f"  - 活跃服务数: {len(self.data_collectors) + len(self.trading_services)}")
        
        print("="*80)


async def main():
    """主函数"""
    print("MarketPrism 分布式速率限制系统演示")
    print("="*80)
    print("这个演示展示了多个服务如何共享API速率限制：")
    print("- 3个数据收集服务（不同优先级）")
    print("- 2个交易服务（最高优先级）")
    print("- 1个监控服务")
    print("- 所有服务共享 Binance API 速率限制")
    print("="*80)
    
    # 创建系统协调器
    coordinator = SystemCoordinator()
    
    # 设置服务
    await coordinator.setup_services()
    
    # 运行系统
    print("\n启动系统运行...")
    await coordinator.run_system(duration=30)  # 运行30秒
    
    # 生成最终报告
    await coordinator.generate_final_report()
    
    print("\n演示完成！")


if __name__ == "__main__":
    # 运行演示
    asyncio.run(main())