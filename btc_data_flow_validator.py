#!/usr/bin/env python3
"""
BTC数据流验证器
验证所有四个市场的BTC数据接收和处理
"""

import asyncio
import nats
import json
from datetime import datetime
from collections import defaultdict
from typing import Dict, List, Any

class BTCDataFlowValidator:
    def __init__(self):
        self.nc = None
        self.received_data = defaultdict(list)
        self.expected_markets = [
            'orderbook-data.binance.spot.BTCUSDT',
            'orderbook-data.binance.futures.BTCUSDT', 
            'orderbook-data.okx.spot.BTCUSDT',
            'orderbook-data.okx.perpetual.BTCUSDT'
        ]
        self.validation_results = {}
        
    async def connect_nats(self):
        """连接NATS服务器"""
        try:
            self.nc = await nats.connect('nats://localhost:4222')
            print("✅ NATS连接成功")
        except Exception as e:
            print(f"❌ NATS连接失败: {e}")
            raise
    
    async def validate_btc_data_flow(self, duration: int = 30):
        """验证BTC数据流"""
        print(f"🔍 开始验证BTC数据流 (持续{duration}秒)...")
        print(f"期望的市场: {self.expected_markets}")
        print()
        
        # 订阅所有BTC相关主题
        async def message_handler(msg):
            await self._handle_btc_message(msg)
        
        await self.nc.subscribe('orderbook-data.*.*.BTCUSDT', cb=message_handler)
        
        # 等待数据收集
        await asyncio.sleep(duration)
        
        # 分析结果
        await self._analyze_results()
    
    async def _handle_btc_message(self, msg):
        """处理BTC消息"""
        try:
            subject = msg.subject
            data = json.loads(msg.data.decode())
            
            # 验证数据格式
            validation_result = self._validate_message_format(subject, data)
            
            # 记录数据
            self.received_data[subject].append({
                'timestamp': datetime.now(),
                'validation': validation_result,
                'price_info': self._extract_price_info(data)
            })
            
            # 实时显示
            if validation_result['valid']:
                price_info = validation_result['price_info']
                print(f"✅ {subject}: BTC价格=${price_info['bid_price']:,.2f}/${price_info['ask_price']:,.2f}")
            else:
                print(f"❌ {subject}: {validation_result['error']}")
                
        except Exception as e:
            print(f"❌ 消息处理错误 {msg.subject}: {e}")
    
    def _validate_message_format(self, subject: str, data: Dict[str, Any]) -> Dict[str, Any]:
        """验证消息格式"""
        result = {
            'valid': False,
            'error': None,
            'price_info': None,
            'data_quality': {}
        }
        
        try:
            # 检查必要字段
            required_fields = ['exchange', 'symbol', 'bids', 'asks', 'timestamp']
            missing_fields = [field for field in required_fields if field not in data]
            
            if missing_fields:
                result['error'] = f"缺少字段: {missing_fields}"
                return result
            
            # 检查bids和asks格式
            if not data['bids'] or not data['asks']:
                result['error'] = "bids或asks为空"
                return result
            
            # 提取价格信息
            price_info = self._extract_price_info(data)
            if not price_info:
                result['error'] = "无法提取价格信息"
                return result
            
            # 验证BTC价格合理性 (应该在$100,000+)
            if price_info['bid_price'] < 50000 or price_info['ask_price'] < 50000:
                result['error'] = f"BTC价格异常: bid=${price_info['bid_price']}, ask=${price_info['ask_price']}"
                return result
            
            # 验证价差合理性
            spread = price_info['ask_price'] - price_info['bid_price']
            spread_pct = (spread / price_info['bid_price']) * 100
            
            if spread_pct > 1.0:  # 价差超过1%可能异常
                result['error'] = f"价差过大: {spread_pct:.4f}%"
                return result
            
            result['valid'] = True
            result['price_info'] = price_info
            result['data_quality'] = {
                'bid_levels': len(data['bids']),
                'ask_levels': len(data['asks']),
                'spread_pct': spread_pct,
                'timestamp': data['timestamp']
            }
            
        except Exception as e:
            result['error'] = f"验证异常: {e}"
        
        return result
    
    def _extract_price_info(self, data: Dict[str, Any]) -> Dict[str, float]:
        """提取价格信息"""
        try:
            bids = data['bids']
            asks = data['asks']
            
            if not bids or not asks:
                return None
            
            # 处理两种格式
            bid = bids[0]
            ask = asks[0]
            
            if isinstance(bid, dict) and 'price' in bid:
                # 对象格式: {"price": "105903.9", "quantity": "1.09281899"}
                bid_price = float(bid['price'])
                ask_price = float(ask['price'])
            elif isinstance(bid, list) and len(bid) >= 2:
                # 数组格式: [105903.9, 1.09281899]
                bid_price = float(bid[0])
                ask_price = float(ask[0])
            else:
                return None
            
            return {
                'bid_price': bid_price,
                'ask_price': ask_price
            }
            
        except Exception:
            return None
    
    async def _analyze_results(self):
        """分析验证结果"""
        print("\n" + "="*60)
        print("📊 BTC数据流验证结果分析")
        print("="*60)
        
        # 检查每个期望市场的数据接收情况
        for market in self.expected_markets:
            if market in self.received_data:
                data_points = self.received_data[market]
                valid_count = sum(1 for dp in data_points if dp['validation']['valid'])
                total_count = len(data_points)
                
                print(f"\n✅ {market}:")
                print(f"   数据点数: {total_count}")
                print(f"   有效数据: {valid_count}/{total_count} ({valid_count/total_count*100:.1f}%)")
                
                if valid_count > 0:
                    # 显示最新价格
                    latest_valid = next(dp for dp in reversed(data_points) if dp['validation']['valid'])
                    price_info = latest_valid['price_info']
                    print(f"   最新价格: ${price_info['bid_price']:,.2f}/${price_info['ask_price']:,.2f}")
                    
                    # 显示数据质量
                    quality = latest_valid['validation']['data_quality']
                    print(f"   订单簿深度: {quality['bid_levels']}/{quality['ask_levels']}")
                    print(f"   价差: {quality['spread_pct']:.4f}%")
            else:
                print(f"\n❌ {market}: 未收到数据")
        
        # 总体统计
        total_markets_received = len(self.received_data)
        expected_markets_count = len(self.expected_markets)
        
        print(f"\n📈 总体统计:")
        print(f"   期望市场数: {expected_markets_count}")
        print(f"   实际接收市场数: {total_markets_received}")
        print(f"   覆盖率: {total_markets_received/expected_markets_count*100:.1f}%")
        
        # 数据质量评估
        if total_markets_received == expected_markets_count:
            print("✅ 所有期望的BTC市场都有数据接收")
        else:
            missing_markets = set(self.expected_markets) - set(self.received_data.keys())
            print(f"❌ 缺失市场: {list(missing_markets)}")
    
    async def close(self):
        """关闭连接"""
        if self.nc:
            await self.nc.close()

async def main():
    """主函数"""
    validator = BTCDataFlowValidator()
    
    try:
        await validator.connect_nats()
        await validator.validate_btc_data_flow(duration=30)
    except KeyboardInterrupt:
        print("\n⏹️ 用户中断验证")
    except Exception as e:
        print(f"❌ 验证过程出错: {e}")
    finally:
        await validator.close()

if __name__ == "__main__":
    asyncio.run(main())
