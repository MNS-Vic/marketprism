#!/usr/bin/env python3
"""
MarketPrism 监控告警服务 - 基础测试版本
用于验证aiohttp中间件修复是否正确
"""

import asyncio
import json
import time
import logging
from datetime import datetime
from aiohttp import web
import aiohttp_cors

# 配置基础日志
logging.basicConfig(level=logging.INFO)

class BasicMonitoringService:
    """基础监控服务 - 用于测试中间件"""
    
    def __init__(self):
        self.start_time = time.time()
        self.version = "2.1.0-test"
        
    async def health_handler(self, request: web.Request) -> web.Response:
        """健康检查处理器"""
        health_data = {
            'status': 'healthy',
            'version': self.version,
            'timestamp': datetime.now().isoformat(),
            'uptime_seconds': time.time() - self.start_time,
            'middleware_test': 'basic_version'
        }
        
        return web.Response(
            text=json.dumps(health_data, indent=2),
            content_type='application/json'
        )
    
    async def test_middleware_handler(self, request: web.Request) -> web.Response:
        """测试中间件处理器"""
        # 检查中间件是否正确设置了数据
        middleware_data = request.get('middleware_test', 'not_set')
        
        response_data = {
            'message': 'Middleware test endpoint',
            'middleware_data': middleware_data,
            'request_path': request.path,
            'request_method': request.method,
            'timestamp': datetime.now().isoformat()
        }
        
        return web.Response(
            text=json.dumps(response_data, indent=2),
            content_type='application/json'
        )

# 测试中间件
async def test_middleware(request: web.Request, handler):
    """测试中间件 - 基于官方文档的正确实现"""
    print(f"中间件处理请求: {request.method} {request.path}")
    
    # 在请求中设置测试数据
    request['middleware_test'] = 'middleware_working'
    
    # 调用下一个处理器
    response = await handler(request)
    
    # 在响应中添加测试头
    response.headers['X-Middleware-Test'] = 'success'
    
    print(f"中间件处理完成: {response.status}")
    return response

async def create_app():
    """创建应用"""
    # 创建应用并添加中间件
    app = web.Application(middlewares=[test_middleware])
    
    # 创建服务实例
    service = BasicMonitoringService()
    
    # 设置路由
    app.router.add_get('/health', service.health_handler)
    app.router.add_get('/test-middleware', service.test_middleware_handler)
    
    # 配置CORS
    cors = aiohttp_cors.setup(app, defaults={
        "*": aiohttp_cors.ResourceOptions(
            allow_credentials=True,
            expose_headers="*",
            allow_headers="*",
            allow_methods="*"
        )
    })
    
    # 为所有路由添加CORS
    for route in list(app.router.routes()):
        cors.add(route)
    
    print("✅ 基础测试应用创建成功")
    return app

async def main():
    """主函数"""
    try:
        print("🧪 启动MarketPrism基础测试服务")
        print("用于验证aiohttp中间件修复")
        print("=" * 40)
        
        # 创建应用
        app = await create_app()
        
        # 创建运行器
        runner = web.AppRunner(app)
        await runner.setup()
        
        # 创建站点
        site = web.TCPSite(runner, '0.0.0.0', 8083)  # 使用不同端口避免冲突
        await site.start()
        
        print("✅ 服务启动成功")
        print("📍 测试地址:")
        print("   健康检查: http://localhost:8083/health")
        print("   中间件测试: http://localhost:8083/test-middleware")
        print("")
        print("🔍 等待测试请求...")
        
        # 保持服务运行
        try:
            while True:
                await asyncio.sleep(1)
        except KeyboardInterrupt:
            print("\n⏹️ 接收到停止信号")
        
        # 清理
        await site.stop()
        await runner.cleanup()
        print("✅ 服务已停止")
        
    except Exception as e:
        print(f"❌ 服务启动失败: {e}")
        return 1
    
    return 0

if __name__ == '__main__':
    try:
        exit_code = asyncio.run(main())
        exit(exit_code)
    except Exception as e:
        print(f"❌ 启动失败: {e}")
        exit(1)
