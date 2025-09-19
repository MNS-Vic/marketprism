#!/usr/bin/env python3
"""
MarketPrism 配置一致性检查脚本
确保从环境变量到运行时配置的一致性
"""
import os
import yaml
import asyncio
import nats
from typing import Dict, Any, List


class ConfigConsistencyChecker:
    """配置一致性检查器"""
    
    def __init__(self):
        self.env_docker_path = "services/message-broker/.env.docker"
        self.collector_config_path = "services/data-collector/config/collector/unified_data_collection.yaml"
        self.nats_url = os.getenv("NATS_URL", "nats://localhost:4222")
        
        # 预期的LSR配置
        self.expected_lsr_config = {
            "LSR_DELIVER_POLICY": "last",
            "LSR_ACK_POLICY": "explicit", 
            "LSR_ACK_WAIT": "60",
            "LSR_MAX_DELIVER": "3",
            "LSR_MAX_ACK_PENDING": "2000"
        }
        
        # 预期的流配置
        self.expected_streams = {
            "MARKET_DATA": {
                "subjects": ["trade.>", "funding_rate.>", "open_interest.>", 
                           "liquidation.>", "volatility_index.>", "lsr_top_position.>", 
                           "lsr_all_account.>"],
                "max_msgs": 5000000,
                "max_bytes": 2147483648,
                "max_age": 172800
            },
            "ORDERBOOK_SNAP": {
                "subjects": ["orderbook.>"],
                "max_msgs": 2000000,
                "max_bytes": 5368709120,
                "max_age": 86400
            }
        }

    def check_env_docker_config(self) -> Dict[str, Any]:
        """检查.env.docker配置"""
        print("=== 检查 .env.docker 配置 ===")
        
        if not os.path.exists(self.env_docker_path):
            print(f"❌ 文件不存在: {self.env_docker_path}")
            return {}
        
        env_config = {}
        with open(self.env_docker_path, 'r', encoding='utf-8') as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith('#') and '=' in line:
                    key, value = line.split('=', 1)
                    env_config[key] = value
        
        # 检查LSR配置
        lsr_consistent = True
        for key, expected_value in self.expected_lsr_config.items():
            actual_value = env_config.get(key)
            if actual_value == expected_value:
                print(f"✅ {key}: {actual_value}")
            else:
                print(f"❌ {key}: 期望 '{expected_value}', 实际 '{actual_value}'")
                lsr_consistent = False
        
        if lsr_consistent:
            print("✅ .env.docker LSR配置一致")
        else:
            print("❌ .env.docker LSR配置不一致")
        
        return env_config

    def check_collector_config(self) -> Dict[str, Any]:
        """检查collector配置"""
        print("\n=== 检查 Collector 配置 ===")
        
        if not os.path.exists(self.collector_config_path):
            print(f"❌ 文件不存在: {self.collector_config_path}")
            return {}
        
        with open(self.collector_config_path, 'r', encoding='utf-8') as f:
            config = yaml.safe_load(f)
        
        # 检查JetStream流配置
        jetstream_config = config.get('nats', {}).get('jetstream', {})
        streams_config = jetstream_config.get('streams', {})
        
        streams_consistent = True
        for stream_name, expected_config in self.expected_streams.items():
            if stream_name in streams_config:
                actual_config = streams_config[stream_name]
                
                print(f"\n--- {stream_name} 流配置 ---")
                
                # 检查subjects
                expected_subjects = set(expected_config['subjects'])
                actual_subjects = set(actual_config.get('subjects', []))
                
                if expected_subjects == actual_subjects:
                    print(f"✅ subjects: {sorted(actual_subjects)}")
                else:
                    print(f"❌ subjects: 期望 {sorted(expected_subjects)}, 实际 {sorted(actual_subjects)}")
                    streams_consistent = False
                
                # 检查其他配置
                for key in ['max_msgs', 'max_bytes', 'max_age']:
                    expected_value = expected_config[key]
                    actual_value = actual_config.get(key)
                    
                    if actual_value == expected_value:
                        print(f"✅ {key}: {actual_value}")
                    else:
                        print(f"❌ {key}: 期望 {expected_value}, 实际 {actual_value}")
                        streams_consistent = False
            else:
                print(f"❌ 缺少流配置: {stream_name}")
                streams_consistent = False
        
        if streams_consistent:
            print("\n✅ Collector流配置一致")
        else:
            print("\n❌ Collector流配置不一致")
        
        return config

    async def check_runtime_config(self):
        """检查运行时配置"""
        print("\n=== 检查运行时配置 ===")
        
        try:
            nc = await nats.connect(self.nats_url)
            jsm = nc.jsm()
            
            # 检查流配置
            for stream_name, expected_config in self.expected_streams.items():
                try:
                    stream_info = await jsm.stream_info(stream_name)
                    actual_config = stream_info.config
                    
                    print(f"\n--- {stream_name} 运行时配置 ---")
                    
                    # 检查subjects
                    expected_subjects = set(expected_config['subjects'])
                    actual_subjects = set(actual_config.subjects)
                    
                    if expected_subjects == actual_subjects:
                        print(f"✅ subjects: {sorted(actual_subjects)}")
                    else:
                        print(f"❌ subjects: 期望 {sorted(expected_subjects)}, 实际 {sorted(actual_subjects)}")
                    
                    # 检查其他配置
                    config_checks = [
                        ('max_msgs', actual_config.max_msgs, expected_config['max_msgs']),
                        ('max_bytes', actual_config.max_bytes, expected_config['max_bytes']),
                        ('max_age', actual_config.max_age, expected_config['max_age'])
                    ]
                    
                    for key, actual_value, expected_value in config_checks:
                        if actual_value == expected_value:
                            print(f"✅ {key}: {actual_value}")
                        else:
                            print(f"❌ {key}: 期望 {expected_value}, 实际 {actual_value}")
                    
                except Exception as e:
                    print(f"❌ 获取 {stream_name} 流信息失败: {e}")
            
            # 检查消费者配置
            consumers_to_check = [
                ("MARKET_DATA", "simple_hot_storage_realtime_trade"),
                ("ORDERBOOK_SNAP", "simple_hot_storage_realtime_orderbook"),
                ("MARKET_DATA", "simple_hot_storage_realtime_liquidation")
            ]
            
            print("\n--- 消费者配置检查 ---")
            for stream_name, consumer_name in consumers_to_check:
                try:
                    info = await jsm.consumer_info(stream_name, consumer_name)
                    config = info.config
                    
                    print(f"\n{consumer_name}:")
                    
                    # 兼容不同返回类型（枚举/字符串）
                    def _to_name_lower(v):
                        try:
                            return v.name.lower()
                        except Exception:
                            return str(v).lower()

                    checks = [
                        ('deliver_policy', _to_name_lower(config.deliver_policy), 'last'),
                        ('ack_policy', _to_name_lower(config.ack_policy), 'explicit'),
                        ('ack_wait', int(float(getattr(config, 'ack_wait', 60))), 60),
                        ('max_deliver', int(getattr(config, 'max_deliver', 3)), 3),
                        ('max_ack_pending', int(getattr(config, 'max_ack_pending', 2000)), 2000)
                    ]

                    consumer_consistent = True
                    for key, actual_value, expected_value in checks:
                        if actual_value == expected_value:
                            print(f"  ✅ {key}: {actual_value}")
                        else:
                            print(f"  ❌ {key}: 期望 {expected_value}, 实际 {actual_value}")
                            consumer_consistent = False
                    
                    if consumer_consistent:
                        print(f"  ✅ {consumer_name} 配置一致")
                    else:
                        print(f"  ❌ {consumer_name} 配置不一致")
                        
                except Exception as e:
                    print(f"❌ 获取消费者 {consumer_name} 信息失败: {e}")
            
            await nc.close()
            
        except Exception as e:
            print(f"❌ NATS连接失败: {e}")

    async def run_check(self):
        """运行完整检查"""
        print("🔍 MarketPrism 配置一致性检查")
        print("=" * 50)
        
        # 检查配置文件
        env_config = self.check_env_docker_config()
        collector_config = self.check_collector_config()
        
        # 检查运行时配置
        await self.check_runtime_config()
        
        print("\n" + "=" * 50)
        print("✅ 配置一致性检查完成")
        
        # 总结建议
        print("\n📋 配置一致性要求:")
        print("1. 所有LSR参数必须在.env.docker中定义")
        print("2. Collector配置必须与.env.docker保持一致")
        print("3. 运行时JetStream配置必须与配置文件匹配")
        print("4. 所有消费者必须使用相同的LSR配置")


async def main():
    """主函数"""
    checker = ConfigConsistencyChecker()
    await checker.run_check()


if __name__ == "__main__":
    asyncio.run(main())
