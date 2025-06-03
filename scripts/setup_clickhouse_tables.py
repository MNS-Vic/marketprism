#!/usr/bin/env python3
"""
ClickHouse数据库表结构初始化脚本
创建MarketPrism所需的所有数据库表

使用方法:
    python scripts/setup_clickhouse_tables.py
"""

import sys
import os
import logging
from datetime import datetime
import clickhouse_connect

# 添加项目根目录到路径
project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
sys.path.insert(0, project_root)

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

class ClickHouseTableSetup:
    """ClickHouse表结构设置管理器"""
    
    def __init__(self, host='localhost', port=8123, username='default', password=''):
        self.host = host
        self.port = port
        self.username = username
        self.password = password
        self.client = None
        
    def connect(self):
        """连接到ClickHouse"""
        try:
            self.client = clickhouse_connect.get_client(
                host=self.host,
                port=self.port,
                username=self.username,
                password=self.password
            )
            logger.info(f"✅ ClickHouse连接成功: {self.host}:{self.port}")
            return True
        except Exception as e:
            logger.error(f"❌ ClickHouse连接失败: {e}")
            return False
    
    def create_database(self, database_name='marketprism'):
        """创建数据库"""
        try:
            create_db_sql = f"CREATE DATABASE IF NOT EXISTS {database_name}"
            self.client.command(create_db_sql)
            logger.info(f"✅ 数据库 '{database_name}' 创建成功")
            return True
        except Exception as e:
            logger.error(f"❌ 创建数据库失败: {e}")
            return False
    
    def create_trades_table(self, database='marketprism'):
        """创建交易数据表"""
        table_sql = f"""
        CREATE TABLE IF NOT EXISTS {database}.trades (
            id UInt64,
            exchange String,
            symbol String,
            trade_id String,
            price Float64,
            quantity Float64,
            side Enum('buy' = 1, 'sell' = 2),
            trade_time DateTime64(3),
            receive_time DateTime64(3) DEFAULT now(),
            normalized_symbol String DEFAULT '',
            market_type Enum('spot' = 1, 'futures' = 2, 'options' = 3) DEFAULT 'spot',
            fee Float64 DEFAULT 0,
            fee_currency String DEFAULT '',
            INDEX idx_exchange exchange TYPE set(0) GRANULARITY 1,
            INDEX idx_symbol symbol TYPE set(0) GRANULARITY 1,
            INDEX idx_trade_time trade_time TYPE minmax GRANULARITY 1
        ) ENGINE = MergeTree()
        PARTITION BY toYYYYMM(trade_time)
        ORDER BY (exchange, symbol, trade_time)
        TTL trade_time + INTERVAL 90 DAY
        SETTINGS index_granularity = 8192
        """
        
        try:
            self.client.command(table_sql)
            logger.info(f"✅ 交易数据表 '{database}.trades' 创建成功")
            return True
        except Exception as e:
            logger.error(f"❌ 创建交易数据表失败: {e}")
            return False
    
    def create_orderbook_table(self, database='marketprism'):
        """创建订单簿数据表"""
        table_sql = f"""
        CREATE TABLE IF NOT EXISTS {database}.orderbook (
            id UInt64,
            exchange String,
            symbol String,
            timestamp DateTime64(3),
            receive_time DateTime64(3) DEFAULT now(),
            last_update_id UInt64,
            bids Array(Array(Float64)),
            asks Array(Array(Float64)),
            depth_levels UInt16 DEFAULT 20,
            normalized_symbol String DEFAULT '',
            INDEX idx_exchange exchange TYPE set(0) GRANULARITY 1,
            INDEX idx_symbol symbol TYPE set(0) GRANULARITY 1,
            INDEX idx_timestamp timestamp TYPE minmax GRANULARITY 1
        ) ENGINE = MergeTree()
        PARTITION BY toYYYYMM(timestamp)
        ORDER BY (exchange, symbol, timestamp)
        TTL timestamp + INTERVAL 30 DAY
        SETTINGS index_granularity = 8192
        """
        
        try:
            self.client.command(table_sql)
            logger.info(f"✅ 订单簿数据表 '{database}.orderbook' 创建成功")
            return True
        except Exception as e:
            logger.error(f"❌ 创建订单簿数据表失败: {e}")
            return False
    
    def create_klines_table(self, database='marketprism'):
        """创建K线数据表"""
        table_sql = f"""
        CREATE TABLE IF NOT EXISTS {database}.klines (
            id UInt64,
            exchange String,
            symbol String,
            interval String,
            open_time DateTime64(3),
            close_time DateTime64(3),
            open_price Float64,
            high_price Float64,
            low_price Float64,
            close_price Float64,
            volume Float64,
            quote_volume Float64,
            trade_count UInt32,
            taker_buy_volume Float64,
            taker_buy_quote_volume Float64,
            receive_time DateTime64(3) DEFAULT now(),
            INDEX idx_exchange exchange TYPE set(0) GRANULARITY 1,
            INDEX idx_symbol symbol TYPE set(0) GRANULARITY 1,
            INDEX idx_interval interval TYPE set(0) GRANULARITY 1,
            INDEX idx_open_time open_time TYPE minmax GRANULARITY 1
        ) ENGINE = MergeTree()
        PARTITION BY (toYYYYMM(open_time), interval)
        ORDER BY (exchange, symbol, interval, open_time)
        TTL open_time + INTERVAL 180 DAY
        SETTINGS index_granularity = 8192
        """
        
        try:
            self.client.command(table_sql)
            logger.info(f"✅ K线数据表 '{database}.klines' 创建成功")
            return True
        except Exception as e:
            logger.error(f"❌ 创建K线数据表失败: {e}")
            return False
    
    def create_funding_rates_table(self, database='marketprism'):
        """创建资金费率表"""
        table_sql = f"""
        CREATE TABLE IF NOT EXISTS {database}.funding_rates (
            id UInt64,
            exchange String,
            symbol String,
            funding_rate Float64,
            funding_time DateTime64(3),
            next_funding_time DateTime64(3),
            predicted_rate Float64 DEFAULT 0,
            receive_time DateTime64(3) DEFAULT now(),
            INDEX idx_exchange exchange TYPE set(0) GRANULARITY 1,
            INDEX idx_symbol symbol TYPE set(0) GRANULARITY 1,
            INDEX idx_funding_time funding_time TYPE minmax GRANULARITY 1
        ) ENGINE = MergeTree()
        PARTITION BY toYYYYMM(funding_time)
        ORDER BY (exchange, symbol, funding_time)
        TTL funding_time + INTERVAL 365 DAY
        SETTINGS index_granularity = 8192
        """
        
        try:
            self.client.command(table_sql)
            logger.info(f"✅ 资金费率表 '{database}.funding_rates' 创建成功")
            return True
        except Exception as e:
            logger.error(f"❌ 创建资金费率表失败: {e}")
            return False
    
    def create_liquidations_table(self, database='marketprism'):
        """创建清算数据表"""
        table_sql = f"""
        CREATE TABLE IF NOT EXISTS {database}.liquidations (
            id UInt64,
            exchange String,
            symbol String,
            side Enum('long' = 1, 'short' = 2),
            quantity Float64,
            price Float64,
            value Float64,
            liquidation_time DateTime64(3),
            receive_time DateTime64(3) DEFAULT now(),
            INDEX idx_exchange exchange TYPE set(0) GRANULARITY 1,
            INDEX idx_symbol symbol TYPE set(0) GRANULARITY 1,
            INDEX idx_liquidation_time liquidation_time TYPE minmax GRANULARITY 1
        ) ENGINE = MergeTree()
        PARTITION BY toYYYYMM(liquidation_time)
        ORDER BY (exchange, symbol, liquidation_time)
        TTL liquidation_time + INTERVAL 180 DAY
        SETTINGS index_granularity = 8192
        """
        
        try:
            self.client.command(table_sql)
            logger.info(f"✅ 清算数据表 '{database}.liquidations' 创建成功")
            return True
        except Exception as e:
            logger.error(f"❌ 创建清算数据表失败: {e}")
            return False
    
    def create_market_stats_table(self, database='marketprism'):
        """创建市场统计表"""
        table_sql = f"""
        CREATE TABLE IF NOT EXISTS {database}.market_stats (
            id UInt64,
            exchange String,
            symbol String,
            open_interest Float64,
            volume_24h Float64,
            price_change_24h Float64,
            price_change_percent_24h Float64,
            high_24h Float64,
            low_24h Float64,
            last_price Float64,
            timestamp DateTime64(3),
            receive_time DateTime64(3) DEFAULT now(),
            INDEX idx_exchange exchange TYPE set(0) GRANULARITY 1,
            INDEX idx_symbol symbol TYPE set(0) GRANULARITY 1,
            INDEX idx_timestamp timestamp TYPE minmax GRANULARITY 1
        ) ENGINE = MergeTree()
        PARTITION BY toYYYYMM(timestamp)
        ORDER BY (exchange, symbol, timestamp)
        TTL timestamp + INTERVAL 90 DAY
        SETTINGS index_granularity = 8192
        """
        
        try:
            self.client.command(table_sql)
            logger.info(f"✅ 市场统计表 '{database}.market_stats' 创建成功")
            return True
        except Exception as e:
            logger.error(f"❌ 创建市场统计表失败: {e}")
            return False
    
    def create_all_tables(self, database='marketprism'):
        """创建所有必需的表"""
        logger.info("🚀 开始创建ClickHouse表结构...")
        
        success_count = 0
        total_tables = 6
        
        # 创建数据库
        if self.create_database(database):
            success_count += 1
        
        # 创建所有表
        table_creators = [
            self.create_trades_table,
            self.create_orderbook_table,
            self.create_klines_table,
            self.create_funding_rates_table,
            self.create_liquidations_table,
            self.create_market_stats_table
        ]
        
        for creator in table_creators:
            if creator(database):
                success_count += 1
        
        logger.info(f"📊 表创建完成: {success_count}/{total_tables + 1} 成功")
        
        if success_count == total_tables + 1:
            logger.info("🎉 所有ClickHouse表结构创建成功！")
            return True
        else:
            logger.warning(f"⚠️ 部分表创建失败: {total_tables + 1 - success_count} 个失败")
            return False
    
    def verify_tables(self, database='marketprism'):
        """验证表是否正确创建"""
        logger.info("🔍 验证表结构...")
        
        try:
            # 查询所有表
            tables_query = f"SHOW TABLES FROM {database}"
            result = self.client.query(tables_query)
            tables = [row[0] for row in result.result_rows]
            
            expected_tables = [
                'trades', 'orderbook', 'klines', 
                'funding_rates', 'liquidations', 'market_stats'
            ]
            
            logger.info(f"发现表: {tables}")
            
            missing_tables = [table for table in expected_tables if table not in tables]
            if missing_tables:
                logger.warning(f"⚠️ 缺少表: {missing_tables}")
                return False
            
            # 验证表结构
            for table in expected_tables:
                describe_query = f"DESCRIBE {database}.{table}"
                result = self.client.query(describe_query)
                columns = len(result.result_rows)
                logger.info(f"✅ 表 '{table}' 验证通过 ({columns}列)")
            
            logger.info("🎉 所有表验证成功！")
            return True
            
        except Exception as e:
            logger.error(f"❌ 表验证失败: {e}")
            return False
    
    def insert_test_data(self, database='marketprism'):
        """插入测试数据"""
        logger.info("🧪 插入测试数据...")
        
        try:
            # 插入测试交易数据
            test_trades = [
                {
                    'id': int(datetime.now().timestamp()),
                    'exchange': 'test_exchange',
                    'symbol': 'BTC/USDT',
                    'trade_id': f'test_{int(datetime.now().timestamp())}',
                    'price': 50000.0,
                    'quantity': 0.001,
                    'side': 'buy',
                    'trade_time': datetime.now(),
                    'receive_time': datetime.now()
                }
            ]
            
            insert_count = self.client.insert(f'{database}.trades', test_trades)
            logger.info(f"✅ 测试数据插入成功: {len(test_trades)} 条记录")
            
            # 验证插入
            count_query = f"SELECT COUNT(*) FROM {database}.trades WHERE exchange = 'test_exchange'"
            result = self.client.query(count_query)
            count = result.result_rows[0][0]
            logger.info(f"✅ 数据验证成功: 表中有 {count} 条测试记录")
            
            return True
            
        except Exception as e:
            logger.error(f"❌ 测试数据插入失败: {e}")
            return False
    
    def cleanup_test_data(self, database='marketprism'):
        """清理测试数据"""
        try:
            cleanup_query = f"ALTER TABLE {database}.trades DELETE WHERE exchange = 'test_exchange'"
            self.client.command(cleanup_query)
            logger.info("✅ 测试数据清理成功")
            return True
        except Exception as e:
            logger.error(f"❌ 测试数据清理失败: {e}")
            return False

def main():
    """主函数"""
    import argparse
    
    parser = argparse.ArgumentParser(description='ClickHouse表结构初始化工具')
    parser.add_argument('--host', default='localhost', help='ClickHouse主机地址')
    parser.add_argument('--port', type=int, default=8123, help='ClickHouse端口')
    parser.add_argument('--username', default='default', help='用户名')
    parser.add_argument('--password', default='', help='密码')
    parser.add_argument('--database', default='marketprism', help='数据库名称')
    parser.add_argument('--verify-only', action='store_true', help='仅验证表结构')
    parser.add_argument('--test-data', action='store_true', help='插入测试数据')
    
    args = parser.parse_args()
    
    setup = ClickHouseTableSetup(
        host=args.host,
        port=args.port,
        username=args.username,
        password=args.password
    )
    
    if not setup.connect():
        logger.error("连接失败，退出")
        return 1
    
    try:
        if args.verify_only:
            # 仅验证表结构
            if setup.verify_tables(args.database):
                logger.info("🎉 表结构验证成功！")
                return 0
            else:
                logger.error("❌ 表结构验证失败")
                return 1
        else:
            # 创建表结构
            if setup.create_all_tables(args.database):
                # 验证创建结果
                if setup.verify_tables(args.database):
                    logger.info("🎉 ClickHouse表结构初始化完成！")
                    
                    if args.test_data:
                        setup.insert_test_data(args.database)
                    
                    return 0
                else:
                    logger.error("❌ 表结构验证失败")
                    return 1
            else:
                logger.error("❌ 表结构创建失败")
                return 1
                
    except Exception as e:
        logger.error(f"执行过程中发生异常: {e}")
        return 1

if __name__ == "__main__":
    exit_code = main()
    sys.exit(exit_code)