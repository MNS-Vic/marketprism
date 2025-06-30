#!/usr/bin/env python3
"""
简单的aiohttp中间件测试
验证基于官方文档的中间件修复是否正确
"""

import asyncio
import json
from datetime import datetime
from aiohttp import web

# 测试中间件 - 基于aiohttp官方文档
async def test_middleware(request, handler):
    """测试中间件"""
    print(f"🔍 中间件处理: {request.method} {request.path}")
    
    # 在请求中设置数据
    request['middleware_data'] = 'middleware_working'
    
    # 调用处理器
    response = await handler(request)
    
    # 设置响应头
    response.headers['X-Middleware-Test'] = 'success'
    
    print(f"✅ 中间件完成: {response.status}")
    return response

async def health_handler(request):
    """健康检查处理器"""
    middleware_data = request.get('middleware_data', 'not_set')
    
    data = {
        'status': 'healthy',
        'timestamp': datetime.now().isoformat(),
        'middleware_test': middleware_data,
        'message': 'Simple test service'
    }
    
    return web.Response(
        text=json.dumps(data, indent=2),
        content_type='application/json'
    )

async def create_app():
    """创建应用"""
    # 创建应用并添加中间件
    app = web.Application(middlewares=[test_middleware])
    
    # 添加路由
    app.router.add_get('/health', health_handler)
    
    return app

async def main():
    """主函数"""
    print("🧪 启动简单测试服务")
    print("验证aiohttp中间件修复")
    print("=" * 30)
    
    try:
        app = await create_app()
        runner = web.AppRunner(app)
        await runner.setup()
        
        site = web.TCPSite(runner, '0.0.0.0', 8083)
        await site.start()
        
        print("✅ 服务启动成功: http://localhost:8083/health")
        print("🔍 等待测试请求...")
        
        # 保持运行
        while True:
            await asyncio.sleep(1)
            
    except KeyboardInterrupt:
        print("\n⏹️ 服务停止")
    except Exception as e:
        print(f"❌ 错误: {e}")
        import traceback
        traceback.print_exc()

if __name__ == '__main__':
    asyncio.run(main())
