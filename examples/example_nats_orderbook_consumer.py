#!/usr/bin/env python3
"""
NATS订单簿消费者示例

订阅NATS中的订单簿数据，展示如何接收和处理推送的订单簿信息
"""

import asyncio
import json
import sys
from datetime import datetime
from typing import Dict, Any, Optional
import structlog

# 添加项目路径
sys.path.append('services/python-collector/src')

try:
    import nats
    from nats.errors import TimeoutError, NoServersError
except ImportError:
    print("❌ 请安装nats-py: pip install nats-py")
    sys.exit(1)

# 配置日志
structlog.configure(
    processors=[
        structlog.stdlib.filter_by_level,
        structlog.stdlib.add_logger_name,
        structlog.stdlib.add_log_level,
        structlog.stdlib.PositionalArgumentsFormatter(),
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.processors.StackInfoRenderer(),
        structlog.processors.format_exc_info,
        structlog.processors.UnicodeDecoder(),
        structlog.dev.ConsoleRenderer()
    ],
    context_class=dict,
    logger_factory=structlog.stdlib.LoggerFactory(),
    wrapper_class=structlog.stdlib.BoundLogger,
    cache_logger_on_first_use=True,
)

logger = structlog.get_logger(__name__)


class OrderBookNATSConsumer:
    """订单簿NATS消费者"""
    
    def __init__(self, nats_url: str = "nats://localhost:4222"):
        self.nats_url = nats_url
        self.nc: Optional[nats.NATS] = None
        self.js: Optional[nats.js.JetStreamContext] = None
        
        # 统计信息
        self.stats = {
            'messages_received': 0,
            'symbols_seen': set(),
            'start_time': None,
            'last_message_time': None,
            'errors': 0
        }
        
        # 订单簿缓存
        self.orderbooks: Dict[str, Dict[str, Any]] = {}
        
        logger.info("NATS订单簿消费者初始化", nats_url=nats_url)
    
    async def connect(self) -> bool:
        """连接到NATS"""
        try:
            self.nc = await nats.connect(self.nats_url)
            self.js = self.nc.jetstream()
            
            logger.info("NATS连接成功", server_info=self.nc.connected_url)
            return True
            
        except NoServersError:
            logger.error("无法连接到NATS服务器", url=self.nats_url)
            return False
        except Exception as e:
            logger.error("NATS连接失败", error=str(e))
            return False
    
    async def disconnect(self):
        """断开NATS连接"""
        if self.nc:
            await self.nc.close()
            logger.info("NATS连接已关闭")
    
    async def subscribe_orderbooks(self, symbols: list = None, exchange: str = "binance"):
        """订阅订单簿数据"""
        if not self.nc:
            logger.error("NATS未连接")
            return
        
        # 构建订阅主题
        if symbols:
            subjects = [f"market.{exchange}.{symbol}.orderbook" for symbol in symbols]
        else:
            # 订阅所有交易对
            subjects = [f"market.{exchange}.*.orderbook"]
        
        logger.info("开始订阅订单簿数据", subjects=subjects)
        self.stats['start_time'] = datetime.utcnow()
        
        # 创建订阅
        for subject in subjects:
            await self.nc.subscribe(subject, cb=self._message_handler)
        
        logger.info("订单簿订阅设置完成")
    
    async def _message_handler(self, msg):
        """消息处理器"""
        try:
            # 解析消息
            data = json.loads(msg.data.decode())
            subject = msg.subject
            
            # 提取交易对信息
            parts = subject.split('.')
            if len(parts) >= 4:
                exchange = parts[1]
                symbol = parts[2]
                data_type = parts[3]
            else:
                logger.warning("无效的主题格式", subject=subject)
                return
            
            # 更新统计信息
            self.stats['messages_received'] += 1
            self.stats['symbols_seen'].add(symbol)
            self.stats['last_message_time'] = datetime.utcnow()
            
            # 处理订单簿数据
            await self._process_orderbook(exchange, symbol, data)
            
            # 定期输出统计信息
            if self.stats['messages_received'] % 10 == 0:
                await self._print_stats()
            
        except json.JSONDecodeError as e:
            logger.error("JSON解析失败", error=str(e), data=msg.data[:100])
            self.stats['errors'] += 1
        except Exception as e:
            logger.error("消息处理异常", error=str(e))
            self.stats['errors'] += 1
    
    async def _process_orderbook(self, exchange: str, symbol: str, data: Dict[str, Any]):
        """处理订单簿数据"""
        try:
            # 缓存订单簿
            key = f"{exchange}.{symbol}"
            self.orderbooks[key] = data
            
            # 解析订单簿信息
            timestamp = data.get('timestamp')
            last_update_id = data.get('last_update_id', 0)
            bids = data.get('bids', [])
            asks = data.get('asks', [])
            
            # 计算基本指标
            best_bid = float(bids[0]['price']) if bids else 0
            best_ask = float(asks[0]['price']) if asks else 0
            spread = best_ask - best_bid if best_bid and best_ask else 0
            depth_levels = len(bids) + len(asks)
            
            logger.debug(
                "订单簿更新",
                symbol=symbol,
                update_id=last_update_id,
                best_bid=best_bid,
                best_ask=best_ask,
                spread=spread,
                depth=depth_levels,
                timestamp=timestamp
            )
            
        except Exception as e:
            logger.error("订单簿处理异常", symbol=symbol, error=str(e))
    
    async def _print_stats(self):
        """输出统计信息"""
        if not self.stats['start_time']:
            return
        
        uptime = datetime.utcnow() - self.stats['start_time']
        rate = self.stats['messages_received'] / max(uptime.total_seconds(), 1)
        
        print(f"\n📊 消费者统计 (运行时间: {uptime})")
        print(f"  • 接收消息数: {self.stats['messages_received']}")
        print(f"  • 消息接收率: {rate:.2f} 消息/秒")
        print(f"  • 交易对数量: {len(self.stats['symbols_seen'])}")
        print(f"  • 错误次数: {self.stats['errors']}")
        print(f"  • 最后消息时间: {self.stats['last_message_time']}")
        
        # 显示当前订单簿状态
        print(f"\n📈 当前订单簿状态:")
        for key, orderbook in list(self.orderbooks.items())[-5:]:  # 显示最近5个
            bids = orderbook.get('bids', [])
            asks = orderbook.get('asks', [])
            
            if bids and asks:
                best_bid = float(bids[0]['price'])
                best_ask = float(asks[0]['price'])
                spread = best_ask - best_bid
                
                print(f"  • {key}: 买价={best_bid:.2f}, 卖价={best_ask:.2f}, 价差={spread:.2f}")
        print()
    
    def get_orderbook(self, exchange: str, symbol: str) -> Optional[Dict[str, Any]]:
        """获取指定交易对的订单簿"""
        key = f"{exchange}.{symbol}"
        return self.orderbooks.get(key)
    
    def get_stats(self) -> Dict[str, Any]:
        """获取统计信息"""
        stats = self.stats.copy()
        stats['symbols_seen'] = list(stats['symbols_seen'])
        
        if stats['start_time']:
            uptime = datetime.utcnow() - stats['start_time']
            stats['uptime_seconds'] = uptime.total_seconds()
            stats['message_rate'] = stats['messages_received'] / max(uptime.total_seconds(), 1)
        
        return stats


async def demo_consumer():
    """演示消费者"""
    print("🚀 NATS订单簿消费者演示")
    print("=" * 50)
    
    # 配置
    nats_url = "nats://localhost:4222"
    demo_symbols = ["BTCUSDT", "ETHUSDT"]
    demo_duration = 60  # 演示1分钟
    
    consumer = OrderBookNATSConsumer(nats_url)
    
    try:
        print(f"📡 连接到NATS服务器: {nats_url}")
        
        # 连接NATS
        success = await consumer.connect()
        if not success:
            print("❌ NATS连接失败")
            return
        
        print("✅ NATS连接成功")
        
        # 订阅订单簿数据
        print(f"📊 订阅订单簿数据: {demo_symbols}")
        await consumer.subscribe_orderbooks(demo_symbols)
        
        print(f"⏰ 开始接收数据，演示时长: {demo_duration}秒")
        print("💡 提示: 请确保订单簿NATS推送器正在运行")
        print()
        
        # 等待接收数据
        start_time = datetime.utcnow()
        while (datetime.utcnow() - start_time).total_seconds() < demo_duration:
            await asyncio.sleep(5)
            
            # 检查是否有数据
            stats = consumer.get_stats()
            if stats['messages_received'] == 0:
                print("⚠️ 尚未接收到任何消息，请检查:")
                print("  1. NATS服务器是否运行 (docker-compose up -d nats)")
                print("  2. 订单簿推送器是否运行 (python run_orderbook_nats_publisher.py)")
                print("  3. 网络连接是否正常")
            
        # 最终统计
        print("\n🏁 演示完成")
        final_stats = consumer.get_stats()
        
        print(f"\n📊 最终统计:")
        print(f"  • 总接收消息: {final_stats['messages_received']}")
        print(f"  • 消息接收率: {final_stats.get('message_rate', 0):.2f} 消息/秒")
        print(f"  • 交易对数量: {len(final_stats['symbols_seen'])}")
        print(f"  • 错误次数: {final_stats['errors']}")
        
        if final_stats['symbols_seen']:
            print(f"  • 接收到的交易对: {', '.join(final_stats['symbols_seen'])}")
        
        # 显示最新订单簿
        print(f"\n📈 最新订单簿数据:")
        for symbol in demo_symbols:
            orderbook = consumer.get_orderbook("binance", symbol)
            if orderbook:
                bids = orderbook.get('bids', [])
                asks = orderbook.get('asks', [])
                
                if bids and asks:
                    best_bid = float(bids[0]['price'])
                    best_ask = float(asks[0]['price'])
                    spread = best_ask - best_bid
                    depth = len(bids) + len(asks)
                    
                    print(f"  • {symbol}:")
                    print(f"    - 最佳买价: {best_bid:.2f}")
                    print(f"    - 最佳卖价: {best_ask:.2f}")
                    print(f"    - 价差: {spread:.2f}")
                    print(f"    - 深度档位: {depth}")
                    print(f"    - 更新ID: {orderbook.get('last_update_id', 'N/A')}")
                else:
                    print(f"  • {symbol}: 订单簿数据不完整")
            else:
                print(f"  • {symbol}: 未接收到数据")
        
        if final_stats['messages_received'] > 0:
            print("\n🎉 演示成功！订单簿数据接收正常")
        else:
            print("\n⚠️ 未接收到任何数据，请检查推送器是否正常运行")
        
    except KeyboardInterrupt:
        print("\n⏹️ 用户中断演示")
    except Exception as e:
        print(f"\n❌ 演示异常: {e}")
        import traceback
        traceback.print_exc()
    finally:
        await consumer.disconnect()
        print("✅ 消费者已关闭")


async def interactive_consumer():
    """交互式消费者"""
    print("🌟 NATS订单簿交互式消费者")
    print("=" * 40)
    
    # 获取用户配置
    nats_url = input("NATS服务器地址 (默认: nats://localhost:4222): ").strip()
    if not nats_url:
        nats_url = "nats://localhost:4222"
    
    exchange = input("交易所 (默认: binance): ").strip()
    if not exchange:
        exchange = "binance"
    
    symbols_input = input("交易对 (用逗号分隔，默认: BTCUSDT,ETHUSDT): ").strip()
    if symbols_input:
        symbols = [s.strip().upper() for s in symbols_input.split(',')]
    else:
        symbols = ["BTCUSDT", "ETHUSDT"]
    
    consumer = OrderBookNATSConsumer(nats_url)
    
    try:
        # 连接NATS
        print(f"\n📡 连接到NATS: {nats_url}")
        success = await consumer.connect()
        if not success:
            return
        
        # 订阅数据
        print(f"📊 订阅 {exchange} 交易所的订单簿: {symbols}")
        await consumer.subscribe_orderbooks(symbols, exchange)
        
        print("\n🚀 开始接收订单簿数据...")
        print("💡 按 Ctrl+C 停止")
        print()
        
        # 持续接收数据
        while True:
            await asyncio.sleep(10)
            await consumer._print_stats()
            
    except KeyboardInterrupt:
        print("\n⏹️ 停止接收数据")
    finally:
        await consumer.disconnect()


async def main():
    """主函数"""
    print("🌟 欢迎使用NATS订单簿消费者")
    print("本工具用于订阅和查看NATS中的订单簿数据")
    print()
    
    print("请选择模式:")
    print("1. 演示模式 (60秒演示)")
    print("2. 交互式模式 (持续运行)")
    print("3. 退出")
    
    try:
        choice = input("\n请选择 (1-3): ").strip()
        
        if choice == "1":
            await demo_consumer()
        elif choice == "2":
            await interactive_consumer()
        elif choice == "3":
            print("再见！")
        else:
            print("无效选择")
            
    except KeyboardInterrupt:
        print("\n程序已退出")


if __name__ == "__main__":
    asyncio.run(main()) 