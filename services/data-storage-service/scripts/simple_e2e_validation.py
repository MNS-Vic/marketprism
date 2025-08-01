#!/usr/bin/env python3
"""
MarketPrism 简化端到端验证脚本
验证基本的数据流：NATS → ClickHouse
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
import nats
from nats.js import JetStreamContext
import aiohttp

# 添加项目根目录到Python路径
project_root = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(project_root))


class SimpleE2EValidator:
    """简化的端到端验证器"""
    
    def __init__(self, config: Dict[str, Any]):
        """
        初始化验证器
        
        Args:
            config: 配置字典
        """
        self.config = config
        
        # NATS配置
        self.nats_config = config.get('nats', {})
        self.nats_client: Optional[nats.NATS] = None
        self.jetstream: Optional[JetStreamContext] = None
        
        # 存储配置
        self.hot_config = config.get('hot_storage', {})
        
        # 验证结果
        self.results = {
            "nats_connection": False,
            "clickhouse_connection": False,
            "data_flow_tests": {},
            "summary": {}
        }
    
    async def run_validation(self):
        """运行验证"""
        try:
            print("🚀 开始简化端到端验证")
            print("="*60)
            
            # 1. 验证NATS连接
            await self._test_nats_connection()
            
            # 2. 验证ClickHouse连接
            await self._test_clickhouse_connection()
            
            # 3. 验证数据流
            await self._test_data_flow()
            
            # 4. 生成报告
            self._generate_report()
            
            print("\n✅ 简化端到端验证完成")
            
        except Exception as e:
            print(f"\n❌ 验证失败: {e}")
            raise
        finally:
            await self._cleanup()
    
    async def _test_nats_connection(self):
        """测试NATS连接"""
        try:
            print("\n📡 测试NATS连接...")
            
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
            
            self.results["nats_connection"] = True
            print(f"✅ NATS连接成功: {nats_url}")
            
        except Exception as e:
            self.results["nats_connection"] = False
            print(f"❌ NATS连接失败: {e}")
            raise
    
    async def _test_clickhouse_connection(self):
        """测试ClickHouse连接"""
        try:
            print("\n🗄️ 测试ClickHouse连接...")
            
            host = self.hot_config.get('clickhouse_host', 'localhost')
            port = self.hot_config.get('clickhouse_http_port', 8123)
            database = self.hot_config.get('clickhouse_database', 'marketprism_hot')
            
            # 测试连接
            url = f"http://{host}:{port}/"
            query = "SELECT 1"
            
            async with aiohttp.ClientSession() as session:
                async with session.post(url, data=query) as response:
                    if response.status == 200:
                        result = await response.text()
                        print(f"✅ ClickHouse连接成功: {host}:{port}")
                        
                        # 测试数据库访问
                        query = f"SELECT count() FROM system.tables WHERE database = '{database}'"
                        async with session.post(url, data=query) as db_response:
                            if db_response.status == 200:
                                table_count = await db_response.text()
                                print(f"✅ 数据库访问成功: {database} (表数量: {table_count.strip()})")
                                self.results["clickhouse_connection"] = True
                            else:
                                error_text = await db_response.text()
                                print(f"❌ 数据库访问失败: {error_text}")
                                self.results["clickhouse_connection"] = False
                    else:
                        error_text = await response.text()
                        print(f"❌ ClickHouse连接失败: {error_text}")
                        self.results["clickhouse_connection"] = False
            
        except Exception as e:
            self.results["clickhouse_connection"] = False
            print(f"❌ ClickHouse连接测试失败: {e}")
            raise
    
    async def _test_data_flow(self):
        """测试数据流"""
        try:
            print("\n🔄 测试数据流...")
            
            # 测试数据类型
            data_types = ["orderbook", "trade", "funding_rate"]
            
            for data_type in data_types:
                try:
                    print(f"\n  📊 测试 {data_type} 数据流...")
                    
                    # 生成测试数据
                    test_data = self._generate_test_data(data_type)
                    
                    # 发布到NATS
                    await self._publish_test_data(data_type, test_data)
                    print(f"    ✅ NATS发布成功")
                    
                    # 等待数据处理
                    await asyncio.sleep(3)
                    
                    # 验证ClickHouse存储
                    stored = await self._verify_clickhouse_storage(data_type)
                    
                    if stored:
                        print(f"    ✅ ClickHouse存储验证成功")
                        self.results["data_flow_tests"][data_type] = "success"
                    else:
                        print(f"    ❌ ClickHouse存储验证失败")
                        self.results["data_flow_tests"][data_type] = "failed"
                    
                except Exception as e:
                    print(f"    ❌ {data_type} 数据流测试失败: {e}")
                    self.results["data_flow_tests"][data_type] = f"error: {e}"
            
        except Exception as e:
            print(f"❌ 数据流测试失败: {e}")
            raise
    
    def _generate_test_data(self, data_type: str) -> Dict[str, Any]:
        """生成测试数据"""
        base_data = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "exchange": "test_exchange",
            "market_type": "spot",
            "symbol": "BTC-USDT",
            "data_source": "simple_e2e_test"
        }
        
        if data_type == "orderbook":
            return {
                **base_data,
                "last_update_id": 12345,
                "bids": json.dumps([["50000.00", "1.0"]]),
                "asks": json.dumps([["50001.00", "1.5"]]),
                "best_bid_price": 50000.00,
                "best_ask_price": 50001.00
            }
        
        elif data_type == "trade":
            return {
                **base_data,
                "trade_id": "test_trade_123",
                "price": 50000.50,
                "quantity": 0.1,
                "side": "buy",
                "is_maker": False
            }
        
        elif data_type == "funding_rate":
            return {
                **base_data,
                "funding_rate": 0.0001,
                "funding_time": datetime.now(timezone.utc).isoformat(),
                "next_funding_time": (datetime.now(timezone.utc) + timedelta(hours=8)).isoformat()
            }
        
        else:
            return base_data
    
    async def _publish_test_data(self, data_type: str, test_data: Dict[str, Any]):
        """发布测试数据到NATS"""
        try:
            # 根据stream配置调整subject命名
            subject_mapping = {
                "funding_rate": "funding-rate.test_exchange.spot.BTC-USDT",
                "open_interest": "open-interest.test_exchange.spot.BTC-USDT",
            }

            if data_type in subject_mapping:
                subject = subject_mapping[data_type]
            else:
                subject = f"{data_type}-data.test_exchange.spot.BTC-USDT"

            message = json.dumps(test_data).encode()
            await self.jetstream.publish(subject, message)

        except Exception as e:
            print(f"❌ 发布测试数据失败: {e}")
            raise
    
    async def _verify_clickhouse_storage(self, data_type: str) -> bool:
        """验证ClickHouse存储"""
        try:
            host = self.hot_config.get('clickhouse_host', 'localhost')
            port = self.hot_config.get('clickhouse_http_port', 8123)
            database = self.hot_config.get('clickhouse_database', 'marketprism_hot')

            # 获取表名
            table_mapping = {
                "orderbook": "orderbooks",
                "trade": "trades",
                "funding_rate": "funding_rates"
            }
            table_name = table_mapping.get(data_type, data_type)

            # 查询数据
            url = f"http://{host}:{port}/?database={database}"
            query = f"""
                SELECT count() as count FROM {table_name}
                WHERE data_source = 'simple_e2e_test'
                AND timestamp >= now() - INTERVAL 1 MINUTE
            """

            async with aiohttp.ClientSession() as session:
                async with session.post(url, data=query) as response:
                    if response.status == 200:
                        result = await response.text()
                        count = int(result.strip()) if result.strip().isdigit() else 0

                        if count > 0:
                            # 显示存储的数据样本
                            sample_query = f"""
                                SELECT * FROM {table_name}
                                WHERE data_source = 'simple_e2e_test'
                                ORDER BY timestamp DESC LIMIT 1
                            """
                            async with session.post(url, data=sample_query) as sample_response:
                                if sample_response.status == 200:
                                    sample_data = await sample_response.text()
                                    print(f"    📊 存储的数据样本: {sample_data.strip()}")

                        return count > 0
                    else:
                        error_text = await response.text()
                        print(f"    ⚠️ 查询失败: {error_text}")
                        return False

        except Exception as e:
            print(f"    ⚠️ 验证存储异常: {e}")
            return False
    
    def _generate_report(self):
        """生成验证报告"""
        print("\n" + "="*60)
        print("📊 验证报告")
        print("="*60)
        
        # 连接测试
        print("\n🔗 连接测试:")
        print(f"  - NATS: {'✅ 通过' if self.results['nats_connection'] else '❌ 失败'}")
        print(f"  - ClickHouse: {'✅ 通过' if self.results['clickhouse_connection'] else '❌ 失败'}")
        
        # 数据流测试
        print("\n🔄 数据流测试:")
        total_tests = len(self.results["data_flow_tests"])
        passed_tests = len([r for r in self.results["data_flow_tests"].values() if r == "success"])
        
        for data_type, result in self.results["data_flow_tests"].items():
            status = "✅ 通过" if result == "success" else f"❌ {result}"
            print(f"  - {data_type}: {status}")
        
        # 总结
        print(f"\n📋 总结:")
        print(f"  - 数据流测试: {passed_tests}/{total_tests} 通过")
        
        overall_success = (
            self.results["nats_connection"] and 
            self.results["clickhouse_connection"] and 
            passed_tests == total_tests
        )
        
        if overall_success:
            print("  - 整体状态: 🎉 全部通过")
        else:
            print("  - 整体状态: ⚠️ 部分失败")
        
        print("="*60)
    
    async def _cleanup(self):
        """清理资源"""
        try:
            print("\n🧹 清理测试数据...")
            
            # 清理ClickHouse测试数据
            host = self.hot_config.get('clickhouse_host', 'localhost')
            port = self.hot_config.get('clickhouse_http_port', 8123)
            database = self.hot_config.get('clickhouse_database', 'marketprism_hot')
            
            cleanup_queries = [
                f"DELETE FROM {database}.orderbooks WHERE data_source = 'simple_e2e_test'",
                f"DELETE FROM {database}.trades WHERE data_source = 'simple_e2e_test'",
                f"DELETE FROM {database}.funding_rates WHERE data_source = 'simple_e2e_test'"
            ]
            
            url = f"http://{host}:{port}/"
            
            async with aiohttp.ClientSession() as session:
                for query in cleanup_queries:
                    try:
                        async with session.post(url, data=query) as response:
                            if response.status == 200:
                                print(f"    ✅ 清理完成: {query.split()[2]}")
                            else:
                                error_text = await response.text()
                                print(f"    ⚠️ 清理失败: {error_text}")
                    except Exception as e:
                        print(f"    ⚠️ 清理异常: {e}")
            
            # 关闭NATS连接
            if self.nats_client:
                await self.nats_client.close()
                print("    ✅ NATS连接已关闭")
            
        except Exception as e:
            print(f"⚠️ 清理失败: {e}")


async def main():
    """主函数"""
    try:
        print("🚀 MarketPrism 简化端到端验证")
        
        # 加载配置
        config_path = Path(__file__).parent.parent / "config" / "tiered_storage_config.yaml"
        
        if not config_path.exists():
            print(f"❌ 配置文件不存在: {config_path}")
            sys.exit(1)
        
        with open(config_path, 'r', encoding='utf-8') as f:
            config = yaml.safe_load(f)
        
        # 运行验证
        validator = SimpleE2EValidator(config)
        await validator.run_validation()
        
    except KeyboardInterrupt:
        print("\n⚠️ 验证被用户中断")
        sys.exit(1)
    except Exception as e:
        print(f"\n❌ 验证失败: {e}")
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main())
