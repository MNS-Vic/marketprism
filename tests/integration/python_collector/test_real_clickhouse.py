"""
Python Collector ClickHouse真实集成测试

连接真实的ClickHouse数据库进行数据存储和查询测试
不使用Mock，使用真实的数据库连接和操作
需要先启动ClickHouse服务：docker-compose up clickhouse
"""

from datetime import datetime, timezone
import pytest
import asyncio
import time
from decimal import Decimal
import aiochclient
from aiochclient import ChClient

# 导入被测试的模块
import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '../../../services/python-collector/src'))

from marketprism_collector.data_types import (
    NormalizedTrade, NormalizedOrderBook, NormalizedTicker,
    PriceLevel
)


@pytest.fixture(scope="session")
def event_loop():
    """创建事件循环"""
    loop = asyncio.new_event_loop()
    yield loop
    loop.close()


@pytest.fixture(scope="session")
async def clickhouse_client():
    """创建真实的ClickHouse客户端"""
    try:
        client = ChClient(
            url="http://localhost:8123",
            user="default",
            password="",
            database="marketprism"
        )
        
        # 测试连接
        await client.execute("SELECT 1")
        yield client
        await client.close()
        
    except Exception as e:
        pytest.skip(f"无法连接到ClickHouse数据库: {e}")


class TestRealClickHouseConnection:
    """测试真实ClickHouse连接"""
    
    @pytest.mark.asyncio
    async def test_clickhouse_server_available(self):
        """测试ClickHouse服务器是否可用"""
        try:
            client = ChClient(
                url="http://localhost:8123",
                user="default",
                password="",
                database="default"
            )
            
            # 执行简单查询
            result = await client.execute("SELECT version()")
            assert result is not None
            print(f"ClickHouse版本: {result}")
            
            await client.close()
            
        except Exception as e:
            pytest.fail(f"ClickHouse服务器不可用: {e}")
    
    @pytest.mark.asyncio
    async def test_database_exists(self, clickhouse_client):
        """测试数据库是否存在"""
        try:
            # 检查数据库是否存在
            result = await clickhouse_client.execute(
                "SELECT name FROM system.databases WHERE name = 'marketprism'"
            )
            
            if not result:
                # 创建数据库
                await clickhouse_client.execute("CREATE DATABASE IF NOT EXISTS marketprism")
                print("创建了marketprism数据库")
            else:
                print("marketprism数据库已存在")
                
        except Exception as e:
            pytest.fail(f"数据库检查失败: {e}")


class TestRealTableOperations:
    """测试真实表操作"""
    
    @pytest.mark.asyncio
    async def test_create_trades_table(self, clickhouse_client):
        """测试创建交易数据表"""
        try:
            # 创建交易数据表
            create_table_sql = """
            CREATE TABLE IF NOT EXISTS trades (
                exchange_name String,
                symbol_name String,
                trade_id String,
                price Decimal64(8),
                quantity Decimal64(8),
                quote_quantity Decimal64(8),
                timestamp DateTime64(3),
                is_buyer_maker UInt8,
                is_best_match Nullable(UInt8),
                collected_at DateTime64(3) DEFAULT now64(),
                raw_data Nullable(String)
            ) ENGINE = MergeTree()
            ORDER BY (exchange_name, symbol_name, timestamp)
            PARTITION BY toYYYYMM(timestamp)
            """
            
            await clickhouse_client.execute(create_table_sql)
            
            # 验证表是否创建成功
            result = await clickhouse_client.execute(
                "SELECT name FROM system.tables WHERE database = 'marketprism' AND name = 'trades'"
            )
            
            assert result, "交易数据表创建失败"
            print("交易数据表创建成功")
            
        except Exception as e:
            pytest.fail(f"创建交易数据表失败: {e}")
    
    @pytest.mark.asyncio
    async def test_create_orderbooks_table(self, clickhouse_client):
        """测试创建订单簿数据表"""
        try:
            # 创建订单簿数据表
            create_table_sql = """
            CREATE TABLE IF NOT EXISTS orderbooks (
                exchange_name String,
                symbol_name String,
                last_update_id Nullable(UInt64),
                bids Array(Tuple(Decimal64(8), Decimal64(8))),
                asks Array(Tuple(Decimal64(8), Decimal64(8))),
                timestamp DateTime64(3),
                collected_at DateTime64(3) DEFAULT now64(),
                raw_data Nullable(String)
            ) ENGINE = MergeTree()
            ORDER BY (exchange_name, symbol_name, timestamp)
            PARTITION BY toYYYYMM(timestamp)
            """
            
            await clickhouse_client.execute(create_table_sql)
            
            # 验证表是否创建成功
            result = await clickhouse_client.execute(
                "SELECT name FROM system.tables WHERE database = 'marketprism' AND name = 'orderbooks'"
            )
            
            assert result, "订单簿数据表创建失败"
            print("订单簿数据表创建成功")
            
        except Exception as e:
            pytest.fail(f"创建订单簿数据表失败: {e}")
    
    @pytest.mark.asyncio
    async def test_create_tickers_table(self, clickhouse_client):
        """测试创建行情数据表"""
        try:
            # 创建行情数据表
            create_table_sql = """
            CREATE TABLE IF NOT EXISTS tickers (
                exchange_name String,
                symbol_name String,
                last_price Decimal64(8),
                open_price Nullable(Decimal64(8)),
                high_price Nullable(Decimal64(8)),
                low_price Nullable(Decimal64(8)),
                volume Nullable(Decimal64(8)),
                quote_volume Nullable(Decimal64(8)),
                price_change Nullable(Decimal64(8)),
                price_change_percent Nullable(Decimal64(4)),
                weighted_avg_price Nullable(Decimal64(8)),
                last_quantity Nullable(Decimal64(8)),
                best_bid_price Nullable(Decimal64(8)),
                best_bid_quantity Nullable(Decimal64(8)),
                best_ask_price Nullable(Decimal64(8)),
                best_ask_quantity Nullable(Decimal64(8)),
                open_time Nullable(DateTime64(3)),
                close_time Nullable(DateTime64(3)),
                trade_count Nullable(UInt64),
                timestamp DateTime64(3),
                collected_at DateTime64(3) DEFAULT now64(),
                raw_data Nullable(String)
            ) ENGINE = MergeTree()
            ORDER BY (exchange_name, symbol_name, timestamp)
            PARTITION BY toYYYYMM(timestamp)
            """
            
            await clickhouse_client.execute(create_table_sql)
            
            # 验证表是否创建成功
            result = await clickhouse_client.execute(
                "SELECT name FROM system.tables WHERE database = 'marketprism' AND name = 'tickers'"
            )
            
            assert result, "行情数据表创建失败"
            print("行情数据表创建成功")
            
        except Exception as e:
            pytest.fail(f"创建行情数据表失败: {e}")


class TestRealDataInsertion:
    """测试真实数据插入"""
    
    @pytest.mark.asyncio
    async def test_insert_real_trade_data(self, clickhouse_client):
        """测试插入真实交易数据"""
        try:
            # 创建测试交易数据
            timestamp = datetime.now(timezone.utc)
            trade = NormalizedTrade(
                exchange_name="binance",
                symbol_name="BTCUSDT",
                trade_id=f"test_trade_{int(time.time())}",
                price=Decimal("50000.00"),
                quantity=Decimal("0.1"),
                quote_quantity=Decimal("5000.00"),
                timestamp=timestamp,
                is_buyer_maker=True
            )
            
            # 插入数据
            insert_sql = """
            INSERT INTO trades (
                exchange_name, symbol_name, trade_id, price, quantity, 
                quote_quantity, timestamp, is_buyer_maker
            ) VALUES
            """
            
            await clickhouse_client.execute(
                insert_sql,
                [
                    trade.exchange_name,
                    trade.symbol_name,
                    trade.trade_id,
                    float(trade.price),
                    float(trade.quantity),
                    float(trade.quote_quantity),
                    trade.timestamp,
                    1 if trade.is_buyer_maker else 0
                ]
            )
            
            # 验证数据是否插入成功
            result = await clickhouse_client.execute(
                "SELECT COUNT(*) FROM trades WHERE trade_id = %s",
                [trade.trade_id]
            )
            
            assert result[0] == 1, "交易数据插入失败"
            print(f"成功插入交易数据: {trade.trade_id}")
            
        except Exception as e:
            pytest.fail(f"插入交易数据失败: {e}")
    
    @pytest.mark.asyncio
    async def test_insert_real_orderbook_data(self, clickhouse_client):
        """测试插入真实订单簿数据"""
        try:
            # 创建测试订单簿数据
            timestamp = datetime.now(timezone.utc)
            orderbook = NormalizedOrderBook(
                exchange_name="binance",
                symbol_name="BTCUSDT",
                bids=[
                    PriceLevel(price=Decimal("49999.00"), quantity=Decimal("0.5")),
                    PriceLevel(price=Decimal("49998.00"), quantity=Decimal("1.0"))
                ],
                asks=[
                    PriceLevel(price=Decimal("50001.00"), quantity=Decimal("0.3")),
                    PriceLevel(price=Decimal("50002.00"), quantity=Decimal("0.8"))
                ],
                timestamp=timestamp,
                last_update_id=int(time.time())
            )
            
            # 转换价格档位为元组数组
            bids_tuples = [(float(bid.price), float(bid.quantity)) for bid in orderbook.bids]
            asks_tuples = [(float(ask.price), float(ask.quantity)) for ask in orderbook.asks]
            
            # 插入数据
            insert_sql = """
            INSERT INTO orderbooks (
                exchange_name, symbol_name, last_update_id, bids, asks, timestamp
            ) VALUES
            """
            
            await clickhouse_client.execute(
                insert_sql,
                [
                    orderbook.exchange_name,
                    orderbook.symbol_name,
                    orderbook.last_update_id,
                    bids_tuples,
                    asks_tuples,
                    orderbook.timestamp
                ]
            )
            
            # 验证数据是否插入成功
            result = await clickhouse_client.execute(
                "SELECT COUNT(*) FROM orderbooks WHERE last_update_id = %s",
                [orderbook.last_update_id]
            )
            
            assert result[0] == 1, "订单簿数据插入失败"
            print(f"成功插入订单簿数据: {orderbook.last_update_id}")
            
        except Exception as e:
            pytest.fail(f"插入订单簿数据失败: {e}")
    
    @pytest.mark.asyncio
    async def test_batch_insert_trades(self, clickhouse_client):
        """测试批量插入交易数据"""
        try:
            # 创建多个测试交易数据
            timestamp = datetime.now(timezone.utc)
            batch_size = 100
            trades_data = []
            
            for i in range(batch_size):
                trades_data.append([
                    "binance",
                    "BTCUSDT",
                    f"batch_trade_{int(time.time())}_{i}",
                    50000.00 + i,
                    0.1,
                    5000.00 + i * 0.1,
                    timestamp,
                    1 if i % 2 == 0 else 0
                ])
            
            # 批量插入
            insert_sql = """
            INSERT INTO trades (
                exchange_name, symbol_name, trade_id, price, quantity, 
                quote_quantity, timestamp, is_buyer_maker
            ) VALUES
            """
            
            await clickhouse_client.execute(insert_sql, *trades_data)
            
            # 验证批量插入结果
            result = await clickhouse_client.execute(
                "SELECT COUNT(*) FROM trades WHERE trade_id LIKE 'batch_trade_%'"
            )
            
            assert result[0] >= batch_size, f"批量插入失败，期望{batch_size}条，实际{result[0]}条"
            print(f"成功批量插入{result[0]}条交易数据")
            
        except Exception as e:
            pytest.fail(f"批量插入交易数据失败: {e}")


class TestRealDataQuery:
    """测试真实数据查询"""
    
    @pytest.mark.asyncio
    async def test_query_recent_trades(self, clickhouse_client):
        """测试查询最近交易数据"""
        try:
            # 查询最近的交易数据
            query_sql = """
            SELECT 
                exchange_name, symbol_name, trade_id, price, quantity, timestamp
            FROM trades 
            WHERE timestamp >= now() - INTERVAL 1 HOUR
            ORDER BY timestamp DESC 
            LIMIT 10
            """
            
            result = await clickhouse_client.execute(query_sql)
            
            # 验证查询结果
            assert isinstance(result, list), "查询结果应该是列表"
            
            if result:
                print(f"查询到{len(result)}条最近交易数据")
                for trade in result[:3]:
                    print(f"交易: {trade[1]} @ ${trade[3]} x {trade[4]}")
            else:
                print("没有查询到最近的交易数据")
                
        except Exception as e:
            pytest.fail(f"查询最近交易数据失败: {e}")
    
    @pytest.mark.asyncio
    async def test_query_price_statistics(self, clickhouse_client):
        """测试查询价格统计"""
        try:
            # 查询价格统计数据
            query_sql = """
            SELECT 
                symbol_name,
                COUNT(*) as trade_count,
                AVG(price) as avg_price,
                MIN(price) as min_price,
                MAX(price) as max_price,
                SUM(quantity) as total_volume
            FROM trades 
            WHERE timestamp >= now() - INTERVAL 1 DAY
            GROUP BY symbol_name
            ORDER BY trade_count DESC
            """
            
            result = await clickhouse_client.execute(query_sql)
            
            # 验证查询结果
            assert isinstance(result, list), "查询结果应该是列表"
            
            if result:
                print(f"查询到{len(result)}个交易对的统计数据")
                for stat in result:
                    symbol, count, avg_price, min_price, max_price, volume = stat
                    print(f"{symbol}: {count}笔交易, 均价${avg_price:.2f}, 成交量{volume}")
            else:
                print("没有查询到统计数据")
                
        except Exception as e:
            pytest.fail(f"查询价格统计失败: {e}")
    
    @pytest.mark.asyncio
    async def test_query_orderbook_spread(self, clickhouse_client):
        """测试查询订单簿价差"""
        try:
            # 查询订单簿价差数据
            query_sql = """
            SELECT 
                symbol_name,
                timestamp,
                bids[1].1 as best_bid,
                asks[1].1 as best_ask,
                asks[1].1 - bids[1].1 as spread
            FROM orderbooks 
            WHERE timestamp >= now() - INTERVAL 1 HOUR
            AND length(bids) > 0 AND length(asks) > 0
            ORDER BY timestamp DESC 
            LIMIT 10
            """
            
            result = await clickhouse_client.execute(query_sql)
            
            # 验证查询结果
            assert isinstance(result, list), "查询结果应该是列表"
            
            if result:
                print(f"查询到{len(result)}条订单簿价差数据")
                for spread_data in result[:3]:
                    symbol, timestamp, bid, ask, spread = spread_data
                    spread_percent = (spread / bid) * 100 if bid > 0 else 0
                    print(f"{symbol}: 买价${bid}, 卖价${ask}, 价差${spread} ({spread_percent:.4f}%)")
            else:
                print("没有查询到订单簿价差数据")
                
        except Exception as e:
            pytest.fail(f"查询订单簿价差失败: {e}")


class TestRealDataPerformance:
    """测试真实数据性能"""
    
    @pytest.mark.asyncio
    async def test_insert_performance(self, clickhouse_client):
        """测试插入性能"""
        try:
            # 准备大量测试数据
            batch_size = 1000
            timestamp = datetime.now(timezone.utc)
            trades_data = []
            
            for i in range(batch_size):
                trades_data.append([
                    "binance",
                    "BTCUSDT",
                    f"perf_test_{int(time.time())}_{i}",
                    50000.00 + (i % 1000),
                    0.1,
                    5000.00,
                    timestamp,
                    1 if i % 2 == 0 else 0
                ])
            
            # 测试插入性能
            start_time = time.time()
            
            insert_sql = """
            INSERT INTO trades (
                exchange_name, symbol_name, trade_id, price, quantity, 
                quote_quantity, timestamp, is_buyer_maker
            ) VALUES
            """
            
            await clickhouse_client.execute(insert_sql, *trades_data)
            
            end_time = time.time()
            duration = end_time - start_time
            
            # 验证性能指标
            inserts_per_second = batch_size / duration
            print(f"插入性能: {inserts_per_second:.2f} 记录/秒")
            print(f"批量插入{batch_size}条记录耗时: {duration:.2f}秒")
            
            # 性能应该大于100记录/秒
            assert inserts_per_second > 100, f"插入性能过低: {inserts_per_second:.2f} 记录/秒"
            
        except Exception as e:
            pytest.fail(f"插入性能测试失败: {e}")
    
    @pytest.mark.asyncio
    async def test_query_performance(self, clickhouse_client):
        """测试查询性能"""
        try:
            # 测试复杂查询性能
            start_time = time.time()
            
            query_sql = """
            SELECT 
                symbol_name,
                toStartOfMinute(timestamp) as minute,
                COUNT(*) as trade_count,
                AVG(price) as avg_price,
                SUM(quantity) as volume
            FROM trades 
            WHERE timestamp >= now() - INTERVAL 1 DAY
            GROUP BY symbol_name, minute
            ORDER BY minute DESC, trade_count DESC
            LIMIT 100
            """
            
            result = await clickhouse_client.execute(query_sql)
            
            end_time = time.time()
            duration = end_time - start_time
            
            # 验证查询结果和性能
            assert isinstance(result, list), "查询结果应该是列表"
            
            print(f"查询性能: {duration:.2f}秒")
            print(f"查询结果: {len(result)}条记录")
            
            # 查询应该在5秒内完成
            assert duration < 5, f"查询性能过低: {duration:.2f}秒"
            
        except Exception as e:
            pytest.fail(f"查询性能测试失败: {e}")


class TestRealDataIntegrity:
    """测试真实数据完整性"""
    
    @pytest.mark.asyncio
    async def test_data_consistency(self, clickhouse_client):
        """测试数据一致性"""
        try:
            # 插入测试数据
            timestamp = datetime.now(timezone.utc)
            test_trade_id = f"consistency_test_{int(time.time())}"
            
            insert_sql = """
            INSERT INTO trades (
                exchange_name, symbol_name, trade_id, price, quantity, 
                quote_quantity, timestamp, is_buyer_maker
            ) VALUES
            """
            
            await clickhouse_client.execute(
                insert_sql,
                [
                    "binance",
                    "BTCUSDT",
                    test_trade_id,
                    50000.00,
                    0.1,
                    5000.00,
                    timestamp,
                    1
                ]
            )
            
            # 立即查询数据
            result = await clickhouse_client.execute(
                "SELECT * FROM trades WHERE trade_id = %s",
                [test_trade_id]
            )
            
            # 验证数据一致性
            assert len(result) == 1, "应该查询到一条记录"
            
            trade_data = result[0]
            assert trade_data[0] == "binance", "交易所名称不匹配"
            assert trade_data[1] == "BTCUSDT", "交易对不匹配"
            assert trade_data[2] == test_trade_id, "交易ID不匹配"
            assert float(trade_data[3]) == 50000.00, "价格不匹配"
            assert float(trade_data[4]) == 0.1, "数量不匹配"
            
            print(f"数据一致性验证通过: {test_trade_id}")
            
        except Exception as e:
            pytest.fail(f"数据一致性测试失败: {e}")
    
    @pytest.mark.asyncio
    async def test_data_durability(self, clickhouse_client):
        """测试数据持久性"""
        try:
            # 插入测试数据
            timestamp = datetime.now(timezone.utc)
            test_trade_id = f"durability_test_{int(time.time())}"
            
            insert_sql = """
            INSERT INTO trades (
                exchange_name, symbol_name, trade_id, price, quantity, 
                quote_quantity, timestamp, is_buyer_maker
            ) VALUES
            """
            
            await clickhouse_client.execute(
                insert_sql,
                [
                    "binance",
                    "BTCUSDT",
                    test_trade_id,
                    50000.00,
                    0.1,
                    5000.00,
                    timestamp,
                    1
                ]
            )
            
            # 等待一段时间后再查询
            await asyncio.sleep(2)
            
            result = await clickhouse_client.execute(
                "SELECT COUNT(*) FROM trades WHERE trade_id = %s",
                [test_trade_id]
            )
            
            # 验证数据持久性
            assert result[0] == 1, "数据未持久化保存"
            print(f"数据持久性验证通过: {test_trade_id}")
            
        except Exception as e:
            pytest.fail(f"数据持久性测试失败: {e}")


if __name__ == "__main__":
    # 运行测试前的说明
    print("=" * 60)
    print("真实ClickHouse集成测试")
    print("=" * 60)
    print("运行此测试需要先启动ClickHouse服务:")
    print("docker-compose up clickhouse")
    print("=" * 60)
    
    pytest.main([__file__, "-v", "-s"]) 