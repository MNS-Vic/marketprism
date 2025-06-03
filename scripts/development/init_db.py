#!/usr/bin/env python
# coding: utf-8

import urllib.request
import urllib.parse
import json
import sys
import os
import time

def execute_sql(sql, max_retries=3, retry_interval=2):
    """执行SQL语句，支持重试"""
    encoded_query = urllib.parse.quote(sql)
    url = f"http://localhost:8123/?query={encoded_query}"
    
    for attempt in range(max_retries):
        try:
            with urllib.request.urlopen(url) as response:
                result = response.read().decode('utf-8')
                print(f"✅ 执行SQL成功: {sql[:50]}...")
                return True
        except Exception as e:
            print(f"❌ 尝试 {attempt+1}/{max_retries} 执行SQL失败: {str(e)}")
            print(f"SQL: {sql[:100]}...")
            if attempt < max_retries - 1:
                print(f"等待 {retry_interval} 秒后重试...")
                time.sleep(retry_interval)
    
    print(f"⚠️ 达到最大重试次数，SQL执行失败")
    return False

def read_sql_file(file_path):
    """从文件读取SQL语句"""
    try:
        with open(file_path, 'r') as file:
            sql_content = file.read()
            return sql_content
    except Exception as e:
        print(f"❌ 读取SQL文件 {file_path} 失败: {str(e)}")
        return None

def init_database_from_file():
    """从文件初始化数据库"""
    sql_content = read_sql_file('create_tables.sql')
    if sql_content:
        # 将SQL文件内容按分号分割为多个语句
        sql_statements = [stmt.strip() for stmt in sql_content.split(';') if stmt.strip()]
        
        success_count = 0
        total_statements = len(sql_statements)
        
        print(f"🔄 开始执行 {total_statements} 条SQL语句...")
        
        for i, sql in enumerate(sql_statements):
            print(f"[{i+1}/{total_statements}] 执行SQL...")
            if execute_sql(sql):
                success_count += 1
        
        print(f"📊 SQL执行结果: {success_count}/{total_statements} 条语句成功")
        return success_count == total_statements
    else:
        return False

def init_database_manually():
    """手动创建数据库和表"""
    print("🔄 开始手动创建数据库和表...")
    
    # 创建数据库
    success = True
    success &= execute_sql("CREATE DATABASE IF NOT EXISTS marketprism")
    success &= execute_sql("CREATE DATABASE IF NOT EXISTS marketprism_test")
    success &= execute_sql("CREATE DATABASE IF NOT EXISTS marketprism_cold")

    # 创建交易数据表
    success &= execute_sql("""
    CREATE TABLE IF NOT EXISTS marketprism.trades (
        id UInt64,
        exchange LowCardinality(String),
        symbol LowCardinality(String),
        trade_id String,
        price Float64,
        quantity Float64,
        side LowCardinality(String),
        trade_time DateTime,
        receive_time DateTime,
        is_best_match Bool DEFAULT true
    ) ENGINE = MergeTree()
    ORDER BY (exchange, symbol, trade_time)
    """)

    # 创建深度数据表
    success &= execute_sql("""
    CREATE TABLE IF NOT EXISTS marketprism.depth (
        id UInt64,
        exchange LowCardinality(String),
        symbol LowCardinality(String),
        update_id UInt64,
        bids String,
        asks String,
        time DateTime,
        receive_time DateTime
    ) ENGINE = MergeTree()
    ORDER BY (exchange, symbol, time)
    """)

    # 创建资金费率表
    success &= execute_sql("""
    CREATE TABLE IF NOT EXISTS marketprism.funding_rate (
        id UInt64,
        exchange LowCardinality(String),
        symbol LowCardinality(String),
        rate Float64,
        time DateTime,
        receive_time DateTime
    ) ENGINE = MergeTree()
    ORDER BY (exchange, symbol, time)
    """)

    # 创建未平仓合约表
    success &= execute_sql("""
    CREATE TABLE IF NOT EXISTS marketprism.open_interest (
        id UInt64,
        exchange LowCardinality(String),
        symbol LowCardinality(String),
        open_interest Float64,
        time DateTime,
        receive_time DateTime
    ) ENGINE = MergeTree()
    ORDER BY (exchange, symbol, time)
    """)

    # 创建交易聚合表
    success &= execute_sql("""
    CREATE TABLE IF NOT EXISTS marketprism.trade_aggregations (
        exchange LowCardinality(String),
        symbol LowCardinality(String),
        interval_type LowCardinality(String),
        interval_start DateTime,
        open_price Float64,
        high_price Float64,
        low_price Float64,
        close_price Float64,
        volume Float64,
        vwap Float64,
        trade_count UInt32,
        created_at DateTime DEFAULT now()
    ) ENGINE = MergeTree()
    ORDER BY (exchange, symbol, interval_type, interval_start)
    """)

    print(f"{'✅ 数据库手动初始化完成' if success else '⚠️ 数据库手动初始化部分失败'}")
    return success

def check_clickhouse_connection():
    """检查ClickHouse连接状态"""
    print("🔄 检查ClickHouse连接...")
    try:
        with urllib.request.urlopen("http://localhost:8123/ping") as response:
            if response.status == 200:
                print("✅ ClickHouse服务器连接正常")
                return True
            else:
                print(f"❌ ClickHouse连接失败，状态码: {response.status}")
                return False
    except Exception as e:
        print(f"❌ ClickHouse连接失败: {str(e)}")
        return False

if __name__ == "__main__":
    print("📋 MarketPrism数据库初始化脚本")
    
    # 等待ClickHouse服务启动
    for attempt in range(5):
        if check_clickhouse_connection():
            break
        else:
            wait_time = 5
            print(f"等待 {wait_time} 秒后重试连接ClickHouse...")
            time.sleep(wait_time)
    
    # 先尝试从文件初始化，如果失败则手动创建
    if os.path.exists('create_tables.sql'):
        print("📄 从SQL文件初始化数据库...")
        if init_database_from_file():
            print("✅ 数据库初始化成功")
            sys.exit(0)
        else:
            print("⚠️ 从SQL文件初始化失败，尝试手动创建...")
    else:
        print("⚠️ SQL文件不存在，使用内置SQL语句初始化...")
    
    # 手动初始化
    if init_database_manually():
        print("✅ 数据库初始化成功")
        sys.exit(0)
    else:
        print("❌ 数据库初始化失败")
        sys.exit(1) 