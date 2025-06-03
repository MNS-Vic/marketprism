#!/usr/bin/env python3
import os
import time
import clickhouse_driver

def init_clickhouse():
    print("初始化ClickHouse数据库...")
    client = clickhouse_driver.Client(host='localhost', port=9000)
    
    # 创建数据库
    client.execute('CREATE DATABASE IF NOT EXISTS marketprism')
    client.execute('CREATE DATABASE IF NOT EXISTS marketprism_test')
    client.execute('CREATE DATABASE IF NOT EXISTS marketprism_cold')
    
    # 创建trades表 - 添加分区和TTL
    client.execute('''
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
    PARTITION BY toYYYYMM(trade_time)
    ORDER BY (exchange, symbol, trade_time)
    TTL trade_time + INTERVAL 6 MONTH TO VOLUME 'marketprism_cold'
    SETTINGS index_granularity = 8192
    ''')
    
    # 为冷存储创建对应的trades表
    client.execute('''
    CREATE TABLE IF NOT EXISTS marketprism_cold.trades (
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
    PARTITION BY toYYYYMM(trade_time)
    ORDER BY (exchange, symbol, trade_time)
    TTL trade_time + INTERVAL 24 MONTH
    SETTINGS index_granularity = 8192
    ''')
    
    # 创建depth表 - 添加分区和TTL
    client.execute('''
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
    PARTITION BY toYYYYMM(time)
    ORDER BY (exchange, symbol, time)
    TTL time + INTERVAL 3 MONTH TO VOLUME 'marketprism_cold'
    SETTINGS index_granularity = 8192
    ''')
    
    # 为冷存储创建对应的depth表
    client.execute('''
    CREATE TABLE IF NOT EXISTS marketprism_cold.depth (
        id UInt64,
        exchange LowCardinality(String),
        symbol LowCardinality(String),
        update_id UInt64,
        bids String,
        asks String,
        time DateTime,
        receive_time DateTime
    ) ENGINE = MergeTree()
    PARTITION BY toYYYYMM(time)
    ORDER BY (exchange, symbol, time)
    TTL time + INTERVAL 12 MONTH
    SETTINGS index_granularity = 8192
    ''')
    
    # 创建funding_rate表 - 添加分区和TTL
    client.execute('''
    CREATE TABLE IF NOT EXISTS marketprism.funding_rate (
        id UInt64,
        exchange LowCardinality(String),
        symbol LowCardinality(String),
        rate Float64,
        time DateTime,
        receive_time DateTime
    ) ENGINE = MergeTree()
    PARTITION BY toYYYYMM(time)
    ORDER BY (exchange, symbol, time)
    TTL time + INTERVAL 12 MONTH
    SETTINGS index_granularity = 8192
    ''')
    
    # 创建open_interest表 - 添加分区和TTL
    client.execute('''
    CREATE TABLE IF NOT EXISTS marketprism.open_interest (
        id UInt64,
        exchange LowCardinality(String),
        symbol LowCardinality(String),
        open_interest Float64,
        time DateTime,
        receive_time DateTime
    ) ENGINE = MergeTree()
    PARTITION BY toYYYYMM(time)
    ORDER BY (exchange, symbol, time)
    TTL time + INTERVAL 12 MONTH
    SETTINGS index_granularity = 8192
    ''')
    
    # 创建trade_aggregations表 - 添加分区
    client.execute('''
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
    PARTITION BY toYYYYMM(interval_start)
    ORDER BY (exchange, symbol, interval_type, interval_start)
    SETTINGS index_granularity = 8192
    ''')
    
    # 创建聚合视图，自动聚合一分钟K线数据
    client.execute('''
    CREATE MATERIALIZED VIEW IF NOT EXISTS marketprism.trades_to_1m
    TO marketprism.trade_aggregations
    AS
    SELECT
        exchange,
        symbol,
        '1m' as interval_type,
        toStartOfMinute(trade_time) as interval_start,
        argMin(price, trade_time) as open_price,
        max(price) as high_price,
        min(price) as low_price,
        argMax(price, trade_time) as close_price,
        sum(quantity) as volume,
        sum(price * quantity) / sum(quantity) as vwap,
        count() as trade_count,
        now() as created_at
    FROM marketprism.trades
    GROUP BY exchange, symbol, interval_start
    ''')
    
    # 创建系统状态表，记录服务器状态
    client.execute('''
    CREATE TABLE IF NOT EXISTS marketprism.system_status (
        timestamp DateTime,
        service LowCardinality(String),
        status Enum8('ok' = 1, 'warning' = 2, 'error' = 3, 'offline' = 4),
        message String,
        details String DEFAULT ''
    ) ENGINE = MergeTree()
    PARTITION BY toYYYYMM(timestamp)
    ORDER BY (service, timestamp)
    TTL timestamp + INTERVAL 3 MONTH
    SETTINGS index_granularity = 8192
    ''')
    
    # 创建监控指标表
    client.execute('''
    CREATE TABLE IF NOT EXISTS marketprism.metrics (
        timestamp DateTime,
        metric_name LowCardinality(String),
        metric_value Float64,
        service LowCardinality(String),
        tags String DEFAULT '{}'
    ) ENGINE = MergeTree()
    PARTITION BY toYYYYMM(timestamp)
    ORDER BY (metric_name, service, timestamp)
    TTL timestamp + INTERVAL 1 MONTH
    SETTINGS index_granularity = 8192
    ''')
    
    print("ClickHouse数据库初始化完成!")

if __name__ == "__main__":
    max_attempts = 5
    attempt = 0
    
    while attempt < max_attempts:
        try:
            init_clickhouse()
            break
        except Exception as e:
            attempt += 1
            print(f"初始化失败（尝试 {attempt}/{max_attempts}）: {e}")
            if attempt < max_attempts:
                print(f"等待5秒后重试...")
                time.sleep(5)
            else:
                print("达到最大尝试次数，初始化失败。")
                raise 