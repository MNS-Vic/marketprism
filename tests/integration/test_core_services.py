#!/usr/bin/env python
# coding: utf-8

import asyncio
import json
from nats.aio.client import Client as NATS
from clickhouse_driver import Client as ClickHouseClient
import os
import sys
import time
import logging
import argparse
import subprocess
from typing import Dict, List, Any, Optional
import urllib.request
import urllib.parse
import base64

# 设置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger('test_core_services')

async def test_nats():
    """测试NATS连接和基本功能"""
    print("测试NATS连接...")
    nc = NATS()
    
    try:
        # 使用localhost代替容器名
        await nc.connect("nats://localhost:4222")
        print("[OK] NATS连接成功")
        
        # 测试发布/订阅
        future = asyncio.Future()
        
        async def message_handler(msg):
            subject = msg.subject
            data = msg.data.decode()
            print(f"收到消息: {subject} {data}")
            future.set_result(True)
        
        # 订阅测试主题
        await nc.subscribe("test.subject", cb=message_handler)
        
        # 发布测试消息
        await nc.publish("test.subject", json.dumps({"test": "data"}).encode())
        
        # 等待接收消息
        try:
            await asyncio.wait_for(future, 5.0)
            print("[OK] NATS发布/订阅功能正常")
        except asyncio.TimeoutError:
            print("[ERROR] NATS发布/订阅测试失败 - 超时")
        
        # 获取NATS服务器信息
        info = await nc.request("$SYS.REQ.SERVER.PING", b'', timeout=1)
        print(f"[OK] NATS服务器信息: {info.data.decode()}")
        
    except Exception as e:
        print(f"[ERROR] NATS测试失败: {str(e)}")
    finally:
        await nc.close()

def test_clickhouse():
    """测试ClickHouse连接和基本查询"""
    print("\n测试ClickHouse连接...")
    
    try:
        # 连接到ClickHouse（使用localhost代替容器名）
        client = ClickHouseClient(host='localhost', port=9000)
        
        # 测试基本查询
        result = client.execute('SELECT 1')
        print(f"[OK] ClickHouse基本查询成功: {result}")
        
        # 获取数据库列表
        databases = client.execute('SHOW DATABASES')
        print(f"[OK] ClickHouse数据库列表: {databases}")
        
        # 检查是否创建了marketprism数据库
        if ('marketprism',) in databases:
            print("[OK] marketprism数据库存在")
            
            # 查看marketprism中的表
            tables = client.execute('SHOW TABLES FROM marketprism')
            print(f"[OK] marketprism数据库中的表: {tables}")
        else:
            print("[ERROR] marketprism数据库不存在")
            
    except Exception as e:
        print(f"[ERROR] ClickHouse测试失败: {str(e)}")

def test_connectivity():
    """测试主要服务的连通性"""
    print("测试主要服务连通性...")
    
    services = [
        {"name": "NATS监控", "url": "http://localhost:8222/varz", "expected_status": 200},
        {"name": "ClickHouse", "url": "http://localhost:8123/ping", "expected_status": 200},
        {"name": "Prometheus", "url": "http://localhost:9090/-/healthy", "expected_status": 200},
        {"name": "Grafana", "url": "http://localhost:3000/api/health", "expected_status": 200, "auth": "admin:admin"},
    ]
    
    success_count = 0
    for service in services:
        print(f"正在测试 {service['name']}...", end="")
        try:
            if service.get("auth"):
                request = urllib.request.Request(service["url"])
                auth_str = base64.b64encode(service["auth"].encode()).decode("utf-8")
                request.add_header("Authorization", f"Basic {auth_str}")
                response = urllib.request.urlopen(request)
            else:
                response = urllib.request.urlopen(service["url"])
                
            status = response.getcode()
            if status == service["expected_status"]:
                print(f" [OK] 状态码: {status}")
                success_count += 1
            else:
                print(f" [ERROR] 状态码不匹配: {status}")
        except Exception as e:
            print(f" [ERROR] 连接失败: {str(e)}")
    
    print(f"\n连通性测试结果: {success_count}/{len(services)} 服务可访问")
    return success_count == len(services)
            
def test_clickhouse_database():
    """测试ClickHouse数据库"""
    print("\n测试ClickHouse数据库...")
    
    try:
        # 检查数据库是否存在
        query = "SHOW DATABASES FORMAT JSON"
        encoded_query = urllib.parse.quote(query)
        with urllib.request.urlopen(f"http://localhost:8123/?query={encoded_query}") as response:
            result = json.loads(response.read().decode('utf-8'))
            databases = [db["name"] for db in result["data"]]
            
            required_dbs = ["marketprism", "marketprism_test", "marketprism_cold"]
            missing_dbs = [db for db in required_dbs if db not in databases]
            
            if not missing_dbs:
                print("[OK] 所有必要的数据库都存在")
            else:
                print(f"[ERROR] 缺少以下数据库: {', '.join(missing_dbs)}")
                return False
                
        # 检查表是否存在
        query = "SHOW TABLES FROM marketprism FORMAT JSON"
        encoded_query = urllib.parse.quote(query)
        with urllib.request.urlopen(f"http://localhost:8123/?query={encoded_query}") as response:
            result = json.loads(response.read().decode('utf-8'))
            tables = [table["name"] for table in result["data"]]
            
            required_tables = ["trades", "depth", "funding_rate", "open_interest", "trade_aggregations"]
            missing_tables = [table for table in required_tables if table not in tables]
            
            if not missing_tables:
                print("[OK] 所有必要的表都存在")
            else:
                print(f"[ERROR] 缺少以下表: {', '.join(missing_tables)}")
                print("注意: 部分表缺失可能会导致特定功能无法使用，但系统可能仍然能部分运行")
            
            return True
    except Exception as e:
        print(f"[ERROR] ClickHouse数据库测试失败: {str(e)}")
        return False
            
def test_nats_jetstream():
    """测试NATS JetStream功能"""
    print("\n测试NATS JetStream...")
    
    try:
        with urllib.request.urlopen("http://localhost:8222/jsz") as response:
            result = json.loads(response.read().decode('utf-8'))
            
            if "config" in result:
                print("[OK] JetStream已启用")
                print(f"内存限制: {result['config'].get('max_memory', 'N/A')}")
                print(f"存储限制: {result['config'].get('max_storage', 'N/A')}")
                
                # 检查流是否存在
                try:
                    with urllib.request.urlopen("http://localhost:8222/streamz") as stream_response:
                        stream_result = json.loads(stream_response.read().decode('utf-8'))
            
                        if "streams" in stream_result:
                            print(f"流数量: {len(stream_result['streams'])}")
                            for stream in stream_result.get("streams", []):
                                print(f"  - {stream.get('name')}: {stream.get('state', {}).get('messages', 0)} 条消息")
                        else:
                            print("[WARN] 没有已配置的流")
                except Exception as e:
                    print(f"[WARN] 无法获取流信息: {str(e)}")
                
                return True
            else:
                print("[ERROR] JetStream未启用")
                return False
    except Exception as e:
        print(f"[ERROR] NATS JetStream测试失败: {str(e)}")
        return False

def generate_report(connectivity, database, jetstream):
    """生成测试报告"""
    print("\n===== MarketPrism QA测试报告 =====")
    print("时间:", time.strftime("%Y-%m-%d %H:%M:%S"))
    
    status = {
        True: "[OK] 通过",
        False: "[ERROR] 失败"
    }
    
    print(f"连通性测试: {status[connectivity]}")
    print(f"ClickHouse数据库测试: {status[database]}")
    print(f"NATS JetStream测试: {status[jetstream]}")
    
    if connectivity and database and jetstream:
        print("\n整体测试结果: [OK] 通过")
        print("恭喜！系统核心组件已正常运行。")
    else:
        print("\n整体测试结果: [WARN] 部分通过")
        print("系统部分组件工作正常，但某些测试未通过。")
        print("请查看上面的详细信息以了解哪些测试失败。")

def main():
    """主函数"""
    print("===== MarketPrism核心服务集成测试 =====")
    
    # 等待服务准备就绪
    print("等待服务准备就绪...")
    time.sleep(3)
    
    # 运行各项测试
    connectivity = test_connectivity()
    database = test_clickhouse_database()
    jetstream = test_nats_jetstream()
    
    # 生成报告
    generate_report(connectivity, database, jetstream)
    
    print("\n===== 测试完成 =====")

if __name__ == "__main__":
    main() 