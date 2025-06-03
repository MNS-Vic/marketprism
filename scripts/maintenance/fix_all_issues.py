#!/usr/bin/env python3
"""
修复项目中的各种问题，包括：
1. NATS流配置
2. ClickHouse表
3. 代理配置
4. 服务健康状态
"""

import os
import sys
import json
import time
import asyncio
import subprocess
from typing import Dict, List, Optional, Any, Tuple

import nats
from nats.js.api import StreamConfig

# 导入集中配置模块
import config.app_config
from config.app_config import NetworkConfig, DBConfig, MQConfig, AppConfig

# 设置日志
import logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger("fix_all_issues")

# NATS流配置
STREAM_CONFIGS = [
    {
        "name": "MARKET_DATA",
        "subjects": ["binance.>", "market.>"],
        "retention": "limits",
        "max_age": 86400000000000,  # 1天(纳秒)
        "storage": "file",
        "num_replicas": 1,
        "description": "市场数据流, 包含所有交易所的市场数据"
    },
    {
        "name": "KLINES",
        "subjects": ["klines.>"],
        "retention": "limits",
        "max_age": 2592000000000000,  # 30天(纳秒)
        "storage": "file",
        "num_replicas": 1,
        "description": "K线数据流"
    },
    {
        "name": "TRADES",
        "subjects": ["trades.>"],
        "retention": "limits", 
        "max_age": 86400000000000,  # 1天(纳秒)
        "storage": "file",
        "num_replicas": 1,
        "description": "交易数据流"
    },
    {
        "name": "ORDERS",
        "subjects": ["orders.>"],
        "retention": "limits",
        "max_age": 86400000000000,  # 1天(纳秒)
        "storage": "file",
        "num_replicas": 1,
        "description": "订单数据流"
    },
    {
        "name": "DLQ",
        "subjects": ["dlq.>"],
        "retention": "limits",
        "max_age": 604800000000000,  # 7天(纳秒)
        "storage": "file",
        "num_replicas": 1,
        "description": "死信队列"
    }
]

async def check_and_fix_nats_streams() -> bool:
    """检查并修复NATS流配置"""
    try:
        # 使用配置获取NATS连接URL
        nats_url = MQConfig.NATS_URL
        logger.info(f"连接到NATS服务器: {nats_url}")
        
        # 尝试连接NATS服务器
        nc = await nats.connect(nats_url)
        js = nc.jetstream()
        
        # 检查现有流
        streams_info = await js.streams_info()
        existing_streams = {stream.config.name: stream for stream in streams_info}
        
        # 检查所需流
        all_streams_ok = True
        for stream_config in STREAM_CONFIGS:
            stream_name = stream_config["name"]
            
            if stream_name in existing_streams:
                logger.info(f"流 {stream_name} 已存在")
                
                # 可以检查配置并更新(此处简化处理)
                current_config = existing_streams[stream_name].config
                
                # 检查主题是否需要更新
                if set(current_config.subjects) != set(stream_config["subjects"]):
                    logger.warning(f"流 {stream_name} 主题不匹配，正在更新...")
                    try:
                        # 创建更新的配置
                        updated_config = StreamConfig(
                            name=stream_name,
                            subjects=stream_config["subjects"],
                            description=stream_config.get("description", ""),
                            retention=stream_config["retention"],
                            max_age=stream_config["max_age"],
                            storage=stream_config["storage"],
                            num_replicas=stream_config["num_replicas"]
                        )
                        
                        # 更新流
                        await js.update_stream(updated_config)
                        logger.info(f"✓ 流 {stream_name} 已更新")
                    except Exception as e:
                        logger.error(f"× 更新流 {stream_name} 失败: {e}")
                        all_streams_ok = False
            else:
                logger.warning(f"流 {stream_name} 不存在，正在创建...")
                try:
                    # 创建流配置
                    stream_cfg = StreamConfig(
                        name=stream_name,
                        subjects=stream_config["subjects"],
                        description=stream_config.get("description", ""),
                        retention=stream_config["retention"],
                        max_age=stream_config["max_age"],
                        storage=stream_config["storage"],
                        num_replicas=stream_config["num_replicas"]
                    )
                    
                    # 创建流
                    await js.add_stream(stream_cfg)
                    logger.info(f"✓ 创建流 {stream_name} 成功")
                except Exception as e:
                    logger.error(f"× 创建流 {stream_name} 失败: {e}")
                    all_streams_ok = False
        
        # 检查NATS流中的消息数量
        for stream_name in [cfg["name"] for cfg in STREAM_CONFIGS]:
            try:
                stream_info = await js.stream_info(stream_name)
                logger.info(f"流 {stream_name} 包含 {stream_info.state.messages} 条消息")
            except Exception as e:
                logger.error(f"获取流 {stream_name} 信息失败: {e}")
                
        await nc.close()
        
        if all_streams_ok:
            logger.info("✓ NATS流配置检查完毕，全部正常")
        else:
            logger.warning("! NATS流配置检查完毕，部分存在问题")
            
        return all_streams_ok
        
    except Exception as e:
        logger.error(f"检查NATS流失败: {e}")
        return False

async def check_proxy_settings() -> Tuple[bool, Optional[str]]:
    """检查代理设置"""
    # 检查当前配置中的代理设置
    use_proxy = NetworkConfig.USE_PROXY
    http_proxy = NetworkConfig.HTTP_PROXY
    https_proxy = NetworkConfig.HTTPS_PROXY
    
    if not use_proxy or (not http_proxy and not https_proxy):
        logger.info("未配置代理")
        return True, None
        
    # 打印当前代理配置
    logger.info(f"检测到HTTP代理: {http_proxy}")
    logger.info(f"检测到HTTPS代理: {https_proxy}")
    
    # 获取HTTP代理URL
    proxy_url = http_proxy or https_proxy
    
    if not proxy_url:
        logger.warning("代理配置不完整，未找到HTTP或HTTPS代理")
        return False, None
    
    # 检查代理可用性的命令
    check_cmd = f"python check_proxy.py"
    
    try:
        # 设置代理环境变量
        env = os.environ.copy()
        env['USE_PROXY'] = 'true'
        if http_proxy:
            env['HTTP_PROXY'] = http_proxy
        if https_proxy:
            env['HTTPS_PROXY'] = https_proxy
            
        # 执行检查
        result = subprocess.run(check_cmd, shell=True, env=env, capture_output=True, text=True)
        
        if result.returncode == 0:
            logger.info(f"✓ 代理检查成功: {result.stdout.strip()}")
            return True, proxy_url
        else:
            logger.error(f"× 代理检查失败: {result.stderr.strip()}")
            return False, proxy_url
            
    except Exception as e:
        logger.error(f"检查代理失败: {e}")
        return False, proxy_url

async def check_nats_health() -> bool:
    """检查NATS健康状态"""
    try:
        # 连接到NATS
        nats_url = MQConfig.NATS_URL
        logger.info(f"检查NATS健康状态: {nats_url}")
        
        # 尝试连接NATS服务器
        nc = await nats.connect(nats_url)
        
        # 执行简单的发布/订阅测试
        test_subject = "healthcheck.test"
        test_message = f"test_{int(time.time())}"
        received_messages = []
        
        # 创建订阅
        sub = await nc.subscribe(test_subject)
        
        # 发布消息
        await nc.publish(test_subject, test_message.encode())
        
        # 等待消息接收
        try:
            msg = await asyncio.wait_for(sub.next_msg(), timeout=5.0)
            received = msg.data.decode()
            received_messages.append(received)
        except asyncio.TimeoutError:
            logger.error("等待NATS消息超时")
        
        # 取消订阅并关闭连接
        await sub.unsubscribe()
        await nc.close()
        
        # 验证测试结果
        if received_messages and received_messages[0] == test_message:
            logger.info("✓ NATS健康检查成功")
            return True
        else:
            logger.error(f"× NATS健康检查失败: 发送 '{test_message}', 接收 {received_messages}")
            return False
            
    except Exception as e:
        logger.error(f"NATS健康检查失败: {e}")
        return False

async def check_services_health() -> Dict[str, bool]:
    """检查基础服务健康状态"""
    services = {
        "nats": False,
        "clickhouse": False,
        "go-collector": False,
        "data-normalizer": False
    }
    
    # 检查NATS
    services["nats"] = await check_nats_health()
    
    # 检查ClickHouse (使用简单的HTTP请求)
    try:
        clickhouse_host = DBConfig.CLICKHOUSE_HOST
        clickhouse_port = DBConfig.CLICKHOUSE_PORT
        
        import aiohttp
        async with aiohttp.ClientSession() as session:
            async with session.get(f"http://{clickhouse_host}:{clickhouse_port}/ping", timeout=5.0) as response:
                if response.status == 200:
                    content = await response.text()
                    if content.strip() == "Ok.":
                        logger.info("✓ ClickHouse健康检查成功")
                        services["clickhouse"] = True
                    else:
                        logger.error(f"× ClickHouse健康检查失败: 响应内容 {content}")
                else:
                    logger.error(f"× ClickHouse健康检查失败: 状态码 {response.status}")
    except Exception as e:
        logger.error(f"ClickHouse健康检查异常: {e}")
    
    # 检查go-collector (简单检查进程)
    try:
        result = subprocess.run("pgrep -f 'go.*collector'", shell=True, capture_output=True, text=True)
        if result.returncode == 0:
            logger.info("✓ Go收集器进程检查成功")
            services["go-collector"] = True
        else:
            logger.warning("! Go收集器进程未运行")
    except Exception as e:
        logger.error(f"检查Go收集器进程失败: {e}")
    
    # 检查data-normalizer
    try:
        result = subprocess.run("pgrep -f 'data-normalizer'", shell=True, capture_output=True, text=True)
        if result.returncode == 0:
            logger.info("✓ 数据归一化服务进程检查成功")
            services["data-normalizer"] = True
        else:
            logger.warning("! 数据归一化服务进程未运行")
    except Exception as e:
        logger.error(f"检查数据归一化服务进程失败: {e}")
    
    return services

async def main():
    """主函数"""
    try:
        logger.info("==== 开始全面系统问题修复 ====")
        
        # 检查代理设置
        logger.info("\n== 检查代理设置 ==")
        proxy_ok, proxy_url = await check_proxy_settings()
        
        # 检查及修复NATS流
        logger.info("\n== 检查及修复NATS流 ==")
        nats_streams_ok = await check_and_fix_nats_streams()
        
        # 检查服务健康状态
        logger.info("\n== 检查服务健康状态 ==")
        services_health = await check_services_health()
        
        # 总结
        logger.info("\n==== 系统检查总结 ====")
        logger.info(f"代理设置: {'✓ 正常' if proxy_ok else '× 异常'}")
        logger.info(f"NATS流配置: {'✓ 正常' if nats_streams_ok else '× 异常'}")
        
        for service, status in services_health.items():
            logger.info(f"{service}: {'✓ 正常' if status else '× 异常'}")
        
        # 系统整体健康状态
        system_ok = proxy_ok and nats_streams_ok and services_health.get("nats", False) and services_health.get("clickhouse", False)
        
        if system_ok:
            logger.info("\n✓✓✓ 系统整体状态: 正常 ✓✓✓")
        else:
            logger.warning("\n!!! 系统整体状态: 异常 !!!")
            
        # 如果有异常服务，尝试自动重启
        if not all(services_health.values()):
            logger.info("\n== 尝试自动重启异常服务 ==")
            
            if not services_health.get("nats", True):
                logger.info("重启NATS服务...")
                subprocess.run("docker-compose restart nats", shell=True)
            
            if not services_health.get("clickhouse", True):
                logger.info("重启ClickHouse服务...")
                subprocess.run("docker-compose restart clickhouse", shell=True)
        
    except Exception as e:
        logger.error(f"程序执行过程中出错: {e}")
        sys.exit(1)

if __name__ == "__main__":
    asyncio.run(main()) 