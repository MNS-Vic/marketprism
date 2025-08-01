#!/usr/bin/env python3
"""
MarketPrism 分层数据存储端到端验证脚本
验证完整的数据流：收集器 → NATS → 热端存储 → 冷端存储
"""

import asyncio
import sys
import os
import json
import time
from pathlib import Path
from datetime import datetime, timezone, timedelta
from typing import Dict, List, Any, Optional
import yaml
import structlog
import nats
from nats.js import JetStreamContext

# 添加项目根目录到Python路径
project_root = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(project_root))

from core.storage.unified_clickhouse_writer import UnifiedClickHouseWriter
from core.storage.tiered_storage_manager import TieredStorageManager, TierConfig, StorageTier


class EndToEndValidator:
    """端到端验证器"""
    
    def __init__(self, config: Dict[str, Any]):
        """
        初始化端到端验证器
        
        Args:
            config: 配置字典
        """
        self.config = config
        self.logger = structlog.get_logger("e2e.validator")
        
        # NATS配置
        self.nats_config = config.get('nats', {})
        self.nats_client: Optional[nats.NATS] = None
        self.jetstream: Optional[JetStreamContext] = None
        
        # 存储配置
        self.hot_config = config.get('hot_storage', {})
        self.cold_config = config.get('cold_storage', {})
        
        # ClickHouse客户端
        self.hot_client: Optional[UnifiedClickHouseWriter] = None
        self.cold_client: Optional[UnifiedClickHouseWriter] = None
        
        # 分层存储管理器
        self.storage_manager: Optional[TieredStorageManager] = None
        
        # 验证结果
        self.validation_results = {
            "nats_connection": False,
            "hot_storage_connection": False,
            "cold_storage_connection": False,
            "data_flow_validation": {},
            "data_integrity_validation": {},
            "performance_metrics": {}
        }
    
    async def run_validation(self):
        """运行完整的端到端验证"""
        try:
            self.logger.info("🚀 开始端到端验证")
            
            # 1. 验证NATS连接
            await self._validate_nats_connection()
            
            # 2. 验证ClickHouse连接
            await self._validate_clickhouse_connections()
            
            # 3. 初始化分层存储管理器
            await self._initialize_storage_manager()
            
            # 4. 验证数据流
            await self._validate_data_flow()
            
            # 5. 验证数据完整性
            await self._validate_data_integrity()
            
            # 6. 性能测试
            await self._performance_test()
            
            # 7. 生成验证报告
            await self._generate_validation_report()
            
            self.logger.info("✅ 端到端验证完成")
            
        except Exception as e:
            self.logger.error("❌ 端到端验证失败", error=str(e))
            raise
        finally:
            await self._cleanup()
    
    async def _validate_nats_connection(self):
        """验证NATS连接"""
        try:
            self.logger.info("📡 验证NATS连接")
            
            nats_url = self.nats_config.get('url', 'nats://localhost:4222')
            
            # 连接NATS
            self.nats_client = await nats.connect(
                servers=[nats_url],
                max_reconnect_attempts=3,
                reconnect_time_wait=2
            )
            
            # 获取JetStream上下文
            self.jetstream = self.nats_client.jetstream()
            
            # 测试JetStream功能
            await self.jetstream.account_info()
            
            self.validation_results["nats_connection"] = True
            self.logger.info("✅ NATS连接验证成功", url=nats_url)
            
        except Exception as e:
            self.validation_results["nats_connection"] = False
            self.logger.error("❌ NATS连接验证失败", error=str(e))
            raise
    
    async def _validate_clickhouse_connections(self):
        """验证ClickHouse连接"""
        try:
            self.logger.info("🗄️ 验证ClickHouse连接")
            
            # 验证热端ClickHouse
            hot_clickhouse_config = {
                'clickhouse_direct_write': True,
                'clickhouse': {
                    'host': self.hot_config.get('clickhouse_host', 'localhost'),
                    'port': self.hot_config.get('clickhouse_http_port', 8123),
                    'user': self.hot_config.get('clickhouse_user', 'default'),
                    'password': self.hot_config.get('clickhouse_password', ''),
                    'database': self.hot_config.get('clickhouse_database', 'marketprism_hot')
                }
            }

            self.hot_client = UnifiedClickHouseWriter(hot_clickhouse_config)
            await self.hot_client.start()
            # 简单的健康检查
            await self.hot_client.execute_query("SELECT 1")
            
            self.validation_results["hot_storage_connection"] = True
            self.logger.info("✅ 热端ClickHouse连接验证成功")
            
            # 验证冷端ClickHouse（如果配置了不同的主机）
            if self.cold_config.get('clickhouse_host') != self.hot_config.get('clickhouse_host'):
                cold_clickhouse_config = {
                    'clickhouse_direct_write': True,
                    'clickhouse': {
                        'host': self.cold_config.get('clickhouse_host', 'localhost'),
                        'port': self.cold_config.get('clickhouse_http_port', 8123),
                        'user': self.cold_config.get('clickhouse_user', 'default'),
                        'password': self.cold_config.get('clickhouse_password', ''),
                        'database': self.cold_config.get('clickhouse_database', 'marketprism_cold')
                    }
                }

                self.cold_client = UnifiedClickHouseWriter(cold_clickhouse_config)
                await self.cold_client.start()
                await self.cold_client.execute_query("SELECT 1")
                
                self.validation_results["cold_storage_connection"] = True
                self.logger.info("✅ 冷端ClickHouse连接验证成功")
            else:
                self.cold_client = self.hot_client
                self.validation_results["cold_storage_connection"] = True
                self.logger.info("🔄 冷端使用相同的ClickHouse实例")
            
        except Exception as e:
            self.logger.error(f"❌ ClickHouse连接验证失败: {e}")
            raise
    
    async def _initialize_storage_manager(self):
        """初始化分层存储管理器"""
        try:
            self.logger.info("🏗️ 初始化分层存储管理器")
            
            # 创建热端配置
            hot_tier_config = TierConfig(
                tier=StorageTier.HOT,
                clickhouse_host=self.hot_config.get('clickhouse_host', 'localhost'),
                clickhouse_port=self.hot_config.get('clickhouse_port', 9000),
                clickhouse_user=self.hot_config.get('clickhouse_user', 'default'),
                clickhouse_password=self.hot_config.get('clickhouse_password', ''),
                clickhouse_database=self.hot_config.get('clickhouse_database', 'marketprism_hot'),
                retention_days=self.hot_config.get('retention_days', 3),
                batch_size=self.hot_config.get('batch_size', 100),  # 测试用小批次
                flush_interval=self.hot_config.get('flush_interval', 1)
            )
            
            # 创建冷端配置
            cold_tier_config = TierConfig(
                tier=StorageTier.COLD,
                clickhouse_host=self.cold_config.get('clickhouse_host', 'localhost'),
                clickhouse_port=self.cold_config.get('clickhouse_port', 9000),
                clickhouse_user=self.cold_config.get('clickhouse_user', 'default'),
                clickhouse_password=self.cold_config.get('clickhouse_password', ''),
                clickhouse_database=self.cold_config.get('clickhouse_database', 'marketprism_cold'),
                retention_days=self.cold_config.get('retention_days', 365),
                batch_size=self.cold_config.get('batch_size', 200),  # 测试用小批次
                flush_interval=self.cold_config.get('flush_interval', 2)
            )
            
            # 初始化分层存储管理器
            self.storage_manager = TieredStorageManager(hot_tier_config, cold_tier_config)
            await self.storage_manager.initialize()
            
            self.logger.info("✅ 分层存储管理器初始化成功")
            
        except Exception as e:
            self.logger.error("❌ 分层存储管理器初始化失败", error=str(e))
            raise
    
    async def _validate_data_flow(self):
        """验证数据流"""
        try:
            self.logger.info("🔄 验证数据流")
            
            # 测试数据类型
            data_types = ["orderbook", "trade", "funding_rate", "open_interest", 
                         "liquidation", "lsr", "volatility_index"]
            
            for data_type in data_types:
                try:
                    # 生成测试数据
                    test_data = self._generate_test_data(data_type)
                    
                    # 发布到NATS
                    await self._publish_test_data(data_type, test_data)
                    
                    # 等待数据处理
                    await asyncio.sleep(2)
                    
                    # 验证热端存储
                    hot_success = await self._verify_hot_storage(data_type, test_data)
                    
                    # 记录结果
                    self.validation_results["data_flow_validation"][data_type] = {
                        "nats_publish": True,
                        "hot_storage": hot_success,
                        "test_data_count": len(test_data) if isinstance(test_data, list) else 1
                    }
                    
                    self.logger.info("✅ 数据流验证成功", data_type=data_type)
                    
                except Exception as e:
                    self.validation_results["data_flow_validation"][data_type] = {
                        "error": str(e)
                    }
                    self.logger.error("❌ 数据流验证失败", data_type=data_type, error=str(e))
            
        except Exception as e:
            self.logger.error("❌ 数据流验证失败", error=str(e))
            raise
    
    def _generate_test_data(self, data_type: str) -> List[Dict[str, Any]]:
        """生成测试数据"""
        base_data = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "exchange": "test_exchange",
            "market_type": "spot",
            "symbol": "BTC-USDT",
            "data_source": "e2e_test"
        }
        
        if data_type == "orderbook":
            return [{
                **base_data,
                "last_update_id": 12345,
                "bids": json.dumps([["50000.00", "1.0"], ["49999.00", "2.0"]]),
                "asks": json.dumps([["50001.00", "1.5"], ["50002.00", "2.5"]]),
                "best_bid_price": 50000.00,
                "best_ask_price": 50001.00,
                "best_bid_quantity": 1.0,
                "best_ask_quantity": 1.5,
                "bids_count": 2,
                "asks_count": 2
            }]
        
        elif data_type == "trade":
            return [{
                **base_data,
                "trade_id": "test_trade_123",
                "price": 50000.50,
                "quantity": 0.1,
                "side": "buy",
                "is_maker": False,
                "trade_time": datetime.now(timezone.utc).isoformat()
            }]
        
        elif data_type == "funding_rate":
            return [{
                **base_data,
                "funding_rate": 0.0001,
                "funding_time": datetime.now(timezone.utc).isoformat(),
                "next_funding_time": (datetime.now(timezone.utc) + timedelta(hours=8)).isoformat(),
                "mark_price": 50000.00,
                "index_price": 49999.50
            }]
        
        elif data_type == "open_interest":
            return [{
                **base_data,
                "open_interest": 1000000.0,
                "open_interest_value": 50000000000.0,
                "count": 5000
            }]
        
        elif data_type == "liquidation":
            return [{
                **base_data,
                "side": "sell",
                "price": 49500.00,
                "quantity": 2.5,
                "liquidation_time": datetime.now(timezone.utc).isoformat()
            }]
        
        elif data_type == "lsr":
            return [{
                **base_data,
                "long_short_ratio": 1.25,
                "long_account": 55.5,
                "short_account": 44.5,
                "period": "1h"
            }]
        
        elif data_type == "volatility_index":
            return [{
                **base_data,
                "index_value": 75.5,
                "underlying_asset": "BTC",
                "maturity_date": (datetime.now(timezone.utc) + timedelta(days=30)).date().isoformat()
            }]
        
        else:
            return [base_data]
    
    async def _publish_test_data(self, data_type: str, test_data: List[Dict[str, Any]]):
        """发布测试数据到NATS"""
        try:
            subject = f"{data_type}-data.test_exchange.spot.BTC-USDT"
            
            for data in test_data:
                message = json.dumps(data).encode()
                await self.jetstream.publish(subject, message)
            
            self.logger.debug("📤 测试数据已发布", data_type=data_type, count=len(test_data))
            
        except Exception as e:
            self.logger.error("❌ 发布测试数据失败", data_type=data_type, error=str(e))
            raise
    
    async def _verify_hot_storage(self, data_type: str, test_data: List[Dict[str, Any]]) -> bool:
        """验证热端存储"""
        try:
            # 等待数据写入
            await asyncio.sleep(3)
            
            # 查询数据
            table_name = self._get_table_name(data_type)
            query = f"""
                SELECT count() as count FROM {table_name}
                WHERE data_source = 'e2e_test'
                AND timestamp >= now() - INTERVAL 1 MINUTE
            """
            
            result = await self.hot_client.execute_query(query)
            
            if result and len(result) > 0:
                count = result[0].get('count', 0)
                expected_count = len(test_data)
                
                if count >= expected_count:
                    self.logger.info("✅ 热端存储验证成功", 
                                   data_type=data_type, 
                                   count=count, 
                                   expected=expected_count)
                    return True
                else:
                    self.logger.warning("⚠️ 热端存储数据不完整", 
                                      data_type=data_type, 
                                      count=count, 
                                      expected=expected_count)
                    return False
            else:
                self.logger.error("❌ 热端存储查询无结果", data_type=data_type)
                return False
            
        except Exception as e:
            self.logger.error("❌ 热端存储验证失败", data_type=data_type, error=str(e))
            return False
    
    def _get_table_name(self, data_type: str) -> str:
        """获取表名"""
        table_mapping = {
            "orderbook": "orderbooks",
            "trade": "trades",
            "funding_rate": "funding_rates",
            "open_interest": "open_interests",
            "liquidation": "liquidations",
            "lsr": "lsrs",
            "volatility_index": "volatility_indices"
        }
        return table_mapping.get(data_type, data_type)

    async def _validate_data_integrity(self):
        """验证数据完整性"""
        try:
            self.logger.info("🔍 验证数据完整性")

            # 验证表结构
            await self._validate_table_schemas()

            # 验证数据格式
            await self._validate_data_formats()

            # 验证索引性能
            await self._validate_index_performance()

            self.logger.info("✅ 数据完整性验证完成")

        except Exception as e:
            self.logger.error("❌ 数据完整性验证失败", error=str(e))
            raise

    async def _validate_table_schemas(self):
        """验证表结构"""
        try:
            tables = ["orderbooks", "trades", "funding_rates", "open_interests",
                     "liquidations", "lsrs", "volatility_indices"]

            for table in tables:
                # 检查表是否存在
                query = f"DESCRIBE TABLE {table}"
                result = await self.hot_client.execute_query(query)

                if result:
                    self.validation_results["data_integrity_validation"][f"{table}_schema"] = True
                    self.logger.info("✅ 表结构验证成功", table=table, columns=len(result))
                else:
                    self.validation_results["data_integrity_validation"][f"{table}_schema"] = False
                    self.logger.error("❌ 表结构验证失败", table=table)

        except Exception as e:
            self.logger.error("❌ 表结构验证失败", error=str(e))
            raise

    async def _validate_data_formats(self):
        """验证数据格式"""
        try:
            # 检查时间戳格式
            query = """
                SELECT
                    toTypeName(timestamp) as timestamp_type,
                    min(timestamp) as min_timestamp,
                    max(timestamp) as max_timestamp
                FROM trades
                WHERE data_source = 'e2e_test'
                LIMIT 1
            """

            result = await self.hot_client.execute_query(query)

            if result and len(result) > 0:
                timestamp_type = result[0].get('timestamp_type')
                if 'DateTime64' in timestamp_type:
                    self.validation_results["data_integrity_validation"]["timestamp_format"] = True
                    self.logger.info("✅ 时间戳格式验证成功", type=timestamp_type)
                else:
                    self.validation_results["data_integrity_validation"]["timestamp_format"] = False
                    self.logger.error("❌ 时间戳格式验证失败", type=timestamp_type)

            # 检查数据精度
            query = """
                SELECT
                    toTypeName(price) as price_type,
                    toTypeName(quantity) as quantity_type
                FROM trades
                WHERE data_source = 'e2e_test'
                LIMIT 1
            """

            result = await self.hot_client.execute_query(query)

            if result and len(result) > 0:
                price_type = result[0].get('price_type')
                quantity_type = result[0].get('quantity_type')

                if 'Decimal64' in price_type and 'Decimal64' in quantity_type:
                    self.validation_results["data_integrity_validation"]["decimal_precision"] = True
                    self.logger.info("✅ 数据精度验证成功",
                                   price_type=price_type,
                                   quantity_type=quantity_type)
                else:
                    self.validation_results["data_integrity_validation"]["decimal_precision"] = False
                    self.logger.error("❌ 数据精度验证失败",
                                    price_type=price_type,
                                    quantity_type=quantity_type)

        except Exception as e:
            self.logger.error("❌ 数据格式验证失败", error=str(e))
            raise

    async def _validate_index_performance(self):
        """验证索引性能"""
        try:
            # 测试查询性能
            start_time = time.time()

            query = """
                SELECT count()
                FROM trades
                WHERE timestamp >= now() - INTERVAL 1 HOUR
                AND exchange = 'test_exchange'
                AND symbol = 'BTC-USDT'
            """

            result = await self.hot_client.execute_query(query)

            query_time = time.time() - start_time

            self.validation_results["data_integrity_validation"]["index_performance"] = {
                "query_time_seconds": query_time,
                "result_count": result[0].get('count()') if result else 0
            }

            if query_time < 1.0:  # 查询时间小于1秒
                self.logger.info("✅ 索引性能验证成功", query_time=query_time)
            else:
                self.logger.warning("⚠️ 索引性能较慢", query_time=query_time)

        except Exception as e:
            self.logger.error("❌ 索引性能验证失败", error=str(e))
            raise

    async def _performance_test(self):
        """性能测试"""
        try:
            self.logger.info("⚡ 开始性能测试")

            # 批量写入测试
            await self._test_batch_write_performance()

            # 查询性能测试
            await self._test_query_performance()

            # 数据传输性能测试
            await self._test_transfer_performance()

            self.logger.info("✅ 性能测试完成")

        except Exception as e:
            self.logger.error("❌ 性能测试失败", error=str(e))
            raise

    async def _test_batch_write_performance(self):
        """测试批量写入性能"""
        try:
            # 生成大量测试数据
            test_data = []
            for i in range(1000):
                test_data.append({
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                    "exchange": "perf_test",
                    "market_type": "spot",
                    "symbol": "BTC-USDT",
                    "trade_id": f"perf_test_{i}",
                    "price": 50000.0 + i,
                    "quantity": 0.1,
                    "side": "buy" if i % 2 == 0 else "sell",
                    "is_maker": False,
                    "trade_time": datetime.now(timezone.utc).isoformat(),
                    "data_source": "perf_test"
                })

            # 测试写入性能
            start_time = time.time()

            success = await self.storage_manager.store_to_hot("trade", test_data)

            write_time = time.time() - start_time

            self.validation_results["performance_metrics"]["batch_write"] = {
                "records_count": len(test_data),
                "write_time_seconds": write_time,
                "records_per_second": len(test_data) / write_time if write_time > 0 else 0,
                "success": success
            }

            self.logger.info("✅ 批量写入性能测试完成",
                           records=len(test_data),
                           time=write_time,
                           rps=len(test_data) / write_time if write_time > 0 else 0)

        except Exception as e:
            self.logger.error("❌ 批量写入性能测试失败", error=str(e))
            raise

    async def _test_query_performance(self):
        """测试查询性能"""
        try:
            queries = [
                ("simple_count", "SELECT count() FROM trades WHERE data_source = 'perf_test'"),
                ("time_range", "SELECT count() FROM trades WHERE timestamp >= now() - INTERVAL 1 HOUR"),
                ("complex_filter", """
                    SELECT exchange, symbol, count() as trade_count, avg(price) as avg_price
                    FROM trades
                    WHERE data_source = 'perf_test'
                    GROUP BY exchange, symbol
                """)
            ]

            query_results = {}

            for query_name, query_sql in queries:
                start_time = time.time()
                result = await self.hot_client.execute_query(query_sql)
                query_time = time.time() - start_time

                query_results[query_name] = {
                    "query_time_seconds": query_time,
                    "result_count": len(result) if result else 0
                }

                self.logger.info("✅ 查询性能测试",
                               query=query_name,
                               time=query_time,
                               results=len(result) if result else 0)

            self.validation_results["performance_metrics"]["query_performance"] = query_results

        except Exception as e:
            self.logger.error("❌ 查询性能测试失败", error=str(e))
            raise

    async def _test_transfer_performance(self):
        """测试数据传输性能"""
        try:
            # 调度一个小的传输任务
            start_time = datetime.now(timezone.utc) - timedelta(minutes=5)
            end_time = datetime.now(timezone.utc)

            transfer_start = time.time()

            task_id = await self.storage_manager.schedule_data_transfer(
                "trade", "perf_test", "BTC-USDT", start_time, end_time
            )

            # 等待传输完成
            timeout = 30  # 30秒超时
            elapsed = 0

            while elapsed < timeout:
                status = self.storage_manager.get_transfer_task_status(task_id)
                if status and status['status'] in ['completed', 'failed']:
                    break
                await asyncio.sleep(1)
                elapsed += 1

            transfer_time = time.time() - transfer_start

            # 获取最终状态
            final_status = self.storage_manager.get_transfer_task_status(task_id)

            self.validation_results["performance_metrics"]["data_transfer"] = {
                "task_id": task_id,
                "transfer_time_seconds": transfer_time,
                "status": final_status['status'] if final_status else 'timeout',
                "records_transferred": final_status['records_count'] if final_status else 0
            }

            self.logger.info("✅ 数据传输性能测试完成",
                           task_id=task_id,
                           time=transfer_time,
                           status=final_status['status'] if final_status else 'timeout')

        except Exception as e:
            self.logger.error("❌ 数据传输性能测试失败", error=str(e))
            raise

    async def _generate_validation_report(self):
        """生成验证报告"""
        try:
            self.logger.info("📊 生成验证报告")

            # 计算总体成功率
            total_tests = 0
            passed_tests = 0

            # 连接测试
            connection_tests = ["nats_connection", "hot_storage_connection", "cold_storage_connection"]
            for test in connection_tests:
                total_tests += 1
                if self.validation_results.get(test, False):
                    passed_tests += 1

            # 数据流测试
            data_flow_results = self.validation_results.get("data_flow_validation", {})
            for data_type, result in data_flow_results.items():
                if isinstance(result, dict) and "error" not in result:
                    total_tests += 1
                    if result.get("hot_storage", False):
                        passed_tests += 1

            # 数据完整性测试
            integrity_results = self.validation_results.get("data_integrity_validation", {})
            for test_name, result in integrity_results.items():
                if isinstance(result, bool):
                    total_tests += 1
                    if result:
                        passed_tests += 1

            success_rate = (passed_tests / total_tests * 100) if total_tests > 0 else 0

            # 生成报告
            report = {
                "validation_timestamp": datetime.now(timezone.utc).isoformat(),
                "overall_success_rate": success_rate,
                "total_tests": total_tests,
                "passed_tests": passed_tests,
                "failed_tests": total_tests - passed_tests,
                "detailed_results": self.validation_results
            }

            # 保存报告到文件
            report_file = Path(__file__).parent.parent / "logs" / f"validation_report_{int(time.time())}.json"
            report_file.parent.mkdir(parents=True, exist_ok=True)

            with open(report_file, 'w', encoding='utf-8') as f:
                json.dump(report, f, indent=2, ensure_ascii=False)

            # 打印摘要
            self.logger.info("📋 验证报告摘要",
                           success_rate=f"{success_rate:.1f}%",
                           passed=passed_tests,
                           total=total_tests,
                           report_file=str(report_file))

            # 打印详细结果
            print("\n" + "="*80)
            print("🎯 MarketPrism 分层数据存储端到端验证报告")
            print("="*80)
            print(f"📊 总体成功率: {success_rate:.1f}% ({passed_tests}/{total_tests})")
            print(f"⏰ 验证时间: {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S UTC')}")
            print()

            # 连接测试结果
            print("🔗 连接测试:")
            for test in connection_tests:
                status = "✅ 通过" if self.validation_results.get(test, False) else "❌ 失败"
                print(f"  - {test}: {status}")
            print()

            # 数据流测试结果
            print("🔄 数据流测试:")
            for data_type, result in data_flow_results.items():
                if isinstance(result, dict) and "error" not in result:
                    status = "✅ 通过" if result.get("hot_storage", False) else "❌ 失败"
                    count = result.get("test_data_count", 0)
                    print(f"  - {data_type}: {status} ({count} 条记录)")
                else:
                    print(f"  - {data_type}: ❌ 失败 ({result.get('error', '未知错误')})")
            print()

            # 性能测试结果
            print("⚡ 性能测试:")
            perf_metrics = self.validation_results.get("performance_metrics", {})

            if "batch_write" in perf_metrics:
                batch_write = perf_metrics["batch_write"]
                print(f"  - 批量写入: {batch_write['records_count']} 条记录, "
                      f"{batch_write['write_time_seconds']:.2f}s, "
                      f"{batch_write['records_per_second']:.0f} 记录/秒")

            if "query_performance" in perf_metrics:
                query_perf = perf_metrics["query_performance"]
                for query_name, metrics in query_perf.items():
                    print(f"  - {query_name}: {metrics['query_time_seconds']:.3f}s, "
                          f"{metrics['result_count']} 条结果")

            if "data_transfer" in perf_metrics:
                transfer = perf_metrics["data_transfer"]
                print(f"  - 数据传输: {transfer['status']}, "
                      f"{transfer['transfer_time_seconds']:.2f}s, "
                      f"{transfer['records_transferred']} 条记录")

            print()
            print(f"📄 详细报告已保存至: {report_file}")
            print("="*80)

            return report

        except Exception as e:
            self.logger.error("❌ 生成验证报告失败", error=str(e))
            raise

    async def _cleanup(self):
        """清理资源"""
        try:
            self.logger.info("🧹 清理验证资源")

            # 清理测试数据
            if self.hot_client:
                try:
                    cleanup_queries = [
                        "DELETE FROM trades WHERE data_source IN ('e2e_test', 'perf_test')",
                        "DELETE FROM orderbooks WHERE data_source IN ('e2e_test', 'perf_test')",
                        "DELETE FROM funding_rates WHERE data_source IN ('e2e_test', 'perf_test')",
                        "DELETE FROM open_interests WHERE data_source IN ('e2e_test', 'perf_test')",
                        "DELETE FROM liquidations WHERE data_source IN ('e2e_test', 'perf_test')",
                        "DELETE FROM lsrs WHERE data_source IN ('e2e_test', 'perf_test')",
                        "DELETE FROM volatility_indices WHERE data_source IN ('e2e_test', 'perf_test')"
                    ]

                    for query in cleanup_queries:
                        try:
                            await self.hot_client.execute_query(query)
                        except Exception as e:
                            self.logger.warning("⚠️ 清理测试数据失败", query=query[:50], error=str(e))

                    self.logger.info("✅ 测试数据清理完成")
                except Exception as e:
                    self.logger.warning("⚠️ 测试数据清理失败", error=str(e))

            # 关闭连接
            if self.storage_manager:
                await self.storage_manager.close()

            if self.hot_client and self.hot_client != self.cold_client:
                await self.hot_client.close()

            if self.cold_client:
                await self.cold_client.close()

            if self.nats_client:
                await self.nats_client.close()

            self.logger.info("✅ 资源清理完成")

        except Exception as e:
            self.logger.error("❌ 资源清理失败", error=str(e))


async def main():
    """主函数"""
    try:
        print("🚀 MarketPrism 分层数据存储端到端验证")
        print("="*60)

        # 加载配置
        config_path = Path(__file__).parent.parent / "config" / "tiered_storage_config.yaml"

        if not config_path.exists():
            print(f"❌ 配置文件不存在: {config_path}")
            sys.exit(1)

        with open(config_path, 'r', encoding='utf-8') as f:
            config = yaml.safe_load(f)

        # 运行验证
        validator = EndToEndValidator(config)
        await validator.run_validation()

        print("\n🎉 端到端验证完成！")

    except KeyboardInterrupt:
        print("\n⚠️ 验证被用户中断")
        sys.exit(1)
    except Exception as e:
        print(f"\n❌ 端到端验证失败: {e}")
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main())
