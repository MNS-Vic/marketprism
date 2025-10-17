#!/usr/bin/env python3
"""
ClickHouse表结构初始化脚本
用于Docker容器启动时创建所有必要的表
"""

import requests
import sys
from typing import Dict, List


def create_table(host: str, port: int, database: str, table_name: str, table_sql: str) -> bool:
    """创建单个表"""
    try:
        url = f"http://{host}:{port}/?database={database}"
        response = requests.post(url, data=table_sql, timeout=30)
        
        if response.status_code == 200:
            print(f"✅ 表创建成功: {table_name}")
            return True
        else:
            print(f"❌ 表创建失败: {table_name} - {response.text}")
            return False
            
    except Exception as e:
        print(f"❌ 表创建异常: {table_name} - {e}")
        return False


def get_table_definitions() -> Dict[str, str]:
    """获取所有表的定义"""
    return {
        "orderbooks": """
        CREATE TABLE IF NOT EXISTS orderbooks (
            timestamp DateTime64(3),
            exchange String,
            market_type String,
            symbol String,
            data_source String,
            last_update_id UInt64,
            best_bid_price Float64,
            best_ask_price Float64,
            bids String,
            asks String
        ) ENGINE = MergeTree()
        PARTITION BY toYYYYMM(timestamp)
        ORDER BY (exchange, symbol, timestamp)
        TTL toDateTime(timestamp) + INTERVAL 3 DAY
        """,
        
        "trades": """
        CREATE TABLE IF NOT EXISTS trades (
            timestamp DateTime64(3),
            exchange String,
            market_type String,
            symbol String,
            data_source String,
            trade_id String,
            price Float64,
            quantity Float64,
            side String,
            is_maker Bool
        ) ENGINE = MergeTree()
        PARTITION BY toYYYYMM(timestamp)
        ORDER BY (exchange, symbol, timestamp)
        TTL toDateTime(timestamp) + INTERVAL 3 DAY
        """,
        
        "funding_rates": """
        CREATE TABLE IF NOT EXISTS funding_rates (
            timestamp DateTime64(3),
            exchange String,
            market_type String,
            symbol String,
            data_source String,
            funding_rate Float64,
            funding_time DateTime64(3),
            next_funding_time DateTime64(3)
        ) ENGINE = MergeTree()
        PARTITION BY toYYYYMM(timestamp)
        ORDER BY (exchange, symbol, timestamp)
        TTL toDateTime(timestamp) + INTERVAL 7 DAY
        """,
        
        "open_interests": """
        CREATE TABLE IF NOT EXISTS open_interests (
            timestamp DateTime64(3),
            exchange String,
            market_type String,
            symbol String,
            data_source String,
            open_interest Float64,
            open_interest_value Float64
        ) ENGINE = MergeTree()
        PARTITION BY toYYYYMM(timestamp)
        ORDER BY (exchange, symbol, timestamp)
        TTL toDateTime(timestamp) + INTERVAL 7 DAY
        """,
        
        "liquidations": """
        CREATE TABLE IF NOT EXISTS liquidations (
            timestamp DateTime64(3),
            exchange String,
            market_type String,
            symbol String,
            data_source String,
            liquidation_id String,
            side String,
            price Float64,
            quantity Float64,
            liquidation_time DateTime64(3)
        ) ENGINE = MergeTree()
        PARTITION BY toYYYYMM(timestamp)
        ORDER BY (exchange, symbol, timestamp)
        TTL toDateTime(timestamp) + INTERVAL 30 DAY
        """,
        
        "lsr_data": """
        CREATE TABLE IF NOT EXISTS lsr_data (
            timestamp DateTime64(3),
            exchange String,
            market_type String,
            symbol String,
            data_source String,
            long_short_ratio Float64,
            long_account Float64,
            short_account Float64,
            period String
        ) ENGINE = MergeTree()
        PARTITION BY toYYYYMM(timestamp)
        ORDER BY (exchange, symbol, timestamp)
        TTL toDateTime(timestamp) + INTERVAL 30 DAY
        """,
        
        "lsr_top_positions": """
        CREATE TABLE IF NOT EXISTS lsr_top_positions (
            timestamp DateTime64(3),
            exchange String,
            market_type String,
            symbol String,
            data_source String,
            long_short_ratio Float64,
            long_account Float64,
            short_account Float64,
            period String
        ) ENGINE = MergeTree()
        PARTITION BY toYYYYMM(timestamp)
        ORDER BY (exchange, symbol, timestamp)
        TTL toDateTime(timestamp) + INTERVAL 30 DAY
        """,
        
        "lsr_all_accounts": """
        CREATE TABLE IF NOT EXISTS lsr_all_accounts (
            timestamp DateTime64(3),
            exchange String,
            market_type String,
            symbol String,
            data_source String,
            long_short_ratio Float64,
            long_account Float64,
            short_account Float64,
            period String
        ) ENGINE = MergeTree()
        PARTITION BY toYYYYMM(timestamp)
        ORDER BY (exchange, symbol, timestamp)
        TTL toDateTime(timestamp) + INTERVAL 30 DAY
        """,

        "volatility_indices": """
        CREATE TABLE IF NOT EXISTS volatility_indices (
            timestamp DateTime64(3),
            exchange String,
            market_type String,
            symbol String,
            data_source String,
            volatility_index Float64,
            period String
        ) ENGINE = MergeTree()
        PARTITION BY toYYYYMM(timestamp)
        ORDER BY (exchange, symbol, timestamp)
        TTL toDateTime(timestamp) + INTERVAL 30 DAY
        """
    }


def init_all_tables(host: str = "localhost", port: int = 8123, database: str = "marketprism_hot") -> bool:
    """初始化所有表"""
    print(f"🔧 开始初始化ClickHouse表结构")
    print(f"   主机: {host}:{port}")
    print(f"   数据库: {database}")
    
    table_definitions = get_table_definitions()
    success_count = 0
    total_count = len(table_definitions)
    
    for table_name, table_sql in table_definitions.items():
        if create_table(host, port, database, table_name, table_sql):
            success_count += 1
        else:
            print(f"❌ 表创建失败，继续处理其他表...")
    
    print(f"\n📊 表创建结果: {success_count}/{total_count} 成功")
    
    if success_count == total_count:
        print("✅ 所有表创建成功")
        return True
    else:
        print(f"⚠️ 有 {total_count - success_count} 个表创建失败")
        return False


def main():
    """主函数"""
    import argparse
    
    parser = argparse.ArgumentParser(description='ClickHouse表结构初始化工具')
    parser.add_argument('--host', default='localhost', help='ClickHouse主机地址')
    parser.add_argument('--port', type=int, default=8123, help='ClickHouse HTTP端口')
    parser.add_argument('--database', default='marketprism_hot', help='数据库名称')
    
    args = parser.parse_args()
    
    success = init_all_tables(args.host, args.port, args.database)
    
    if not success:
        sys.exit(1)


if __name__ == "__main__":
    main()
