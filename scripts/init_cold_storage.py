#!/usr/bin/env python3
"""
冷存储ClickHouse数据库初始化脚本
"""

import clickhouse_connect
import time
import sys
from datetime import datetime

def wait_for_clickhouse(host, port, max_attempts=30):
    """等待ClickHouse服务启动"""
    for attempt in range(max_attempts):
        try:
            client = clickhouse_connect.get_client(host=host, port=port)
            client.ping()
            print(f"✅ ClickHouse冷存储在 {host}:{port} 已准备就绪")
            return client
        except Exception as e:
            print(f"⏱️ 等待ClickHouse冷存储启动... 尝试 {attempt+1}/{max_attempts}")
            time.sleep(2)
    
    raise Exception(f"❌ 无法连接到ClickHouse冷存储 {host}:{port}")

def create_cold_storage_database(client):
    """创建冷存储数据库和表"""
    
    # 创建数据库
    print("📚 创建冷存储数据库...")
    client.command("CREATE DATABASE IF NOT EXISTS marketprism_cold")
    
    # 创建市场数据表（冷存储版本，优化压缩）
    print("📊 创建冷存储市场数据表...")
    create_market_data_sql = """
    CREATE TABLE IF NOT EXISTS marketprism_cold.market_data
    (
        timestamp DateTime64(3) CODEC(Delta, LZ4HC),
        exchange String CODEC(LZ4HC),
        symbol String CODEC(LZ4HC),
        data_type String CODEC(LZ4HC),
        price Float64 CODEC(Delta, LZ4HC),
        volume Float64 CODEC(LZ4HC),
        high Float64 CODEC(Delta, LZ4HC),
        low Float64 CODEC(Delta, LZ4HC),
        open Float64 CODEC(Delta, LZ4HC),
        close Float64 CODEC(Delta, LZ4HC),
        bid_price Float64 CODEC(Delta, LZ4HC),
        ask_price Float64 CODEC(Delta, LZ4HC),
        bid_size Float64 CODEC(LZ4HC),
        ask_size Float64 CODEC(LZ4HC),
        raw_data String CODEC(LZ4HC),
        created_at DateTime64(3) DEFAULT now() CODEC(Delta, LZ4HC)
    )
    ENGINE = MergeTree()
    PARTITION BY toYYYYMM(timestamp)
    ORDER BY (exchange, symbol, data_type, timestamp)
    SETTINGS storage_policy = 'cold_storage_policy'
    """
    client.command(create_market_data_sql)
    
    # 创建元数据表
    print("📋 创建冷存储元数据表...")
    create_metadata_sql = """
    CREATE TABLE IF NOT EXISTS marketprism_cold.archive_metadata
    (
        partition_id String,
        table_name String,
        archived_at DateTime64(3) DEFAULT now(),
        start_time DateTime64(3),
        end_time DateTime64(3),
        record_count UInt64,
        compressed_size UInt64,
        original_size UInt64,
        compression_ratio Float32,
        status String DEFAULT 'active'
    )
    ENGINE = MergeTree()
    ORDER BY (table_name, start_time)
    """
    client.command(create_metadata_sql)
    
    # 创建性能优化的物化视图
    print("📈 创建冷存储优化视图...")
    create_daily_summary_sql = """
    CREATE MATERIALIZED VIEW IF NOT EXISTS marketprism_cold.daily_summary
    ENGINE = SummingMergeTree()
    PARTITION BY toYYYYMM(date)
    ORDER BY (date, exchange, symbol, data_type)
    AS SELECT
        toDate(timestamp) as date,
        exchange,
        symbol,
        data_type,
        count() as record_count,
        sum(volume) as total_volume,
        avg(price) as avg_price,
        max(price) as max_price,
        min(price) as min_price
    FROM marketprism_cold.market_data
    GROUP BY date, exchange, symbol, data_type
    """
    client.command(create_daily_summary_sql)
    
    print("✅ 冷存储数据库初始化完成!")

def create_cold_storage_users(client):
    """创建冷存储专用用户"""
    print("👤 创建冷存储用户...")
    
    # 只读用户（用于查询历史数据）
    client.command("""
        CREATE USER IF NOT EXISTS cold_reader
        IDENTIFIED WITH plaintext_password BY 'cold_read_2024'
    """)
    
    client.command("""
        GRANT SELECT ON marketprism_cold.* TO cold_reader
    """)
    
    # 归档用户（用于数据迁移）
    client.command("""
        CREATE USER IF NOT EXISTS cold_archiver
        IDENTIFIED WITH plaintext_password BY 'cold_archive_2024'
    """)
    
    client.command("""
        GRANT SELECT, INSERT, DELETE ON marketprism_cold.* TO cold_archiver
    """)
    
    print("✅ 冷存储用户创建完成!")

def verify_cold_storage(client):
    """验证冷存储设置"""
    print("🔍 验证冷存储配置...")
    
    # 检查数据库
    databases = client.query("SHOW DATABASES").result_rows
    print(f"📚 可用数据库: {[db[0] for db in databases]}")
    
    # 检查表
    tables = client.query("SHOW TABLES FROM marketprism_cold").result_rows
    print(f"📊 冷存储表: {[table[0] for table in tables]}")
    
    # 检查存储策略
    policies = client.query("SELECT policy_name, volume_name, disks FROM system.storage_policies").result_rows
    print(f"💾 存储策略: {policies}")
    
    print("✅ 冷存储验证完成!")

def main():
    """主函数"""
    print("🚀 开始初始化MarketPrism冷存储...")
    
    # 配置
    COLD_HOST = "localhost"  # 或NAS的IP地址
    COLD_PORT = 9001         # 冷存储ClickHouse端口
    
    try:
        # 连接冷存储
        client = wait_for_clickhouse(COLD_HOST, COLD_PORT)
        
        # 初始化数据库
        create_cold_storage_database(client)
        
        # 创建用户
        create_cold_storage_users(client)
        
        # 验证设置
        verify_cold_storage(client)
        
        print("🎉 冷存储初始化成功完成!")
        print(f"📍 冷存储地址: {COLD_HOST}:{COLD_PORT}")
        print(f"📚 数据库: marketprism_cold")
        print(f"👤 只读用户: cold_reader")
        print(f"🔧 归档用户: cold_archiver")
        
    except Exception as e:
        print(f"❌ 冷存储初始化失败: {e}")
        sys.exit(1)

if __name__ == "__main__":
    main() 