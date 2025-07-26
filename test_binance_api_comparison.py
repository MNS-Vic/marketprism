#!/usr/bin/env python3
"""
测试Binance衍生品REST API vs WebSocket API的lastUpdateId差距
"""

import asyncio
import json
import time
import aiohttp
import websockets
from datetime import datetime
from collections import deque

async def get_rest_api_snapshot(symbol="BTCUSDT", limit=500):
    """通过REST API获取订单簿快照"""
    url = f"https://fapi.binance.com/fapi/v1/depth"
    params = {
        'symbol': symbol,
        'limit': limit
    }
    
    try:
        async with aiohttp.ClientSession() as session:
            start_time = time.time()
            async with session.get(url, params=params, timeout=aiohttp.ClientTimeout(total=10)) as response:
                end_time = time.time()
                
                if response.status == 200:
                    data = await response.json()
                    return {
                        'source': 'REST_API',
                        'symbol': symbol,
                        'lastUpdateId': data.get('lastUpdateId'),
                        'bids_count': len(data.get('bids', [])),
                        'asks_count': len(data.get('asks', [])),
                        'response_time_ms': round((end_time - start_time) * 1000, 2),
                        'timestamp': datetime.now().isoformat()
                    }
                else:
                    return {
                        'source': 'REST_API',
                        'error': f'HTTP {response.status}',
                        'timestamp': datetime.now().isoformat()
                    }
    except Exception as e:
        return {
            'source': 'REST_API',
            'error': str(e),
            'timestamp': datetime.now().isoformat()
        }

async def get_websocket_api_snapshot(symbol="BTCUSDT", limit=500):
    """通过WebSocket API获取订单簿快照"""
    ws_url = "wss://ws-fapi.binance.com/ws-fapi/v1"
    
    try:
        start_time = time.time()
        async with websockets.connect(ws_url) as websocket:
            # 构建请求
            request = {
                "id": f"test_{symbol}_{int(time.time() * 1000)}",
                "method": "depth",
                "params": {
                    "symbol": symbol,
                    "limit": limit
                }
            }
            
            # 发送请求
            await websocket.send(json.dumps(request))
            
            # 等待响应
            response_str = await asyncio.wait_for(websocket.recv(), timeout=10.0)
            end_time = time.time()
            
            response_data = json.loads(response_str)
            
            if response_data.get('status') == 200:
                result = response_data.get('result', {})
                return {
                    'source': 'WebSocket_API',
                    'symbol': symbol,
                    'lastUpdateId': result.get('lastUpdateId'),
                    'bids_count': len(result.get('bids', [])),
                    'asks_count': len(result.get('asks', [])),
                    'response_time_ms': round((end_time - start_time) * 1000, 2),
                    'timestamp': datetime.now().isoformat(),
                    'request_id': request['id']
                }
            else:
                return {
                    'source': 'WebSocket_API',
                    'error': response_data.get('error', 'Unknown error'),
                    'timestamp': datetime.now().isoformat()
                }
                
    except Exception as e:
        return {
            'source': 'WebSocket_API',
            'error': str(e),
            'timestamp': datetime.now().isoformat()
        }

class WebSocketStreamMonitor:
    """WebSocket Stream监控器"""

    def __init__(self, symbol="BTCUSDT"):
        self.symbol = symbol
        self.ws_url = f"wss://fstream.binance.com/ws/{symbol.lower()}@depth"
        self.recent_messages = deque(maxlen=50)  # 保存最近50条消息
        self.websocket = None
        self.running = False

    async def start_monitoring(self):
        """开始监控WebSocket Stream"""
        try:
            print(f"🔗 连接WebSocket Stream: {self.ws_url}")
            self.websocket = await websockets.connect(self.ws_url)
            self.running = True

            # 启动监听任务
            asyncio.create_task(self._listen_messages())

            # 等待一些消息到达
            await asyncio.sleep(2)
            print(f"✅ WebSocket Stream连接成功，已收到 {len(self.recent_messages)} 条消息")

        except Exception as e:
            print(f"❌ WebSocket Stream连接失败: {e}")

    async def _listen_messages(self):
        """监听WebSocket消息"""
        try:
            while self.running and self.websocket:
                message_str = await self.websocket.recv()
                message = json.loads(message_str)

                # 保存消息（带时间戳）
                message['received_at'] = time.time()
                self.recent_messages.append(message)

        except Exception as e:
            print(f"⚠️ WebSocket Stream监听异常: {e}")

    def get_latest_message(self):
        """获取最新的消息"""
        if self.recent_messages:
            return self.recent_messages[-1]
        return None

    def get_message_range(self):
        """获取消息范围"""
        if not self.recent_messages:
            return None

        messages = list(self.recent_messages)
        first_msg = messages[0]
        last_msg = messages[-1]

        return {
            'count': len(messages),
            'first_U': first_msg.get('U'),
            'first_u': first_msg.get('u'),
            'first_pu': first_msg.get('pu'),
            'last_U': last_msg.get('U'),
            'last_u': last_msg.get('u'),
            'last_pu': last_msg.get('pu'),
            'time_span_seconds': round(last_msg.get('received_at', 0) - first_msg.get('received_at', 0), 2)
        }

    async def stop(self):
        """停止监控"""
        self.running = False
        if self.websocket:
            await self.websocket.close()

async def compare_apis_with_stream(symbol="BTCUSDT", limit=500, rounds=5):
    """对比REST API、WebSocket API和WebSocket Stream"""
    print(f"🔍 开始全面对比测试: {symbol}, limit={limit}, rounds={rounds}")
    print("包含: REST API, WebSocket API, WebSocket Stream")
    print("=" * 100)

    # 启动WebSocket Stream监控
    stream_monitor = WebSocketStreamMonitor(symbol)
    await stream_monitor.start_monitoring()

    results = []
    
    for round_num in range(1, rounds + 1):
        print(f"\n📊 第 {round_num}/{rounds} 轮测试")
        print("-" * 60)

        # 获取WebSocket Stream当前状态
        stream_range = stream_monitor.get_message_range()
        latest_stream_msg = stream_monitor.get_latest_message()

        # 同时发起两个API请求
        tasks = [
            get_rest_api_snapshot(symbol, limit),
            get_websocket_api_snapshot(symbol, limit)
        ]

        round_results = await asyncio.gather(*tasks)

        # 显示结果
        rest_result = round_results[0]
        ws_result = round_results[1]
        
        print(f"REST API:")
        if 'error' in rest_result:
            print(f"  ❌ 错误: {rest_result['error']}")
        else:
            print(f"  ✅ lastUpdateId: {rest_result['lastUpdateId']}")
            print(f"  📊 数据: {rest_result['bids_count']} bids, {rest_result['asks_count']} asks")
            print(f"  ⏱️  响应时间: {rest_result['response_time_ms']}ms")

        print(f"WebSocket API:")
        if 'error' in ws_result:
            print(f"  ❌ 错误: {ws_result['error']}")
        else:
            print(f"  ✅ lastUpdateId: {ws_result['lastUpdateId']}")
            print(f"  📊 数据: {ws_result['bids_count']} bids, {ws_result['asks_count']} asks")
            print(f"  ⏱️  响应时间: {ws_result['response_time_ms']}ms")

        print(f"WebSocket Stream:")
        if stream_range and latest_stream_msg:
            print(f"  ✅ 最新消息: U={latest_stream_msg.get('U')}, u={latest_stream_msg.get('u')}, pu={latest_stream_msg.get('pu')}")
            print(f"  📊 缓存范围: {stream_range['first_U']} ~ {stream_range['last_u']} ({stream_range['count']}条消息)")
            print(f"  ⏱️  时间跨度: {stream_range['time_span_seconds']}秒")
        else:
            print(f"  ❌ 暂无Stream数据")
        
        # 计算差距
        if ('lastUpdateId' in rest_result and 'lastUpdateId' in ws_result and
            latest_stream_msg and latest_stream_msg.get('u')):

            rest_id = rest_result['lastUpdateId']
            ws_id = ws_result['lastUpdateId']
            stream_u = latest_stream_msg.get('u')
            stream_U = latest_stream_msg.get('U')

            print(f"📈 数据新旧对比:")
            print(f"  REST API lastUpdateId: {rest_id}")
            print(f"  WebSocket API lastUpdateId: {ws_id}")
            print(f"  Stream 最新消息: U={stream_U}, u={stream_u}")

            # 计算各种差距
            ws_vs_rest = ws_id - rest_id
            ws_vs_stream = ws_id - stream_u
            rest_vs_stream = rest_id - stream_u

            print(f"📊 差距分析:")
            print(f"  WebSocket API vs REST API: {ws_vs_rest}")
            print(f"  WebSocket API vs Stream u: {ws_vs_stream}")
            print(f"  REST API vs Stream u: {rest_vs_stream}")

            # 判断哪个最新
            data_sources = [
                ('REST API', rest_id),
                ('WebSocket API', ws_id),
                ('Stream u', stream_u)
            ]
            data_sources.sort(key=lambda x: x[1], reverse=True)

            print(f"🏆 数据新旧排序:")
            for i, (source, update_id) in enumerate(data_sources):
                if i == 0:
                    print(f"  1️⃣ {source}: {update_id} (最新)")
                else:
                    gap = data_sources[0][1] - update_id
                    print(f"  {i+1}️⃣ {source}: {update_id} (落后 {gap})")

            # 保存结果用于统计
            results.append({
                'round': round_num,
                'rest_lastUpdateId': rest_id,
                'ws_lastUpdateId': ws_id,
                'stream_u': stream_u,
                'stream_U': stream_U,
                'ws_vs_rest': ws_vs_rest,
                'ws_vs_stream': ws_vs_stream,
                'rest_vs_stream': rest_vs_stream,
                'rest_response_time': rest_result['response_time_ms'],
                'ws_response_time': ws_result['response_time_ms']
            })
        
        # 间隔1秒
        if round_num < rounds:
            await asyncio.sleep(1)

    # 停止Stream监控
    await stream_monitor.stop()

    # 统计分析
    if results:
        print("\n" + "=" * 100)
        print("📊 综合统计分析")
        print("=" * 100)

        ws_vs_rest_gaps = [r['ws_vs_rest'] for r in results]
        ws_vs_stream_gaps = [r['ws_vs_stream'] for r in results]
        rest_vs_stream_gaps = [r['rest_vs_stream'] for r in results]
        rest_times = [r['rest_response_time'] for r in results]
        ws_times = [r['ws_response_time'] for r in results]

        print(f"📈 WebSocket API vs REST API:")
        print(f"  平均差距: {sum(ws_vs_rest_gaps) / len(ws_vs_rest_gaps):.1f}")
        print(f"  差距范围: {min(ws_vs_rest_gaps)} ~ {max(ws_vs_rest_gaps)}")

        print(f"\n📈 WebSocket API vs Stream u:")
        print(f"  平均差距: {sum(ws_vs_stream_gaps) / len(ws_vs_stream_gaps):.1f}")
        print(f"  差距范围: {min(ws_vs_stream_gaps)} ~ {max(ws_vs_stream_gaps)}")

        print(f"\n📈 REST API vs Stream u:")
        print(f"  平均差距: {sum(rest_vs_stream_gaps) / len(rest_vs_stream_gaps):.1f}")
        print(f"  差距范围: {min(rest_vs_stream_gaps)} ~ {max(rest_vs_stream_gaps)}")

        print(f"\n⏱️ 响应时间统计:")
        print(f"  REST API 平均响应时间: {sum(rest_times) / len(rest_times):.1f}ms")
        print(f"  WebSocket API 平均响应时间: {sum(ws_times) / len(ws_times):.1f}ms")

        # 分析哪个数据源最新
        ws_newest = sum(1 for r in results if r['ws_lastUpdateId'] >= r['rest_lastUpdateId'] and r['ws_lastUpdateId'] >= r['stream_u'])
        rest_newest = sum(1 for r in results if r['rest_lastUpdateId'] >= r['ws_lastUpdateId'] and r['rest_lastUpdateId'] >= r['stream_u'])
        stream_newest = sum(1 for r in results if r['stream_u'] >= r['ws_lastUpdateId'] and r['stream_u'] >= r['rest_lastUpdateId'])

        print(f"\n🏆 数据源新旧统计:")
        print(f"  WebSocket API 最新: {ws_newest}/{len(results)} 次")
        print(f"  REST API 最新: {rest_newest}/{len(results)} 次")
        print(f"  Stream 最新: {stream_newest}/{len(results)} 次")

async def main():
    """主函数"""
    print("🚀 Binance衍生品全面API对比测试")
    print("测试REST API vs WebSocket API vs WebSocket Stream的数据差距")
    print()

    # 测试BTCUSDT
    await compare_apis_with_stream("BTCUSDT", 500, 5)

if __name__ == "__main__":
    asyncio.run(main())
