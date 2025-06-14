#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
MarketPrism集成测试的共享fixtures
"""

from datetime import datetime, timezone
import os
import sys
import pytest
import logging
import docker
import time
from typing import Dict, Any, Generator

# 添加项目根目录到Python路径
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '../../')))

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger('integration_test')

@pytest.fixture(scope="session")
def integration_config() -> Dict[str, Any]:
    """
    提供集成测试的配置
    如果在CI环境中运行，将使用环境变量中的配置
    否则使用本地测试环境配置
    """
    is_ci = os.environ.get("CI", "false").lower() == "true"
    
    if is_ci:
        # CI环境配置
        config = {
            "clickhouse": {
                "host": os.environ.get("TEST_CH_HOST", "clickhouse"),
                "port": int(os.environ.get("TEST_CH_PORT", "9000")),
                "database": os.environ.get("TEST_CH_DB", "marketprism_test"),
                "user": os.environ.get("TEST_CH_USER", "default"),
                "password": os.environ.get("TEST_CH_PASSWORD", "")
            },
            "nats": {
                "url": os.environ.get("TEST_NATS_URL", "nats://nats:4222"),
                "stream": os.environ.get("TEST_NATS_STREAM", "TEST_MARKET_DATA")
            }
        }
    else:
        # 本地测试环境配置
        config = {
            "clickhouse": {
                "host": "localhost",
                "port": 9000,
                "database": "marketprism_test",
                "user": "default",
                "password": ""
            },
            "nats": {
                "url": "nats://localhost:4222",
                "stream": "TEST_MARKET_DATA"
            }
        }
    
    return config

@pytest.fixture(scope="session")
def docker_compose_project() -> Generator[None, None, None]:
    """
    启动和停止Docker Compose中的测试服务
    """
    if os.environ.get("SKIP_DOCKER", "false").lower() == "true":
        # 跳过启动Docker服务
        logger.info("跳过Docker Compose环境启动")
        yield
        return

    logger.info("启动集成测试Docker Compose环境")
    try:
        # 初始化Docker客户端
        client = docker.from_env()
        
        # 检查是否已有服务运行
        test_services = {
            "clickhouse": False,
            "nats": False
        }
        
        for container in client.containers.list():
            for service in test_services:
                if service in container.name:
                    test_services[service] = True
        
        # 启动Docker Compose环境（如果需要）
        missing_services = [s for s, running in test_services.items() if not running]
        if missing_services:
            logger.info(f"需要启动的服务: {missing_services}")
            
            # 执行docker-compose up (仅限部分服务)
            import subprocess
            cmd = ["docker", "compose", "-f", "docker-compose.testing.yml", "up", "-d"] + missing_services
            subprocess.run(cmd, check=True)
            
            # 等待服务启动
            logger.info("等待服务启动...")
            time.sleep(10)  # 等待服务完全启动
        else:
            logger.info("所有测试服务已运行")
            
        # 提供环境给测试使用
        yield
        
        # 保留Docker容器供其他测试使用
        logger.info("保留Docker Compose环境以供其他测试使用")
        
    except Exception as e:
        logger.error(f"设置Docker Compose环境时出错: {str(e)}")
        # 出错时也尝试提供环境
        yield

@pytest.fixture(scope="function")
def prepare_test_stream(integration_config) -> Generator[None, None, None]:
    """
    准备NATS测试流
    """
    import asyncio
    import nats
    from nats.js.api import StreamConfig
    
    async def setup_stream():
        # 连接NATS
        nc = await nats.connect(integration_config["nats"]["url"])
        js = nc.jetstream()
        
        # 创建测试流
        stream_name = integration_config["nats"]["stream"]
        stream_config = StreamConfig(
            name=stream_name,
            subjects=[
                "TEST.MARKET.>",
            ],
            retention="limits",
            max_msgs=10000,
            storage="memory",
        )
        
        try:
            # 检查流是否存在，如果存在则删除
            await js.stream_info(stream_name)
            await js.delete_stream(stream_name)
        except:
            # 流不存在，继续创建
            pass
            
        # 创建新的测试流
        await js.add_stream(config=stream_config)
        logger.info(f"创建测试流: {stream_name}")
        
        # 关闭连接
        await nc.close()
    
    # 执行异步设置
    asyncio.run(setup_stream())
    
    yield
    
    # 测试后清理 - 移除测试流
    async def cleanup_stream():
        # 连接NATS
        nc = await nats.connect(integration_config["nats"]["url"])
        js = nc.jetstream()
        
        # 删除测试流
        try:
            stream_name = integration_config["nats"]["stream"]
            await js.delete_stream(stream_name)
            logger.info(f"删除测试流: {stream_name}")
        except Exception as e:
            logger.warning(f"清理测试流时出错: {str(e)}")
        
        # 关闭连接
        await nc.close()
    
    # 执行异步清理
    asyncio.run(cleanup_stream())

# 将集成配置作为测试配置提供
@pytest.fixture(scope="session")
def test_config(integration_config) -> Dict[str, Any]:
    """提供测试配置"""
    return integration_config 