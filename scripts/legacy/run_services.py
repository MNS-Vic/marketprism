#!/usr/bin/env python3
"""
启动MarketPrism核心服务 (已迁移)

⚠️ 重要通知: 此脚本已过时，推荐使用Docker Compose启动服务:
   docker-compose up -d python-collector

原功能已迁移至python-collector服务，包括:
- NATS流配置
- 数据收集器 
- ClickHouse消费者

此脚本保留用于开发和测试目的。
"""
import os
import sys
import time
import argparse
import signal
import asyncio
import subprocess
import logging

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# 服务脚本路径 (已迁移到python-collector)
NATS_STREAM_SCRIPT = "create_market_data_stream.py"
COLLECTOR_SCRIPT = "services/python-collector/src/marketprism_collector/main.py"
CONSUMER_SCRIPT = None  # 已集成到python-collector中

async def check_nats_running():
    """检查NATS服务是否正在运行"""
    try:
        # 尝试使用nc命令检查NATS端口是否开放
        process = await asyncio.create_subprocess_exec(
            "nc", "-z", "localhost", "4222",
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE
        )
        await process.communicate()
        
        if process.returncode == 0:
            logger.info("NATS服务正在运行")
            return True
        else:
            logger.error("NATS服务未运行，请先启动Docker容器")
            return False
    except:
        # 如果nc命令不可用，尝试使用telnet
        try:
            process = await asyncio.create_subprocess_exec(
                "telnet", "localhost", "4222",
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )
            stdout, stderr = await process.communicate()
            
            if process.returncode == 0:
                logger.info("NATS服务正在运行")
                return True
            else:
                logger.error("NATS服务未运行，请先启动Docker容器")
                return False
        except:
            logger.warning("无法检查NATS服务状态，将假设服务已运行")
            return True

async def check_clickhouse_running():
    """检查ClickHouse服务是否正在运行"""
    try:
        # 尝试使用curl命令检查ClickHouse HTTP接口是否可用
        process = await asyncio.create_subprocess_exec(
            "curl", "-s", "http://localhost:8123/ping",
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE
        )
        stdout, stderr = await process.communicate()
        
        if stdout.decode().strip() == "Ok.":
            logger.info("ClickHouse服务正在运行")
            return True
        else:
            logger.error("ClickHouse服务未运行，请先启动Docker容器")
            return False
    except:
        logger.warning("无法检查ClickHouse服务状态，将假设服务已运行")
        return True

async def run_script(script_path, env=None):
    """运行指定的Python脚本"""
    try:
        # 设置环境变量
        env_vars = os.environ.copy()
        if env:
            env_vars.update(env)
        
        # 启动脚本
        process = await asyncio.create_subprocess_exec(
            sys.executable, script_path,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            env=env_vars
        )
        
        # 返回进程对象，以便后续管理
        return process
    except Exception as e:
        logger.error(f"启动脚本 {script_path} 失败: {str(e)}")
        return None

async def stream_logs(process, name):
    """实时输出进程日志"""
    while True:
        # 读取标准输出
        line = await process.stdout.readline()
        if not line:
            break
        logger.info(f"[{name}] {line.decode().strip()}")
        
        # 检查进程是否仍在运行
        if process.returncode is not None:
            break

class ServiceManager:
    """服务管理器"""
    
    def __init__(self, args):
        """初始化服务管理器"""
        self.args = args
        self.processes = {}
        self.running = False
    
    async def start_services(self):
        """启动所有服务"""
        self.running = True
        
        # 检查依赖服务
        nats_ok = await check_nats_running()
        clickhouse_ok = await check_clickhouse_running()
        
        if not nats_ok or not clickhouse_ok:
            logger.error("依赖服务检查失败，无法启动服务")
            return False
        
        # 配置NATS流
        if not self.args.skip_nats_config:
            logger.info("配置NATS流...")
            nats_process = await run_script(NATS_STREAM_SCRIPT)
            
            if nats_process:
                stdout, stderr = await nats_process.communicate()
                if nats_process.returncode != 0:
                    logger.error(f"NATS流配置失败: {stderr.decode()}")
                    return False
                logger.info("NATS流配置完成")
            else:
                logger.error("NATS流配置失败")
                return False
        
        # 启动数据收集器
        if not self.args.skip_collector:
            logger.info("启动Binance数据收集器...")
            # 设置收集器环境变量
            collector_env = {
                "SYMBOLS": self.args.symbols,
                "USE_PROXY": "true" if self.args.use_proxy else "false"
            }
            
            # 如果指定了代理，设置代理环境变量
            if self.args.proxy:
                collector_env["HTTP_PROXY"] = self.args.proxy
                collector_env["HTTPS_PROXY"] = self.args.proxy
                logger.info(f"使用代理: {self.args.proxy}")
            elif self.args.use_proxy:
                # 使用系统环境变量中的代理
                system_proxy = os.environ.get("HTTP_PROXY", os.environ.get("http_proxy", ""))
                if system_proxy:
                    collector_env["HTTP_PROXY"] = system_proxy
                    collector_env["HTTPS_PROXY"] = system_proxy
                    logger.info(f"使用系统代理: {system_proxy}")
                else:
                    logger.warning("启用了代理但未指定代理地址，将尝试查找可用代理")
            
            # 可配置的超时和重试
            if self.args.request_timeout:
                collector_env["REQUEST_TIMEOUT"] = str(self.args.request_timeout)
            if self.args.max_retries:
                collector_env["MAX_RETRIES"] = str(self.args.max_retries)
            if self.args.retry_delay:
                collector_env["RETRY_DELAY"] = str(self.args.retry_delay)

            # 允许配置API接入点
            if self.args.api_endpoint:
                collector_env["BINANCE_BASE_URL"] = self.args.api_endpoint
                logger.info(f"使用自定义API接入点: {self.args.api_endpoint}")
            
            collector_process = await run_script(COLLECTOR_SCRIPT, collector_env)
            
            if collector_process:
                self.processes["collector"] = collector_process
                # 开始实时输出日志
                asyncio.create_task(stream_logs(collector_process, "Collector"))
                logger.info("Binance数据收集器已启动")
            else:
                logger.error("启动Binance数据收集器失败")
                return False
        
        # 启动ClickHouse消费者
        if not self.args.skip_consumer:
            logger.info("启动ClickHouse数据消费者...")
            consumer_process = await run_script(CONSUMER_SCRIPT)
            
            if consumer_process:
                self.processes["consumer"] = consumer_process
                # 开始实时输出日志
                asyncio.create_task(stream_logs(consumer_process, "Consumer"))
                logger.info("ClickHouse数据消费者已启动")
            else:
                logger.error("启动ClickHouse数据消费者失败")
                return False
        
        return True
    
    async def stop_services(self):
        """停止所有服务"""
        self.running = False
        
        for name, process in self.processes.items():
            if process.returncode is None:  # 进程仍在运行
                logger.info(f"停止 {name} 服务...")
                try:
                    process.terminate()
                    # 等待进程优雅退出
                    try:
                        await asyncio.wait_for(process.wait(), timeout=5.0)
                    except asyncio.TimeoutError:
                        logger.warning(f"{name} 服务未能在5秒内停止，强制终止")
                        process.kill()
                except Exception as e:
                    logger.error(f"停止 {name} 服务失败: {str(e)}")
        
        logger.info("所有服务已停止")
    
    async def wait_for_completion(self):
        """等待所有服务完成"""
        while self.running:
            # 检查所有进程是否仍在运行
            for name, process in list(self.processes.items()):
                if process.returncode is not None:  # 进程已退出
                    logger.warning(f"{name} 服务已退出，返回码: {process.returncode}")
                    del self.processes[name]
            
            # 如果所有进程都已退出，停止运行
            if not self.processes:
                self.running = False
                logger.info("所有服务已退出")
                break
            
            await asyncio.sleep(1)

async def main():
    """主函数"""
    parser = argparse.ArgumentParser(description="启动MarketPrism服务")
    parser.add_argument("--skip-nats-config", action="store_true", help="跳过NATS流配置")
    parser.add_argument("--skip-collector", action="store_true", help="跳过数据收集器")
    parser.add_argument("--skip-consumer", action="store_true", help="跳过ClickHouse消费者")
    parser.add_argument("--symbols", default="BTCUSDT,ETHUSDT", help="要收集的交易对，以逗号分隔")
    parser.add_argument("--use-proxy", action="store_true", help="启用代理")
    parser.add_argument("--proxy", help="指定代理地址，如 http://127.0.0.1:1087")
    parser.add_argument("--request-timeout", type=int, help="请求超时时间（秒）")
    parser.add_argument("--max-retries", type=int, help="最大重试次数")
    parser.add_argument("--retry-delay", type=int, help="重试延迟时间（秒）")
    parser.add_argument("--api-endpoint", help="自定义API接入点，例如 https://api1.binance.com")
    
    args = parser.parse_args()
    
    # 创建服务管理器
    manager = ServiceManager(args)
    
    # 设置信号处理
    loop = asyncio.get_running_loop()
    for sig in (signal.SIGINT, signal.SIGTERM):
        loop.add_signal_handler(sig, lambda: asyncio.create_task(manager.stop_services()))
    
    # 启动服务
    if await manager.start_services():
        # 等待服务完成或被中断
        await manager.wait_for_completion()
    
    # 确保所有服务都已停止
    await manager.stop_services()

if __name__ == "__main__":
    logger.info("启动MarketPrism服务...")
    asyncio.run(main())