#!/usr/bin/env python3
"""
检查Symbol标准化过程的脚本
验证OKX的BTC-USDT-SWAP是否正确转换为BTC-USDT
"""

import asyncio
import json
import sys
from datetime import datetime
from pathlib import Path

# 添加项目路径
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root / "services" / "data-collector"))

try:
    import nats
    from nats.errors import TimeoutError
except ImportError as e:
    print(f"❌ 无法导入NATS库: {e}")
    print("请安装: pip install nats-py")
    sys.exit(1)

class SymbolNormalizationChecker:
    def __init__(self):
        self.nc = None
        self.message_count = 0
        self.symbol_mappings = {}
        self.raw_symbols_seen = set()
        self.normalized_symbols_seen = set()
        
    async def connect(self):
        """连接到NATS服务器"""
        try:
            self.nc = await nats.connect("nats://localhost:4222")
            print("✅ 成功连接到NATS服务器")
            return True
        except Exception as e:
            print(f"❌ 连接NATS服务器失败: {e}")
            return False
    
    async def message_handler(self, msg):
        """处理接收到的消息"""
        self.message_count += 1
        
        # 解析消息数据
        try:
            data = json.loads(msg.data.decode())
            timestamp = datetime.now().strftime("%H:%M:%S")
            
            # 提取关键信息
            exchange = data.get("exchange", "unknown")
            symbol = data.get("symbol", "unknown")
            normalized_symbol = data.get("normalized_symbol", "N/A")
            data_type = data.get("data_type", "unknown")
            
            # 记录symbol映射关系
            if exchange not in self.symbol_mappings:
                self.symbol_mappings[exchange] = {}
            
            # 检查是否有原始symbol信息
            raw_symbol = None
            if 'instId' in data:
                raw_symbol = data['instId']
            elif 'instrument_id' in data:
                raw_symbol = data['instrument_id']
            elif 'raw_symbol' in data:
                raw_symbol = data['raw_symbol']
            
            if raw_symbol:
                self.raw_symbols_seen.add(f"{exchange}:{raw_symbol}")
                self.symbol_mappings[exchange][raw_symbol] = {
                    'symbol': symbol,
                    'normalized_symbol': normalized_symbol,
                    'data_type': data_type,
                    'subject': msg.subject
                }
            
            self.normalized_symbols_seen.add(f"{exchange}:{symbol}")
            
            # 特别关注OKX的symbol转换
            if exchange.startswith('okx') and (raw_symbol or symbol):
                display_raw = raw_symbol if raw_symbol else "N/A"
                print(f"🔍 [{timestamp}] OKX Symbol转换:")
                print(f"    交易所: {exchange}")
                print(f"    原始Symbol: {display_raw}")
                print(f"    标准Symbol: {symbol}")
                print(f"    标准化Symbol: {normalized_symbol}")
                print(f"    数据类型: {data_type}")
                print(f"    NATS主题: {msg.subject}")
                print("-" * 50)
                
        except json.JSONDecodeError:
            print(f"⚠️ [{datetime.now().strftime('%H:%M:%S')}] 无法解析JSON: {msg.subject}")
        except Exception as e:
            print(f"❌ [{datetime.now().strftime('%H:%M:%S')}] 处理消息错误: {e}")
    
    async def subscribe_all(self):
        """订阅所有主题"""
        if not self.nc:
            print("❌ 未连接到NATS服务器")
            return
            
        try:
            # 订阅所有主题
            await self.nc.subscribe(">", cb=self.message_handler)
            print("🔍 开始检查Symbol标准化过程...")
            print("=" * 60)
            
        except Exception as e:
            print(f"❌ 订阅失败: {e}")
    
    async def monitor(self, duration=30):
        """监控指定时间"""
        print(f"⏰ 监控时间: {duration}秒")
        
        start_time = asyncio.get_event_loop().time()
        
        while True:
            current_time = asyncio.get_event_loop().time()
            elapsed = current_time - start_time
            
            if elapsed >= duration:
                break
                
            await asyncio.sleep(1)
        
        # 显示统计信息
        print("\n" + "=" * 60)
        print("📊 Symbol标准化统计:")
        print(f"  总消息数: {self.message_count}")
        print(f"  原始Symbols: {len(self.raw_symbols_seen)}")
        print(f"  标准化Symbols: {len(self.normalized_symbols_seen)}")
        
        # 显示各交易所的symbol映射
        for exchange, mappings in self.symbol_mappings.items():
            if mappings:
                print(f"\n📋 {exchange.upper()} Symbol映射:")
                for raw_symbol, info in mappings.items():
                    print(f"  {raw_symbol} → {info['symbol']} → {info['normalized_symbol']}")
                    print(f"    数据类型: {info['data_type']}, 主题: {info['subject']}")
        
        # 特别检查OKX的SWAP转换
        okx_swaps = []
        for exchange, mappings in self.symbol_mappings.items():
            if exchange.startswith('okx'):
                for raw_symbol, info in mappings.items():
                    if '-SWAP' in raw_symbol:
                        okx_swaps.append({
                            'exchange': exchange,
                            'raw': raw_symbol,
                            'symbol': info['symbol'],
                            'normalized': info['normalized_symbol']
                        })
        
        if okx_swaps:
            print(f"\n🎯 OKX SWAP Symbol转换验证:")
            for swap in okx_swaps:
                expected = swap['raw'].replace('-SWAP', '')
                actual_symbol = swap['symbol']
                actual_normalized = swap['normalized']
                
                symbol_correct = actual_symbol == expected
                normalized_correct = actual_normalized == expected
                
                print(f"  {swap['raw']} ({swap['exchange']}):")
                print(f"    期望: {expected}")
                print(f"    实际Symbol: {actual_symbol} {'✅' if symbol_correct else '❌'}")
                print(f"    实际Normalized: {actual_normalized} {'✅' if normalized_correct else '❌'}")
        else:
            print(f"\n⚠️ 未发现OKX SWAP Symbol数据")
        
        # 显示所有发现的symbols
        print(f"\n📝 发现的所有Symbols:")
        for symbol in sorted(self.normalized_symbols_seen):
            print(f"  {symbol}")
    
    async def close(self):
        """关闭连接"""
        if self.nc:
            await self.nc.close()
            print("🔌 NATS连接已关闭")

async def main():
    """主函数"""
    print("🔍 Symbol标准化检查工具")
    print("=" * 60)
    
    checker = SymbolNormalizationChecker()
    
    # 连接NATS
    if not await checker.connect():
        return
    
    try:
        # 订阅所有消息
        await checker.subscribe_all()
        
        # 监控30秒
        await checker.monitor(30)
        
    except KeyboardInterrupt:
        print("\n⏹️ 用户中断监控")
    except Exception as e:
        print(f"❌ 监控过程中出错: {e}")
    finally:
        await checker.close()

if __name__ == "__main__":
    asyncio.run(main())
