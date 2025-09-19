#!/usr/bin/env python3
"""
MarketPrism 生产环境端到端验证脚本
验证JetStream纯架构的数据流完整性
"""
import asyncio
import json
import os
import time
from datetime import datetime, timezone
from typing import Dict, Any

import nats
import requests


class ProductionE2EValidator:
    """生产环境端到端验证器"""
    
    def __init__(self):
        self.nats_url = os.getenv("NATS_URL", "nats://localhost:4222")
        self.clickhouse_url = os.getenv("CLICKHOUSE_HTTP", "http://localhost:8123")
        self.collector_health_url = "http://localhost:8086/health"
        self.storage_health_url = "http://localhost:18080/health"
        self.storage_metrics_url = "http://localhost:18080/metrics"
        
    async def validate_system_health(self):
        """验证系统健康状态"""
        print("=== 系统健康检查 ===")
        
        # 检查Collector健康状态
        try:
            response = requests.get(self.collector_health_url, timeout=5)
            if response.status_code == 200:
                print("✅ Data Collector: 健康")
            else:
                print(f"⚠️ Data Collector: 状态码 {response.status_code}")
        except Exception as e:
            print(f"❌ Data Collector: 不可达 ({e})")
        
        # 检查Storage健康状态
        try:
            response = requests.get(self.storage_health_url, timeout=5)
            if response.status_code == 200:
                health_data = response.json()
                print(f"✅ Hot Storage: {health_data.get('status', 'unknown')}")
                print(f"   - NATS连接: {'✅' if health_data.get('nats_connected') else '❌'}")
                print(f"   - 订阅数: {health_data.get('subscriptions', 0)}")
            else:
                print(f"⚠️ Hot Storage: 状态码 {response.status_code}")
        except Exception as e:
            print(f"❌ Hot Storage: 不可达 ({e})")
        
        # 检查ClickHouse健康状态
        try:
            response = requests.get(f"{self.clickhouse_url}/ping", timeout=5)
            if response.status_code == 200:
                print("✅ ClickHouse: 健康")
            else:
                print(f"⚠️ ClickHouse: 状态码 {response.status_code}")
        except Exception as e:
            print(f"❌ ClickHouse: 不可达 ({e})")

    async def validate_jetstream_architecture(self):
        """验证JetStream架构"""
        print("\n=== JetStream架构验证 ===")
        
        try:
            nc = await nats.connect(self.nats_url)
            jsm = nc.jsm()
            
            # 验证MARKET_DATA流
            try:
                market_data_info = await jsm.stream_info("MARKET_DATA")
                print(f"✅ MARKET_DATA流: {market_data_info.state.messages} 消息")
                print(f"   - 主题: {', '.join(market_data_info.config.subjects)}")
                print(f"   - 存储: {market_data_info.state.bytes / 1024 / 1024:.1f}MB")
            except Exception as e:
                print(f"❌ MARKET_DATA流: {e}")
            
            # 验证ORDERBOOK_SNAP流
            try:
                orderbook_info = await jsm.stream_info("ORDERBOOK_SNAP")
                print(f"✅ ORDERBOOK_SNAP流: {orderbook_info.state.messages} 消息")
                print(f"   - 主题: {', '.join(orderbook_info.config.subjects)}")
                print(f"   - 存储: {orderbook_info.state.bytes / 1024 / 1024:.1f}MB")
            except Exception as e:
                print(f"❌ ORDERBOOK_SNAP流: {e}")
            
            # 验证消费者配置
            consumers_to_check = [
                ("MARKET_DATA", "simple_hot_storage_realtime_trade"),
                ("ORDERBOOK_SNAP", "simple_hot_storage_realtime_orderbook"),
                ("MARKET_DATA", "simple_hot_storage_realtime_liquidation")
            ]
            
            print("\n--- 消费者配置验证 ---")
            for stream_name, consumer_name in consumers_to_check:
                try:
                    info = await jsm.consumer_info(stream_name, consumer_name)
                    config = info.config
                    
                    print(f"✅ {consumer_name}:")
                    print(f"   - 策略: {config.deliver_policy}")
                    print(f"   - ACK: {config.ack_policy}")
                    print(f"   - 待处理: {info.num_pending}")
                    
                    # 兼容不同nats客户端返回类型（枚举/字符串）
                    def _to_name_lower(v):
                        try:
                            return v.name.lower()
                        except Exception:
                            return str(v).lower()

                    deliver_ok = _to_name_lower(config.deliver_policy) == "last"
                    ack_ok = _to_name_lower(config.ack_policy) == "explicit"
                    ack_wait_ok = False
                    try:
                        ack_wait_ok = int(float(getattr(config, 'ack_wait', 60))) == 60
                    except Exception:
                        ack_wait_ok = False
                    max_ack_ok = int(getattr(config, 'max_ack_pending', 2000)) == 2000

                    if all([deliver_ok, ack_ok, ack_wait_ok, max_ack_ok]):
                        print("   - 配置: ✅ 符合LSR标准")
                    else:
                        print("   - 配置: ⚠️ 不符合LSR标准")
                        
                except Exception as e:
                    print(f"❌ {consumer_name}: {e}")
            
            await nc.close()
            
        except Exception as e:
            print(f"❌ JetStream连接失败: {e}")

    async def validate_data_flow(self):
        """验证数据流"""
        print("\n=== 数据流验证 ===")
        
        # 检查ClickHouse表数据
        tables = ["trades", "orderbooks", "liquidations"]
        
        for table in tables:
            try:
                # 检查最近5分钟数据
                query = f"SELECT count() FROM marketprism_hot.{table} WHERE timestamp > now() - INTERVAL 5 MINUTE"
                response = requests.get(f"{self.clickhouse_url}/?query={query}", timeout=10)
                
                if response.status_code == 200:
                    count = int(response.text.strip())
                    print(f"✅ {table}: 最近5分钟 {count} 条记录")
                    
                    if count > 0:
                        # 检查最新时间戳
                        query = f"SELECT max(timestamp) FROM marketprism_hot.{table}"
                        response = requests.get(f"{self.clickhouse_url}/?query={query}", timeout=10)
                        if response.status_code == 200:
                            latest_ts = response.text.strip()
                            print(f"   - 最新时间: {latest_ts}")
                    else:
                        print("   - ⚠️ 无最近数据")
                else:
                    print(f"❌ {table}: 查询失败 (状态码: {response.status_code})")
                    
            except Exception as e:
                print(f"❌ {table}: 查询异常 ({e})")

    async def validate_performance_metrics(self):
        """验证性能指标"""
        print("\n=== 性能指标验证 ===")
        
        try:
            response = requests.get(self.storage_metrics_url, timeout=5)
            if response.status_code == 200:
                metrics_text = response.text
                
                # 解析关键指标
                for line in metrics_text.split('\n'):
                    if 'hot_storage_messages_processed_total' in line and not line.startswith('#'):
                        processed = line.split()[-1]
                        print(f"✅ 已处理消息: {processed}")
                    elif 'hot_storage_messages_failed_total' in line and not line.startswith('#'):
                        failed = line.split()[-1]
                        print(f"✅ 失败消息: {failed}")
                    elif 'hot_storage_error_rate_percent' in line and not line.startswith('#'):
                        error_rate = line.split()[-1]
                        print(f"✅ 错误率: {error_rate}%")
            else:
                print(f"⚠️ 指标获取失败: 状态码 {response.status_code}")
                
        except Exception as e:
            print(f"❌ 指标获取异常: {e}")

    async def run_validation(self):
        """运行完整验证"""
        print(f"🚀 MarketPrism 生产环境端到端验证")
        print(f"时间: {datetime.now(timezone.utc).isoformat()}")
        print(f"NATS: {self.nats_url}")
        print(f"ClickHouse: {self.clickhouse_url}")
        
        await self.validate_system_health()
        await self.validate_jetstream_architecture()
        await self.validate_data_flow()
        await self.validate_performance_metrics()
        
        print(f"\n✅ 验证完成 @ {datetime.now(timezone.utc).isoformat()}")


async def main():
    """主函数"""
    validator = ProductionE2EValidator()
    await validator.run_validation()


if __name__ == "__main__":
    asyncio.run(main())
