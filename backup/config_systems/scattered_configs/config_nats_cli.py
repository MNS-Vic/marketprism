#!/usr/bin/env python
# coding: utf-8

import subprocess
import sys
import time
import os
import json

def run_command(command):
    """运行命令并返回结果"""
    try:
        result = subprocess.run(
            command,
            shell=True,
            check=True,
            capture_output=True,
            text=True
        )
        return result.stdout
    except subprocess.CalledProcessError as e:
        print(f"命令执行失败: {e}")
        print(f"错误输出: {e.stderr}")
        return None

def create_stream_cli(stream_name, subjects, description, retention="limits", discard="old", max_age="24h", storage="file"):
    """使用nats命令创建流"""
    subjects_str = " ".join([f'--subjects="{s}"' for s in (subjects if isinstance(subjects, list) else [subjects])])
    
    # 构建命令
    command = f'docker exec marketprism-nats-1 nats stream add {stream_name} {subjects_str} --retention={retention} --storage={storage} --max-age={max_age} --description="{description}"'
    
    # 检查流是否已存在
    check_cmd = f'docker exec marketprism-nats-1 nats stream info {stream_name} --json'
    check_result = run_command(check_cmd)
    
    if check_result and "stream_name" in check_result:
        print(f"[OK] 流 {stream_name} 已存在，跳过创建")
        return True
    
    # 创建流
    print(f"创建流: {stream_name}")
    result = run_command(command)
    
    if result and "created" in result.lower():
        print(f"[OK] 成功创建流 {stream_name}")
        return True
    else:
        print(f"[ERROR] 创建流 {stream_name} 失败")
        # 尝试使用另一种命令
        alt_cmd = f'docker exec marketprism-nats-1 nats str create {stream_name} {subjects_str} --retention={retention} --storage={storage} --max-age={max_age}'
        alt_result = run_command(alt_cmd)
        if alt_result and "created" in alt_result.lower():
            print(f"[OK] 成功创建流 {stream_name} (通过备用命令)")
            return True
        else:
            print(f"[ERROR] 通过备用命令创建流 {stream_name} 也失败")
            return False

def configure_streams_cli():
    """使用CLI配置所有流"""
    print("===== 使用NATS CLI配置流 =====")
    
    # 检查NATS容器是否运行
    check_cmd = 'docker ps | findstr "nats"'
    result = run_command(check_cmd)
    
    if not result or "marketprism-nats" not in result:
        print("[ERROR] NATS容器未运行，请先启动容器")
        return False
    
    # 需要配置的流
    streams = [
        {
            "name": "ORDERS",
            "subjects": ["market.orders.*", "market.orders.>"],
            "description": "市场订单数据流"
        },
        {
            "name": "TRADES",
            "subjects": ["market.trades.*", "market.trades.>"],
            "description": "市场交易数据流"
        },
        {
            "name": "ORDERBOOKS",
            "subjects": ["market.orderbooks.*", "market.orderbooks.>"],
            "description": "订单簿数据流"
        },
        {
            "name": "FUNDINGRATES",
            "subjects": ["market.funding.*", "market.funding.>"],
            "description": "资金费率数据流"
        },
        {
            "name": "OPENINTEREST",
            "subjects": ["market.openinterest.*", "market.openinterest.>"],
            "description": "未平仓合约数据流"
        },
        {
            "name": "ARCHIVE",
            "subjects": ["archive.*", "archive.>"],
            "description": "数据归档流",
            "max_age": "72h"
        },
        {
            "name": "SYSTEM",
            "subjects": ["system.*", "system.>"],
            "description": "系统消息流"
        }
    ]
    
    # 创建流
    success_count = 0
    for stream in streams:
        max_age = stream.get("max_age", "24h")
        if create_stream_cli(
            stream["name"], 
            stream["subjects"], 
            stream["description"],
            max_age=max_age
        ):
            success_count += 1
    
    print(f"\n流配置结果: {success_count}/{len(streams)} 个流配置成功")
    return success_count == len(streams)

def test_streams_cli():
    """使用CLI测试已创建的流"""
    print("\n测试NATS流...")
    
    command = 'docker exec marketprism-nats-1 nats stream ls --json'
    result = run_command(command)
    
    if result:
        try:
            streams = json.loads(result)
            print(f"总计 {len(streams)} 个流:")
            for stream in streams:
                print(f"  - {stream.get('name')}: {stream.get('config', {}).get('description', '无描述')}")
            return True
        except json.JSONDecodeError:
            print(f"[ERROR] 解析流列表失败: 无效的JSON")
            return False
    else:
        print("[ERROR] 获取流列表失败")
        return False

def main():
    """主函数"""
    # 等待NATS服务就绪
    print("等待NATS服务就绪...")
    time.sleep(2)
    
    # 配置所有流
    configure_streams_cli()
    
    # 测试流
    test_streams_cli()
    
    print("\n===== 配置完成 =====")

if __name__ == "__main__":
    main() 