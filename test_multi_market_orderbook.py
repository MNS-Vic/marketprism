#!/usr/bin/env python3
"""
多市场OrderBook Manager架构验证脚本
验证每个symbol是否有4个独立的订单簿数据流
"""

import asyncio
import json
import nats
from datetime import datetime, timedelta
from collections import defaultdict
import signal
import sys


class MultiMarketOrderBookValidator:
    """多市场订单簿验证器"""
    
    def __init__(self):
        self.nc = None
        self.received_messages = defaultdict(list)
        self.market_types = set()
        self.exchanges = set()
        self.symbols = set()
        self.running = True
        
        # 期望的市场配置
        self.expected_markets = [
            ('binance', 'spot'),
            ('binance', 'futures'),
            ('okx', 'spot'),
            ('okx', 'perpetual')
        ]
        
        # 期望的交易对
        self.expected_symbols = ['BTCUSDT', 'ETHUSDT', 'BNBUSDT']
        
    async def connect_nats(self):
        """连接NATS服务器"""
        # 尝试多个NATS地址
        nats_urls = [
            "nats://localhost:4222",  # 主机直接连接
            "nats://127.0.0.1:4222",  # 本地回环
        ]

        for url in nats_urls:
            try:
                print(f"🔗 尝试连接NATS: {url}")
                self.nc = await nats.connect(url)
                print(f"✅ 已连接到NATS服务器: {url}")
                return True
            except Exception as e:
                print(f"❌ 连接NATS失败 ({url}): {e}")
                continue

        print("❌ 所有NATS连接尝试都失败了")
        return False
    
    async def subscribe_orderbook_data(self):
        """订阅所有订单簿数据"""
        try:
            # 订阅所有订单簿主题 - 支持多种格式
            subjects = [
                "orderbook-data.*.*.>",  # 新格式: exchange.market_type.symbol
                "orderbook-data.*.*",    # 旧格式: exchange.symbol
                "orderbook-data.>"       # 通配符格式
            ]

            for subject in subjects:
                await self.nc.subscribe(subject, cb=self.handle_orderbook_message)
                print(f"✅ 已订阅订单簿数据: {subject}")
        except Exception as e:
            print(f"❌ 订阅失败: {e}")
    
    def _normalize_symbol_for_validation(self, symbol: str, exchange: str) -> str:
        """
        标准化交易对格式用于验证

        Args:
            symbol: 原始交易对符号
            exchange: 交易所名称

        Returns:
            标准化的交易对符号（如BTCUSDT）
        """
        if not symbol:
            return symbol

        # 移除常见的分隔符和后缀
        normalized = symbol.upper()

        # 处理不同交易所的格式
        if exchange.lower() == 'okx':
            # OKX格式: BTC-USDT, BTC-USDT-SWAP -> BTCUSDT
            if '-SWAP' in normalized:
                normalized = normalized.replace('-SWAP', '')
            normalized = normalized.replace('-', '')
        elif exchange.lower() == 'binance':
            # Binance格式: BTCUSDT (已经是标准格式)
            pass
        else:
            # 其他交易所：移除常见分隔符
            normalized = normalized.replace('-', '').replace('_', '').replace('/', '')

        return normalized

    async def handle_orderbook_message(self, msg):
        """处理订单簿消息"""
        try:
            # 解析主题: 支持两种格式
            # 格式1: orderbook-data.{exchange}.{market_type}.{symbol}
            # 格式2: orderbook-data.{exchange}.{symbol}
            subject_parts = msg.subject.split('.')

            if len(subject_parts) >= 4:
                # 新格式: orderbook-data.{exchange}.{market_type}.{symbol}
                exchange = subject_parts[1]
                market_type = subject_parts[2]
                raw_symbol = subject_parts[3]
            elif len(subject_parts) >= 3:
                # 旧格式: orderbook-data.{exchange}.{symbol}
                exchange = subject_parts[1]
                market_type = "unknown"  # 默认市场类型
                raw_symbol = subject_parts[2]
            else:
                print(f"⚠️ 无法解析主题: {msg.subject}")
                return

            # 标准化交易对格式
            symbol = self._normalize_symbol_for_validation(raw_symbol, exchange)

            # 解析消息数据
            data = json.loads(msg.data.decode())
            update_type = data.get('update_type', 'unknown')

            # 记录消息
            key = f"{exchange}.{market_type}.{symbol}"
            self.received_messages[key].append({
                'timestamp': datetime.now(),
                'update_type': update_type,
                'bid_levels': len(data.get('bids', [])),
                'ask_levels': len(data.get('asks', []))
            })

            # 记录市场信息
            self.exchanges.add(exchange)
            self.market_types.add(market_type)
            self.symbols.add(symbol)

            # 实时输出
            print(f"📊 {key}: {update_type}, 买盘={len(data.get('bids', []))}, 卖盘={len(data.get('asks', []))}")
                
        except Exception as e:
            print(f"❌ 处理消息失败: {e}")
    
    def analyze_coverage(self):
        """分析市场覆盖情况"""
        print("\n" + "="*60)
        print("📈 多市场OrderBook覆盖分析")
        print("="*60)
        
        print(f"🔍 发现的交易所: {sorted(self.exchanges)}")
        print(f"🔍 发现的市场类型: {sorted(self.market_types)}")
        print(f"🔍 发现的交易对: {sorted(self.symbols)}")
        
        print(f"\n📊 数据流统计:")
        for key, messages in self.received_messages.items():
            if messages:
                update_count = len([m for m in messages if m['update_type'] == 'update'])
                snapshot_count = len([m for m in messages if m['update_type'] == 'snapshot'])
                print(f"  {key}: {len(messages)}条消息 (增量={update_count}, 快照={snapshot_count})")
        
        # 检查期望的市场覆盖
        print(f"\n✅ 期望的市场配置检查:")
        missing_markets = []
        for exchange, market_type in self.expected_markets:
            found = False
            for symbol in self.expected_symbols:
                key = f"{exchange}.{market_type}.{symbol}"
                if key in self.received_messages and self.received_messages[key]:
                    found = True
                    break
            
            if found:
                print(f"  ✅ {exchange}.{market_type}: 有数据")
            else:
                print(f"  ❌ {exchange}.{market_type}: 无数据")
                missing_markets.append(f"{exchange}.{market_type}")
        
        # 检查每个symbol的4个市场覆盖
        print(f"\n🎯 每个Symbol的4市场覆盖检查:")
        for symbol in self.expected_symbols:
            markets_for_symbol = []
            for exchange, market_type in self.expected_markets:
                key = f"{exchange}.{market_type}.{symbol}"
                if key in self.received_messages and self.received_messages[key]:
                    markets_for_symbol.append(f"{exchange}.{market_type}")
            
            print(f"  {symbol}: {len(markets_for_symbol)}/4 市场")
            for market in markets_for_symbol:
                print(f"    ✅ {market}")
            
            missing = set([f"{e}.{m}" for e, m in self.expected_markets]) - set(markets_for_symbol)
            for market in missing:
                print(f"    ❌ {market}")
        
        return len(missing_markets) == 0
    
    def signal_handler(self, signum, frame):
        """信号处理器"""
        print(f"\n🛑 收到信号 {signum}，正在停止...")
        self.running = False
    
    async def run_validation(self, duration_seconds=60):
        """运行验证"""
        print(f"🚀 开始多市场OrderBook验证，持续时间: {duration_seconds}秒")
        
        # 设置信号处理
        signal.signal(signal.SIGINT, self.signal_handler)
        signal.signal(signal.SIGTERM, self.signal_handler)
        
        # 连接NATS
        if not await self.connect_nats():
            return False
        
        # 订阅数据
        await self.subscribe_orderbook_data()
        
        # 等待数据
        start_time = datetime.now()
        end_time = start_time + timedelta(seconds=duration_seconds)
        
        print(f"⏰ 开始收集数据，结束时间: {end_time.strftime('%H:%M:%S')}")
        
        while self.running and datetime.now() < end_time:
            await asyncio.sleep(1)
            
            # 每10秒显示进度
            if (datetime.now() - start_time).seconds % 10 == 0:
                elapsed = (datetime.now() - start_time).seconds
                remaining = duration_seconds - elapsed
                print(f"⏳ 已收集 {elapsed}秒，剩余 {remaining}秒，收到 {sum(len(msgs) for msgs in self.received_messages.values())} 条消息")
        
        # 分析结果
        success = self.analyze_coverage()
        
        # 关闭连接
        if self.nc:
            await self.nc.close()
        
        return success


async def main():
    """主函数"""
    validator = MultiMarketOrderBookValidator()
    
    try:
        success = await validator.run_validation(duration_seconds=90)
        
        if success:
            print("\n🎉 多市场OrderBook架构验证成功！")
            sys.exit(0)
        else:
            print("\n❌ 多市场OrderBook架构验证失败！")
            sys.exit(1)
            
    except KeyboardInterrupt:
        print("\n🛑 用户中断验证")
        sys.exit(1)
    except Exception as e:
        print(f"\n💥 验证过程异常: {e}")
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main())
