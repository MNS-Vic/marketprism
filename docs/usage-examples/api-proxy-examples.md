# MarketPrism API代理使用实例大全

## 🚀 快速开始实例

### **1. 最简单的使用方式**
```python
# 一行代码解决所有问题
from core.networking.exchange_api_proxy import proxy_request

async def simple_example():
    # 自动处理权重、IP选择、错误重试
    result = await proxy_request("binance", "GET", "/api/v3/ticker/24hr", {"symbol": "BTCUSDT"})
    print(f"BTC价格: {result['lastPrice']} USDT")
    print(f"24h涨跌: {result['priceChangePercent']}%")
```

### **2. 批量数据获取**
```python
import asyncio
from core.networking.exchange_api_proxy import get_exchange_proxy

async def batch_ticker_example():
    proxy = get_exchange_proxy()
    
    # 并发获取多个交易对数据，自动分配到最佳IP
    symbols = ["BTCUSDT", "ETHUSDT", "BNBUSDT", "ADAUSDT", "DOTUSDT"]  # 原始格式
    
    tasks = [
        proxy.request("binance", "GET", "/api/v3/ticker/24hr", {"symbol": symbol})
        for symbol in symbols
    ]
    
    results = await asyncio.gather(*tasks, return_exceptions=True)
    
    for symbol, result in zip(symbols, results):
        if isinstance(result, Exception):
            print(f"❌ {symbol}: 获取失败 - {result}")
        else:
            print(f"✅ {symbol}: {result['lastPrice']} USDT ({result['priceChangePercent']}%)")
```

## 🎯 装饰器集成实例

### **3. 现有函数无缝集成**
```python
from core.networking.proxy_adapter import use_api_proxy

@use_api_proxy("binance")
async def get_order_book(session, symbol, limit=100):
    """获取订单簿数据 - 现有代码完全不变"""
    params = {"symbol": symbol, "limit": limit}
    async with session.get("/api/v3/depth", params=params) as response:
        return await response.json()

@use_api_proxy("okx")
async def get_okx_instruments(session):
    """获取OKX交易对信息"""
    async with session.get("/api/v5/public/instruments", params={"instType": "SPOT"}) as response:
        return await response.json()

# 使用示例
async def decorator_example():
    # 直接调用，代理自动处理所有复杂逻辑
    btc_book = await get_order_book("BTCUSDT", 50)
    print(f"BTC买一价: {btc_book['bids'][0][0]}")
    
    okx_instruments = await get_okx_instruments()
    print(f"OKX现货交易对数量: {len(okx_instruments['data'])}")
```

### **4. 类方法集成**
```python
class CryptoDataCollector:
    def __init__(self):
        self.collected_data = []
    
    @use_api_proxy("binance")
    async def collect_kline_data(self, session, symbol, interval="1h", limit=100):
        """收集K线数据"""
        params = {
            "symbol": symbol,
            "interval": interval,
            "limit": limit
        }
        async with session.get("/api/v3/klines", params=params) as response:
            klines = await response.json()
            return [{
                "timestamp": k[0],
                "open": float(k[1]),
                "high": float(k[2]),
                "low": float(k[3]),
                "close": float(k[4]),
                "volume": float(k[5])
            } for k in klines]
    
    @use_api_proxy("binance")
    async def collect_trade_data(self, session, symbol, limit=500):
        """收集最近交易数据"""
        params = {"symbol": symbol, "limit": limit}
        async with session.get("/api/v3/trades", params=params) as response:
            return await response.json()

# 使用示例
async def class_method_example():
    collector = CryptoDataCollector()
    
    # 所有方法自动享受代理保护
    btc_klines = await collector.collect_kline_data("BTCUSDT", "1h", 24)
    eth_trades = await collector.collect_trade_data("ETHUSDT", 100)
    
    print(f"BTC 24小时K线数据: {len(btc_klines)}条")
    print(f"ETH 最近交易数据: {len(eth_trades)}条")
```

## 🌐 全局代理实例

### **5. 零侵入全局代理**
```python
from core.networking.proxy_adapter import enable_global_proxy, disable_global_proxy
import aiohttp

async def global_proxy_example():
    # 启用全局代理 - 现有所有aiohttp代码自动受保护
    enable_global_proxy()
    
    try:
        # 现有代码完全不用修改！
        async with aiohttp.ClientSession(base_url="https://api.binance.com") as session:
            # 这些请求会自动通过统一代理
            async with session.get("/api/v3/exchangeInfo") as response:
                exchange_info = await response.json()
                symbols = [s['symbol'] for s in exchange_info['symbols'] if s['status'] == 'TRADING']
                print(f"Binance活跃交易对: {len(symbols)}个")
            
            # 批量请求也会自动负载均衡
            tasks = [
                session.get(f"/api/v3/ticker/price?symbol={symbol}")
                for symbol in symbols[:10]  # 前10个交易对
            ]
            
            responses = await asyncio.gather(*tasks)
            prices = []
            for response in responses:
                data = await response.json()
                prices.append(data)
            
            print(f"获取到{len(prices)}个交易对价格")
            
    finally:
        # 恢复原始行为
        disable_global_proxy()
```

## 🏢 企业级分布式实例

### **6. 多服务器分布式部署**
```python
from core.networking.exchange_api_proxy import ExchangeAPIProxy, ProxyMode

async def distributed_deployment_example():
    # 配置多IP分布式代理
    server_ips = [
        "10.0.1.100",  # 主服务器
        "10.0.2.100",  # 备用服务器1  
        "10.0.3.100",  # 备用服务器2
        "10.0.4.100"   # 高频交易专用
    ]
    
    proxy = ExchangeAPIProxy.distributed_mode(server_ips)
    
    # 高频数据收集任务
    async def high_frequency_collection():
        symbols = ["BTCUSDT", "ETHUSDT", "BNBUSDT", "ADAUSDT", "DOTUSDT", 
                  "LINKUSDT", "XRPUSDT", "LTCUSDT", "BCHUSDT", "EOSUSDT"]
        
        while True:
            try:
                # 并发收集所有交易对的实时价格
                tasks = [
                    proxy.request("binance", "GET", "/api/v3/ticker/price", {"symbol": symbol})
                    for symbol in symbols
                ]
                
                start_time = time.time()
                results = await asyncio.gather(*tasks, return_exceptions=True)
                elapsed = time.time() - start_time
                
                success_count = len([r for r in results if not isinstance(r, Exception)])
                print(f"收集完成: {success_count}/{len(symbols)} 成功, 耗时: {elapsed:.3f}s")
                
                # 检查代理状态
                status = proxy.get_status()
                print(f"可用IP: {status['available_ips']}/{status['total_ips']}, "
                      f"成功率: {status['recent_success_rate']}")
                
                await asyncio.sleep(1)  # 1秒间隔
                
            except Exception as e:
                print(f"高频收集错误: {e}")
                await asyncio.sleep(5)  # 错误时等待5秒
    
    # 启动高频收集
    await high_frequency_collection()
```

### **7. 多交易所套利监控**
```python
class ArbitrageMonitor:
    def __init__(self):
        self.proxy = ExchangeAPIProxy.auto_configure()
        self.price_data = {}
    
    async def monitor_arbitrage_opportunities(self):
        """监控套利机会"""
        trading_pairs = ["BTCUSDT", "ETHUSDT", "BNBUSDT"]
        exchanges = ["binance", "okx"]
        
        while True:
            try:
                # 并发获取所有交易所价格
                tasks = []
                for exchange in exchanges:
                    for pair in trading_pairs:
                        if exchange == "binance":
                            endpoint = "/api/v3/ticker/price"
                            params = {"symbol": pair}
                        else:  # okx
                            endpoint = "/api/v5/market/ticker"
                            params = {"instId": pair.replace("USDT", "-USDT")}
                        
                        tasks.append(self.proxy.request(exchange, "GET", endpoint, params))
                
                results = await asyncio.gather(*tasks, return_exceptions=True)
                
                # 解析价格数据
                idx = 0
                for exchange in exchanges:
                    for pair in trading_pairs:
                        if idx < len(results) and not isinstance(results[idx], Exception):
                            result = results[idx]
                            
                            if exchange == "binance":
                                price = float(result['price'])
                            else:  # okx
                                price = float(result['data'][0]['last'])
                            
                            key = f"{exchange}_{pair}"
                            self.price_data[key] = price
                        
                        idx += 1
                
                # 计算套利机会
                self.calculate_arbitrage()
                
                await asyncio.sleep(2)  # 2秒更新间隔
                
            except Exception as e:
                print(f"套利监控错误: {e}")
                await asyncio.sleep(10)
    
    def calculate_arbitrage(self):
        """计算套利机会"""
        for pair in ["BTCUSDT", "ETHUSDT", "BNBUSDT"]:
            binance_key = f"binance_{pair}"
            okx_key = f"okx_{pair}"
            
            if binance_key in self.price_data and okx_key in self.price_data:
                binance_price = self.price_data[binance_key]
                okx_price = self.price_data[okx_key]
                
                # 计算价差百分比
                if okx_price > 0:
                    diff_pct = (binance_price - okx_price) / okx_price * 100
                    
                    if abs(diff_pct) > 0.1:  # 价差超过0.1%
                        direction = "Binance→OKX" if diff_pct > 0 else "OKX→Binance"
                        print(f"🔥 套利机会 {pair}: {direction}, 价差: {abs(diff_pct):.3f}%")

# 使用示例
async def arbitrage_example():
    monitor = ArbitrageMonitor()
    await monitor.monitor_arbitrage_opportunities()
```

## 📊 监控和诊断实例

### **8. 实时监控面板**
```python
import json
from datetime import datetime

class ProxyMonitoringDashboard:
    def __init__(self):
        self.proxy = get_exchange_proxy()
    
    async def display_realtime_status(self):
        """显示实时状态面板"""
        while True:
            try:
                # 获取状态数据
                status = self.proxy.get_status()
                health = self.proxy.get_health_report()
                
                # 清屏并显示面板
                print("\033[2J\033[H")  # 清屏
                print("=" * 80)
                print(f"📊 MarketPrism API代理监控面板 - {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
                print("=" * 80)
                
                # 基础状态
                print(f"🔧 运行模式: {status['mode']}")
                print(f"🌐 IP资源: {status['available_ips']}/{status['total_ips']} 可用")
                print(f"📈 成功率: {status['recent_success_rate']}")
                print(f"⚡ 总权重消耗: {status['total_weight_consumed']}")
                print(f"🏥 系统健康: {health['overall_health']}")
                
                # IP详情
                print("\n🌐 IP资源详情:")
                for ip, details in status['ip_details'].items():
                    status_emoji = "✅" if details['available'] else "❌"
                    print(f"  {status_emoji} {ip}: {details['weight_usage']} 权重, "
                          f"健康分数: {details['health_score']}")
                
                # 统计信息
                stats = status['statistics']
                print(f"\n📊 请求统计:")
                print(f"  总请求: {stats['total_requests']}")
                print(f"  成功: {stats['successful_requests']}")
                print(f"  失败: {stats['failed_requests']}")
                print(f"  限流: {stats['rate_limited_requests']}")
                print(f"  平均响应时间: {stats['average_response_time']:.3f}s")
                
                # 优化建议
                if health['recommendations']:
                    print(f"\n💡 优化建议:")
                    for rec in health['recommendations'][:3]:
                        print(f"  • {rec}")
                
                await asyncio.sleep(5)  # 5秒刷新
                
            except Exception as e:
                print(f"监控面板错误: {e}")
                await asyncio.sleep(10)

# 使用示例
async def monitoring_example():
    dashboard = ProxyMonitoringDashboard()
    await dashboard.display_realtime_status()
```

这些实例展示了MarketPrism统一API代理的强大功能和灵活性，从简单的一行代码使用到复杂的企业级分布式部署，都能优雅地处理！