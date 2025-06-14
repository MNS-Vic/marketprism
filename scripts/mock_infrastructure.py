#!/usr/bin/env python3
"""
模拟基础设施服务
为MarketPrism提供内存数据库和消息队列的模拟实现
"""

import asyncio
import aiohttp
from aiohttp import web
import json
import time
import threading
from pathlib import Path
import sys

PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

class MockRedisServer:
    """模拟Redis服务器"""
    
    def __init__(self):
        self.data = {}
        self.app = web.Application()
        self.setup_routes()
    
    def setup_routes(self):
        """设置路由"""
        self.app.router.add_get('/ping', self.ping)
        self.app.router.add_post('/set/{key}', self.set_key)
        self.app.router.add_get('/get/{key}', self.get_key)
        self.app.router.add_delete('/del/{key}', self.del_key)
    
    async def ping(self, request):
        """Redis PING命令"""
        return web.Response(text="PONG")
    
    async def set_key(self, request):
        """设置键值"""
        key = request.match_info['key']
        value = await request.text()
        self.data[key] = value
        return web.Response(text="OK")
    
    async def get_key(self, request):
        """获取键值"""
        key = request.match_info['key']
        value = self.data.get(key)
        if value is None:
            return web.Response(status=404, text="KEY_NOT_FOUND")
        return web.Response(text=value)
    
    async def del_key(self, request):
        """删除键"""
        key = request.match_info['key']
        if key in self.data:
            del self.data[key]
            return web.Response(text="1")
        return web.Response(text="0")

class MockClickHouseServer:
    """模拟ClickHouse服务器"""
    
    def __init__(self):
        self.tables = {}
        self.app = web.Application()
        self.setup_routes()
    
    def setup_routes(self):
        """设置路由"""
        self.app.router.add_get('/ping', self.ping)
        self.app.router.add_post('/', self.query)
        self.app.router.add_get('/', self.query_get)
    
    async def ping(self, request):
        """健康检查"""
        return web.Response(text="Ok.")
    
    async def query(self, request):
        """处理SQL查询"""
        query = await request.text()
        
        # 模拟常见查询响应
        if 'CREATE TABLE' in query.upper():
            return web.Response(text="")
        elif 'INSERT' in query.upper():
            return web.Response(text="")
        elif 'SELECT' in query.upper():
            if 'version()' in query.lower():
                return web.Response(text="24.1.1.1")
            return web.Response(text="[]")
        
        return web.Response(text="")
    
    async def query_get(self, request):
        """处理GET查询"""
        query = request.query.get('query', '')
        
        if 'version()' in query.lower():
            return web.Response(text="24.1.1.1")
        elif 'show tables' in query.lower():
            return web.Response(text="")
            
        return web.Response(text="Ok.")

class MockNATSServer:
    """模拟NATS服务器"""
    
    def __init__(self):
        self.subjects = {}
        self.app = web.Application()
        self.setup_routes()
    
    def setup_routes(self):
        """设置路由"""
        self.app.router.add_get('/healthz', self.healthz)
        self.app.router.add_post('/pub/{subject}', self.publish)
        self.app.router.add_get('/sub/{subject}', self.subscribe)
    
    async def healthz(self, request):
        """健康检查"""
        return web.Response(text="OK")
    
    async def publish(self, request):
        """发布消息"""
        subject = request.match_info['subject']
        message = await request.text()
        
        if subject not in self.subjects:
            self.subjects[subject] = []
        
        self.subjects[subject].append({
            'message': message,
            'timestamp': time.time()
        })
        
        return web.Response(text="OK")
    
    async def subscribe(self, request):
        """订阅消息"""
        subject = request.match_info['subject']
        messages = self.subjects.get(subject, [])
        return web.Response(text=json.dumps(messages))

class MockInfrastructureManager:
    """模拟基础设施管理器"""
    
    def __init__(self):
        self.servers = {}
        self.running = False
    
    async def start_redis_mock(self):
        """启动模拟Redis服务器"""
        try:
            redis_server = MockRedisServer()
            runner = web.AppRunner(redis_server.app)
            await runner.setup()
            site = web.TCPSite(runner, 'localhost', 6379)
            await site.start()
            self.servers['redis'] = runner
            print("✅ 模拟Redis服务器启动成功 (端口6379)")
            return True
        except Exception as e:
            print(f"❌ 模拟Redis启动失败: {e}")
            return False
    
    async def start_clickhouse_mock(self):
        """启动模拟ClickHouse服务器"""
        try:
            clickhouse_server = MockClickHouseServer()
            runner = web.AppRunner(clickhouse_server.app)
            await runner.setup()
            site = web.TCPSite(runner, 'localhost', 8123)
            await site.start()
            self.servers['clickhouse'] = runner
            print("✅ 模拟ClickHouse服务器启动成功 (端口8123)")
            return True
        except Exception as e:
            print(f"❌ 模拟ClickHouse启动失败: {e}")
            return False
    
    async def start_nats_mock(self):
        """启动模拟NATS服务器"""
        try:
            nats_server = MockNATSServer()
            runner = web.AppRunner(nats_server.app)
            await runner.setup()
            site = web.TCPSite(runner, 'localhost', 8222)  # 使用8222端口进行HTTP健康检查
            await site.start()
            self.servers['nats'] = runner
            print("✅ 模拟NATS服务器启动成功 (端口8222)")
            
            # 创建一个简单的TCP监听器在4222端口
            server = await asyncio.start_server(
                self.nats_tcp_handler, 'localhost', 4222
            )
            self.servers['nats_tcp'] = server
            print("✅ 模拟NATS TCP服务器启动成功 (端口4222)")
            return True
        except Exception as e:
            print(f"❌ 模拟NATS启动失败: {e}")
            return False
    
    async def nats_tcp_handler(self, reader, writer):
        """处理NATS TCP连接"""
        # 发送NATS INFO消息
        info_msg = 'INFO {"server_id":"mock-nats","version":"2.0.0","proto":1,"git_commit":"","go":"go1.18","host":"localhost","port":4222,"max_payload":1048576,"client_id":1}\r\n'
        writer.write(info_msg.encode())
        await writer.drain()
        
        try:
            while True:
                data = await reader.read(1024)
                if not data:
                    break
                
                # 简单的PING/PONG处理
                message = data.decode().strip()
                if message == 'PING':
                    writer.write(b'PONG\r\n')
                    await writer.drain()
                elif message.startswith('CONNECT'):
                    writer.write(b'+OK\r\n')
                    await writer.drain()
                
        except Exception:
            pass
        finally:
            writer.close()
            await writer.wait_closed()
    
    async def start_all_services(self):
        """启动所有模拟服务"""
        print("🚀 启动MarketPrism模拟基础设施服务")
        print("=" * 50)
        
        success_count = 0
        total_services = 3
        
        # 启动模拟Redis
        if await self.start_redis_mock():
            success_count += 1
        
        # 启动模拟ClickHouse
        if await self.start_clickhouse_mock():
            success_count += 1
        
        # 启动模拟NATS
        if await self.start_nats_mock():
            success_count += 1
        
        print("\n" + "=" * 50)
        print(f"📊 模拟服务启动结果: {success_count}/{total_services}")
        
        if success_count == total_services:
            print("🎉 所有模拟基础设施服务启动成功！")
            print("💡 系统已准备就绪，可以运行验证测试")
            self.running = True
            return True
        else:
            print("⚠️ 部分模拟服务启动失败")
            return False
    
    async def keep_running(self):
        """保持服务运行"""
        print("\n🔄 模拟基础设施服务正在运行...")
        print("按 Ctrl+C 停止服务")
        
        try:
            while self.running:
                await asyncio.sleep(1)
        except KeyboardInterrupt:
            print("\n⏹️ 正在停止模拟基础设施服务...")
            await self.stop_all_services()
    
    async def stop_all_services(self):
        """停止所有服务"""
        for name, server in self.servers.items():
            try:
                if hasattr(server, 'cleanup'):
                    await server.cleanup()
                elif hasattr(server, 'close'):
                    server.close()
                    if hasattr(server, 'wait_closed'):
                        await server.wait_closed()
                print(f"✅ {name} 服务已停止")
            except Exception as e:
                print(f"❌ 停止 {name} 服务失败: {e}")
        
        self.running = False
        print("🎉 所有模拟服务已停止")

async def main():
    """主函数"""
    manager = MockInfrastructureManager()
    
    success = await manager.start_all_services()
    
    if success:
        print("\n🎯 模拟基础设施已就绪!")
        print("现在可以在另一个终端运行验证测试:")
        print("python scripts/quick_fix_verification.py")
        
        # 保持服务运行
        await manager.keep_running()
    else:
        print("\n❌ 模拟基础设施启动失败")
        return 1
    
    return 0

if __name__ == "__main__":
    try:
        result = asyncio.run(main())
        sys.exit(result)
    except KeyboardInterrupt:
        print("\n⏹️ 服务已停止")
        sys.exit(0)