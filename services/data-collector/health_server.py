#!/usr/bin/env python3
"""
MarketPrism Data Collector 健康检查HTTP服务器（示例/备用）
注意：当前 Dockerfile 使用 services/data-collector/entrypoint.sh 内置的轻量健康检查，
本文件通常不作为容器入口的一部分，仅供本地或自定义场景参考。
"""

import asyncio
import json
import logging
from datetime import datetime
from aiohttp import web
import os
import sys

# 配置日志
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class HealthServer:
    def __init__(self, port=8086):
        self.port = port
        self.app = web.Application()
        self.setup_routes()
        
    def setup_routes(self):
        """设置路由"""
        self.app.router.add_get('/health', self.health_check)
        self.app.router.add_get('/ping', self.ping)
        self.app.router.add_get('/status', self.status)
        
    async def health_check(self, request):
        """健康检查端点"""
        try:
            # 检查主进程是否存在
            main_process_exists = self.check_main_process()
            
            health_status = {
                "status": "healthy" if main_process_exists else "unhealthy",
                "timestamp": datetime.utcnow().isoformat(),
                "checks": {
                    "main_process": main_process_exists,
                    "server_running": True
                }
            }
            
            status_code = 200 if main_process_exists else 503
            return web.json_response(health_status, status=status_code)
            
        except Exception as e:
            logger.error(f"健康检查失败: {e}")
            return web.json_response({
                "status": "unhealthy",
                "error": str(e),
                "timestamp": datetime.utcnow().isoformat()
            }, status=503)
    
    async def ping(self, request):
        """简单的ping端点"""
        return web.Response(text="pong")
    
    async def status(self, request):
        """详细状态端点"""
        try:
            status_info = {
                "service": "marketprism-data-collector",
                "version": "1.0.0",
                "timestamp": datetime.utcnow().isoformat(),
                "uptime": self.get_uptime(),
                "process_info": {
                    "pid": os.getpid(),
                    "main_process_exists": self.check_main_process()
                }
            }
            return web.json_response(status_info)
            
        except Exception as e:
            logger.error(f"状态检查失败: {e}")
            return web.json_response({
                "error": str(e),
                "timestamp": datetime.utcnow().isoformat()
            }, status=500)
    
    def check_main_process(self):
        """检查主进程是否存在"""
        try:
            # 检查是否有Python进程在运行
            import subprocess
            result = subprocess.run(['pgrep', '-f', 'python'], 
                                  capture_output=True, text=True)
            return result.returncode == 0 and len(result.stdout.strip()) > 0
        except:
            # 如果pgrep不可用，检查/proc/1/cmdline
            try:
                with open('/proc/1/cmdline', 'r') as f:
                    cmdline = f.read()
                    return 'python' in cmdline
            except:
                return True  # 默认认为健康
    
    def get_uptime(self):
        """获取系统运行时间"""
        try:
            with open('/proc/uptime', 'r') as f:
                uptime_seconds = float(f.readline().split()[0])
                return f"{uptime_seconds:.2f}s"
        except:
            return "unknown"
    
    async def start_server(self):
        """启动健康检查服务器"""
        try:
            runner = web.AppRunner(self.app)
            await runner.setup()
            
            site = web.TCPSite(runner, '0.0.0.0', self.port)
            await site.start()
            
            logger.info(f"健康检查服务器启动在端口 {self.port}")
            return runner
            
        except Exception as e:
            logger.error(f"启动健康检查服务器失败: {e}")
            raise

async def main():
    """主函数"""
    health_server = HealthServer()
    runner = await health_server.start_server()
    
    try:
        # 保持服务器运行
        while True:
            await asyncio.sleep(1)
    except KeyboardInterrupt:
        logger.info("收到停止信号，关闭健康检查服务器")
    finally:
        await runner.cleanup()

if __name__ == "__main__":
    asyncio.run(main())
