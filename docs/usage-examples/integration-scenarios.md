# MarketPrism API代理集成场景实例

## 🔄 与现有系统集成

### **场景1: Python Collector集成**
```python
# services/python-collector/src/marketprism_collector/exchanges/binance_collector.py

from core.networking.proxy_adapter import use_api_proxy
import asyncio
import logging

logger = logging.getLogger(__name__)

class BinanceCollector:
    """Binance数据收集器 - 集成API代理"""
    
    def __init__(self, symbols=None):
        self.symbols = symbols or ["BTCUSDT", "ETHUSDT", "BNBUSDT"]
        self.data_buffer = []
    
    @use_api_proxy("binance")
    async def collect_ticker_data(self, session):
        """收集行情数据 - 使用代理保护"""
        try:
            # 批量获取所有交易对的24h行情
            if len(self.symbols) == 1:
                # 单个交易对
                params = {"symbol": self.symbols[0]}
                async with session.get("/api/v3/ticker/24hr", params=params) as response:
                    data = await response.json()
                    return [data] if isinstance(data, dict) else data
            else:
                # 多个交易对 - 自动使用优化的批量请求
                async with session.get("/api/v3/ticker/24hr") as response:
                    all_tickers = await response.json()
                    # 过滤出我们需要的交易对
                    return [ticker for ticker in all_tickers if ticker['symbol'] in self.symbols]
        
        except Exception as e:
            logger.error(f"收集Binance行情数据失败: {e}")
            raise
    
    @use_api_proxy("binance")
    async def collect_depth_data(self, session, symbol, limit=100):
        """收集深度数据"""
        params = {"symbol": symbol, "limit": limit}
        async with session.get("/api/v3/depth", params=params) as response:
            return await response.json()
    
    @use_api_proxy("binance")
    async def collect_kline_data(self, session, symbol, interval="1m", limit=500):
        """收集K线数据"""
        params = {
            "symbol": symbol,
            "interval": interval,
            "limit": limit
        }
        async with session.get("/api/v3/klines", params=params) as response:
            return await response.json()
    
    async def run_collection_cycle(self):
        """运行一个完整的数据收集周期"""
        try:
            # 并发收集多种数据
            tasks = [
                self.collect_ticker_data(),
                *[self.collect_depth_data(symbol, 50) for symbol in self.symbols[:3]],  # 限制深度数据数量
                *[self.collect_kline_data(symbol, "1m", 100) for symbol in self.symbols[:2]]  # 限制K线数据数量
            ]
            
            results = await asyncio.gather(*tasks, return_exceptions=True)
            
            # 处理结果
            ticker_data = results[0] if not isinstance(results[0], Exception) else []
            depth_data = [r for r in results[1:4] if not isinstance(r, Exception)]
            kline_data = [r for r in results[4:] if not isinstance(r, Exception)]
            
            logger.info(f"收集完成: {len(ticker_data)}个行情, {len(depth_data)}个深度, {len(kline_data)}个K线")
            
            return {
                "ticker": ticker_data,
                "depth": depth_data,
                "klines": kline_data
            }
            
        except Exception as e:
            logger.error(f"数据收集周期失败: {e}")
            return {"ticker": [], "depth": [], "klines": []}

# 使用示例
async def collector_integration_example():
    """演示与Python Collector的集成"""
    collector = BinanceCollector(["BTCUSDT", "ETHUSDT", "BNBUSDT", "ADAUSDT"])
    
    # 运行10个收集周期
    for cycle in range(10):
        print(f"\n🔄 执行第{cycle + 1}个收集周期...")
        
        start_time = time.time()
        data = await collector.run_collection_cycle()
        elapsed = time.time() - start_time
        
        print(f"✅ 周期{cycle + 1}完成: 耗时{elapsed:.3f}s")
        print(f"   行情数据: {len(data['ticker'])}条")
        print(f"   深度数据: {len(data['depth'])}条")
        print(f"   K线数据: {len(data['klines'])}条")
        
        # 等待下一个周期
        await asyncio.sleep(30)  # 30秒间隔
```

### **场景2: 监控服务集成**
```python
# core/monitoring/components/exchange_monitor.py

from core.networking.exchange_api_proxy import get_exchange_proxy
from core.storage.unified_clickhouse_writer import UnifiedClickHouseWriter
import asyncio
import json
from datetime import datetime

class ExchangeMonitor:
    """交易所监控服务 - 集成API代理"""
    
    def __init__(self):
        self.proxy = get_exchange_proxy()
        self.clickhouse_writer = UnifiedClickHouseWriter()
        self.monitoring_data = []
    
    async def monitor_exchange_health(self):
        """监控交易所健康状态"""
        exchanges = ["binance", "okx", "deribit"]
        health_endpoints = {
            "binance": "/api/v3/ping",
            "okx": "/api/v5/public/time", 
            "deribit": "/api/v2/public/get_time"
        }
        
        while True:
            try:
                health_data = []
                
                # 并发检查所有交易所健康状态
                tasks = [
                    self.check_single_exchange_health(exchange, health_endpoints[exchange])
                    for exchange in exchanges
                ]
                
                results = await asyncio.gather(*tasks, return_exceptions=True)
                
                for exchange, result in zip(exchanges, results):
                    if isinstance(result, Exception):
                        health_status = {
                            "exchange": exchange,
                            "status": "error",
                            "error": str(result),
                            "response_time": None,
                            "timestamp": datetime.now()
                        }
                    else:
                        health_status = result
                    
                    health_data.append(health_status)
                    print(f"🏥 {exchange}: {health_status['status']} "
                          f"({health_status.get('response_time', 'N/A')}ms)")
                
                # 存储监控数据
                await self.store_monitoring_data(health_data)
                
                # 检查代理自身健康状态
                await self.check_proxy_health()
                
                await asyncio.sleep(60)  # 1分钟检查间隔
                
            except Exception as e:
                print(f"监控服务错误: {e}")
                await asyncio.sleep(300)  # 错误时等待5分钟
    
    async def check_single_exchange_health(self, exchange, endpoint):
        """检查单个交易所健康状态"""
        start_time = time.time()
        
        try:
            result = await self.proxy.request(exchange, "GET", endpoint)
            response_time = (time.time() - start_time) * 1000  # 转换为毫秒
            
            return {
                "exchange": exchange,
                "status": "healthy",
                "response_time": round(response_time, 2),
                "server_time": result.get("serverTime") or result.get("data", {}).get("time"),
                "timestamp": datetime.now()
            }
            
        except Exception as e:
            response_time = (time.time() - start_time) * 1000
            
            return {
                "exchange": exchange,
                "status": "unhealthy",
                "error": str(e),
                "response_time": round(response_time, 2),
                "timestamp": datetime.now()
            }
    
    async def check_proxy_health(self):
        """检查代理自身健康状态"""
        status = self.proxy.get_status()
        health = self.proxy.get_health_report()
        
        print(f"\n📊 API代理状态:")
        print(f"   模式: {status['mode']}")
        print(f"   可用IP: {status['available_ips']}/{status['total_ips']}")
        print(f"   成功率: {status['recent_success_rate']}")
        print(f"   系统健康: {health['overall_health']}")
        
        # 如果有警告，记录到监控系统
        if health['recommendations'] and health['overall_health'] != 'healthy':
            await self.alert_proxy_issues(health)
    
    async def store_monitoring_data(self, health_data):
        """存储监控数据到ClickHouse"""
        try:
            for data in health_data:
                await self.clickhouse_writer.write_data("exchange_health", {
                    "timestamp": data["timestamp"],
                    "exchange": data["exchange"],
                    "status": data["status"],
                    "response_time": data.get("response_time"),
                    "error": data.get("error", ""),
                    "server_time": data.get("server_time")
                })
        except Exception as e:
            print(f"存储监控数据失败: {e}")
    
    async def alert_proxy_issues(self, health_report):
        """API代理问题告警"""
        print(f"\n🚨 API代理健康警告:")
        for recommendation in health_report['recommendations']:
            print(f"   • {recommendation}")

# 使用示例
async def monitoring_integration_example():
    """演示与监控服务的集成"""
    monitor = ExchangeMonitor()
    await monitor.monitor_exchange_health()
```

### **场景3: 数据归档服务集成**
```python
# services/data_archiver/archive_manager.py

from core.networking.proxy_adapter import get_proxy_session
import asyncio
import json
from datetime import datetime, timedelta

class DataArchiveManager:
    """数据归档管理器 - 集成API代理"""
    
    def __init__(self):
        self.archive_tasks = []
    
    async def archive_historical_data(self, exchange, symbol, start_date, end_date):
        """归档历史数据"""
        proxy_session = get_proxy_session(exchange)
        
        try:
            async with proxy_session as session:
                # 按天分批归档，避免单次请求量过大
                current_date = start_date
                archived_data = []
                
                while current_date <= end_date:
                    try:
                        # 获取当天的K线数据
                        start_timestamp = int(current_date.timestamp() * 1000)
                        end_timestamp = int((current_date + timedelta(days=1)).timestamp() * 1000)
                        
                        if exchange == "binance":
                            params = {
                                "symbol": symbol,
                                "interval": "1h",
                                "startTime": start_timestamp,
                                "endTime": end_timestamp,
                                "limit": 1000
                            }
                            async with session.get("/api/v3/klines", params=params) as response:
                                daily_data = await response.json()
                        
                        elif exchange == "okx":
                            params = {
                                "instId": symbol.replace("USDT", "-USDT"),
                                "bar": "1H",
                                "after": start_timestamp,
                                "before": end_timestamp,
                                "limit": 100
                            }
                            async with session.get("/api/v5/market/history-candles", params=params) as response:
                                result = await response.json()
                                daily_data = result.get("data", [])
                        
                        if daily_data:
                            archived_data.extend(daily_data)
                            print(f"✅ 归档 {exchange} {symbol} {current_date.strftime('%Y-%m-%d')}: {len(daily_data)}条")
                        else:
                            print(f"⚠️ 无数据 {exchange} {symbol} {current_date.strftime('%Y-%m-%d')}")
                        
                        # 避免请求过于频繁
                        await asyncio.sleep(1)
                        
                    except Exception as e:
                        print(f"❌ 归档失败 {exchange} {symbol} {current_date.strftime('%Y-%m-%d')}: {e}")
                    
                    current_date += timedelta(days=1)
                
                print(f"🎉 {exchange} {symbol} 归档完成: 总计{len(archived_data)}条数据")
                return archived_data
                
        except Exception as e:
            print(f"归档任务失败: {e}")
            return []
        
        finally:
            await proxy_session.close()
    
    async def batch_archive_multiple_symbols(self, exchange, symbols, days=30):
        """批量归档多个交易对"""
        end_date = datetime.now()
        start_date = end_date - timedelta(days=days)
        
        # 并发归档，但限制并发数避免过载
        semaphore = asyncio.Semaphore(3)  # 最多3个并发任务
        
        async def archive_single_symbol(symbol):
            async with semaphore:
                return await self.archive_historical_data(exchange, symbol, start_date, end_date)
        
        # 创建所有归档任务
        tasks = [archive_single_symbol(symbol) for symbol in symbols]
        
        # 执行所有任务
        print(f"🚀 开始批量归档 {exchange} {len(symbols)}个交易对，最近{days}天数据...")
        results = await asyncio.gather(*tasks, return_exceptions=True)
        
        # 统计结果
        total_archived = 0
        success_count = 0
        
        for symbol, result in zip(symbols, results):
            if isinstance(result, Exception):
                print(f"❌ {symbol} 归档失败: {result}")
            else:
                total_archived += len(result)
                success_count += 1
        
        print(f"📊 批量归档完成:")
        print(f"   成功: {success_count}/{len(symbols)} 个交易对")
        print(f"   总数据量: {total_archived} 条记录")

# 使用示例
async def archive_integration_example():
    """演示与数据归档服务的集成"""
    archive_manager = DataArchiveManager()
    
    # 归档主要交易对的历史数据
    major_symbols = ["BTCUSDT", "ETHUSDT", "BNBUSDT", "ADAUSDT", "DOTUSDT"]
    
    await archive_manager.batch_archive_multiple_symbols("binance", major_symbols, days=7)
```

## 🔧 配置管理集成

### **场景4: 环境配置自动适配**
```python
# config/environments/production.py

import os
from core.networking.exchange_api_proxy import ExchangeAPIProxy, ProxyMode

class ProductionProxyConfig:
    """生产环境API代理配置"""
    
    @staticmethod
    def setup_production_proxy():
        """设置生产环境代理"""
        # 从环境变量读取配置
        proxy_mode = os.getenv("PROXY_MODE", "auto")
        ip_list = os.getenv("PROXY_IPS", "").split(",") if os.getenv("PROXY_IPS") else []
        
        if proxy_mode == "distributed" and ip_list:
            # 分布式部署
            proxy = ExchangeAPIProxy.distributed_mode([ip.strip() for ip in ip_list if ip.strip()])
            print(f"🌐 生产环境: 分布式代理模式，{len(ip_list)}个IP")
            
        elif proxy_mode == "unified":
            # 统一代理
            main_ip = os.getenv("MAIN_IP")
            proxy = ExchangeAPIProxy.unified_mode(main_ip)
            print(f"🔗 生产环境: 统一代理模式，IP: {main_ip}")
            
        else:
            # 自动检测
            proxy = ExchangeAPIProxy.auto_configure()
            print(f"🤖 生产环境: 自动配置模式")
        
        return proxy
    
    @staticmethod
    def setup_monitoring_alerts():
        """设置生产环境监控告警"""
        return {
            "error_rate_threshold": 0.05,      # 5%错误率告警
            "response_time_threshold": 3.0,    # 3秒响应时间告警
            "weight_usage_threshold": 0.85,    # 85%权重使用率告警
            "ip_availability_threshold": 0.7   # 70%IP可用性告警
        }

# config/environments/development.py

class DevelopmentProxyConfig:
    """开发环境API代理配置"""
    
    @staticmethod
    def setup_development_proxy():
        """设置开发环境代理"""
        # 开发环境使用简单配置
        proxy = ExchangeAPIProxy.unified_mode()  # 单IP模式
        print(f"🔧 开发环境: 统一代理模式（本地IP）")
        return proxy
    
    @staticmethod
    def setup_test_mode():
        """设置测试模式"""
        return {
            "enable_mock_responses": True,
            "simulate_rate_limits": False,
            "log_all_requests": True
        }

# 使用示例
def environment_config_example():
    """环境配置示例"""
    env = os.getenv("ENVIRONMENT", "development")
    
    if env == "production":
        proxy = ProductionProxyConfig.setup_production_proxy()
        alerts = ProductionProxyConfig.setup_monitoring_alerts()
    else:
        proxy = DevelopmentProxyConfig.setup_development_proxy()
        alerts = {"error_rate_threshold": 0.2}  # 开发环境更宽松
    
    print(f"✅ {env}环境代理配置完成")
    return proxy, alerts
```

### **场景5: Docker容器化部署集成**
```python
# docker/proxy_entrypoint.py

#!/usr/bin/env python3
"""
Docker容器化部署入口脚本
自动配置API代理并启动服务
"""

import os
import sys
import asyncio
import signal
from core.networking.exchange_api_proxy import ExchangeAPIProxy

class DockerizedProxyService:
    def __init__(self):
        self.proxy = None
        self.running = True
    
    def setup_proxy_from_env(self):
        """从环境变量设置代理配置"""
        # 读取Docker环境变量
        service_name = os.getenv("SERVICE_NAME", "unknown")
        proxy_mode = os.getenv("PROXY_MODE", "auto")
        
        # 从Docker network获取其他服务IP
        ip_prefix = os.getenv("IP_PREFIX", "172.20.0")
        proxy_ips = []
        
        # 自动发现集群中的其他代理节点
        for i in range(10, 20):  # 检查172.20.0.10-19
            ip = f"{ip_prefix}.{i}"
            if ip != os.getenv("MY_IP"):  # 排除自己
                # 这里可以加入健康检查逻辑
                proxy_ips.append(ip)
        
        if proxy_mode == "distributed" and proxy_ips:
            self.proxy = ExchangeAPIProxy.distributed_mode(proxy_ips)
            print(f"🐳 Docker: {service_name} 分布式代理启动，{len(proxy_ips)}个节点")
        else:
            self.proxy = ExchangeAPIProxy.auto_configure()
            print(f"🐳 Docker: {service_name} 自动配置代理启动")
    
    def setup_signal_handlers(self):
        """设置信号处理器"""
        def signal_handler(signum, frame):
            print(f"\n🛑 接收到信号 {signum}，开始优雅关闭...")
            self.running = False
        
        signal.signal(signal.SIGTERM, signal_handler)
        signal.signal(signal.SIGINT, signal_handler)
    
    async def health_check_endpoint(self):
        """Docker健康检查端点"""
        from aiohttp import web
        
        async def health_check(request):
            """健康检查处理器"""
            try:
                status = self.proxy.get_status()
                health = self.proxy.get_health_report()
                
                if health['overall_health'] == 'healthy':
                    return web.json_response({
                        "status": "healthy",
                        "proxy_mode": status['mode'],
                        "available_ips": status['available_ips'],
                        "total_ips": status['total_ips']
                    })
                else:
                    return web.json_response({
                        "status": "unhealthy",
                        "issues": health['recommendations']
                    }, status=503)
                    
            except Exception as e:
                return web.json_response({
                    "status": "error",
                    "error": str(e)
                }, status=500)
        
        app = web.Application()
        app.router.add_get('/health', health_check)
        
        runner = web.AppRunner(app)
        await runner.setup()
        
        site = web.TCPSite(runner, '0.0.0.0', 8080)
        await site.start()
        print("🩺 健康检查端点启动: http://0.0.0.0:8080/health")
    
    async def run_service(self):
        """运行主服务"""
        # 启动健康检查端点
        await self.health_check_endpoint()
        
        # 主服务循环
        while self.running:
            try:
                # 定期报告状态
                status = self.proxy.get_status()
                print(f"📊 服务运行中: 成功率{status['recent_success_rate']}, "
                      f"可用IP{status['available_ips']}/{status['total_ips']}")
                
                await asyncio.sleep(30)  # 30秒报告间隔
                
            except Exception as e:
                print(f"服务运行错误: {e}")
                await asyncio.sleep(60)
        
        print("✅ 服务优雅关闭完成")

def main():
    """Docker容器主入口"""
    service = DockerizedProxyService()
    
    # 设置信号处理
    service.setup_signal_handlers()
    
    # 配置代理
    service.setup_proxy_from_env()
    
    # 运行服务
    try:
        asyncio.run(service.run_service())
    except KeyboardInterrupt:
        print("服务被中断")
    finally:
        print("容器退出")

if __name__ == "__main__":
    main()
```

### **对应的Docker配置文件**
```yaml
# docker-compose.yml

version: '3.8'

services:
  marketprism-collector-1:
    build: 
      context: .
      dockerfile: docker/Dockerfile.collector
    environment:
      - SERVICE_NAME=collector-1
      - PROXY_MODE=distributed
      - MY_IP=172.20.0.10
      - IP_PREFIX=172.20.0
    networks:
      marketprism_net:
        ipv4_address: 172.20.0.10
    healthcheck:
      test: ["CMD", "curl", "-f", "http://localhost:8080/health"]
      interval: 30s
      timeout: 10s
      retries: 3
  
  marketprism-collector-2:
    build: 
      context: .
      dockerfile: docker/Dockerfile.collector
    environment:
      - SERVICE_NAME=collector-2
      - PROXY_MODE=distributed
      - MY_IP=172.20.0.11
      - IP_PREFIX=172.20.0
    networks:
      marketprism_net:
        ipv4_address: 172.20.0.11
    healthcheck:
      test: ["CMD", "curl", "-f", "http://localhost:8080/health"]
      interval: 30s
      timeout: 10s
      retries: 3

networks:
  marketprism_net:
    driver: bridge
    ipam:
      config:
        - subnet: 172.20.0.0/16
```

这些集成场景展示了MarketPrism统一API代理如何无缝集成到现有系统架构中，从简单的函数装饰器到复杂的Docker容器化部署，都能提供一致的速率限制保护和IP管理功能！