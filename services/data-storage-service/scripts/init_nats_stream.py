#!/usr/bin/env python3
"""
NATS JetStream Stream 初始化脚本
确保所有必要的 subjects 都被正确配置
"""

import asyncio
import yaml
import nats
from nats.js import JetStreamContext
from nats.js.api import StreamConfig, RetentionPolicy, DiscardPolicy, StorageType
from pathlib import Path
import sys


class NATSStreamInitializer:
    """NATS Stream 初始化器"""
    
    def __init__(self, config_path: str):
        """
        初始化
        
        Args:
            config_path: 配置文件路径
        """
        self.config_path = Path(config_path)
        self.config = self._load_config()
        
    def _load_config(self) -> dict:
        """加载配置文件"""
        try:
            with open(self.config_path, 'r', encoding='utf-8') as f:
                return yaml.safe_load(f)
        except Exception as e:
            print(f"❌ 加载配置文件失败: {e}")
            sys.exit(1)
    
    async def initialize_stream(self):
        """初始化 NATS Stream"""
        try:
            print("🚀 开始初始化 NATS JetStream")
            
            # 连接 NATS
            nats_config = self.config.get('nats', {})
            nats_url = nats_config.get('url', 'nats://localhost:4222')
            
            nc = await nats.connect(nats_url)
            js = nc.jetstream()
            
            print(f"✅ 连接到 NATS: {nats_url}")
            
            # 获取 stream 配置
            stream_config = nats_config.get('jetstream', {}).get('stream', {})
            stream_name = stream_config.get('name', 'MARKET_DATA')
            
            # 定义完整的 subjects 列表
            subjects = [
                # 基础数据类型
                "orderbook-data.>",
                "trade-data.>",
                "kline-data.>",
                
                # 衍生品数据类型 - 支持两种格式
                "funding-rate.>",
                "funding-rate-data.>",
                "open-interest.>", 
                "open-interest-data.>",
                "liquidation-data.>",
                
                # LSR 数据类型 - 完整支持
                "lsr-data.>",
                "lsr-top-position-data.>",
                "lsr-all-account-data.>",
                
                # 波动率指数
                "volatility_index-data.>",
            ]
            
            print(f"📝 配置 subjects ({len(subjects)} 个):")
            for i, subject in enumerate(subjects, 1):
                print(f"   {i:2d}. {subject}")
            
            # 创建或更新 stream 配置
            new_stream_config = StreamConfig(
                name=stream_name,
                subjects=subjects,
                retention=RetentionPolicy.LIMITS,
                max_consumers=stream_config.get('max_consumers', 50),
                max_msgs=stream_config.get('max_msgs', 10000000),
                max_bytes=stream_config.get('max_bytes', 5368709120),  # 5GB
                max_age=stream_config.get('max_age', 259200),  # 72小时
                discard=DiscardPolicy.OLD,
                storage=StorageType.FILE,
                num_replicas=1,
                duplicate_window=stream_config.get('duplicate_window', 300),
            )
            
            # 检查 stream 是否存在
            try:
                existing_stream = await js.stream_info(stream_name)
                print(f"📊 发现现有 stream: {stream_name}")
                print(f"   当前 subjects: {len(existing_stream.config.subjects)} 个")
                print(f"   当前消息数: {existing_stream.state.messages:,}")
                
                # 更新 stream
                updated_stream = await js.update_stream(new_stream_config)
                print(f"🔄 Stream 更新成功!")
                
                # 显示更新结果
                old_subjects = set(existing_stream.config.subjects)
                new_subjects_set = set(updated_stream.config.subjects)
                added_subjects = new_subjects_set - old_subjects
                
                if added_subjects:
                    print(f"➕ 新增 subjects:")
                    for subject in sorted(added_subjects):
                        print(f"     + {subject}")
                else:
                    print("✅ 所有 subjects 已存在")
                
            except Exception as e:
                if "stream not found" in str(e).lower():
                    # 创建新 stream
                    print(f"🆕 创建新 stream: {stream_name}")
                    created_stream = await js.add_stream(new_stream_config)
                    print(f"✅ Stream 创建成功!")
                    print(f"   Subjects: {len(created_stream.config.subjects)} 个")
                else:
                    raise e
            
            # 验证最终配置
            final_stream = await js.stream_info(stream_name)
            print(f"\n📋 最终 Stream 配置:")
            print(f"   名称: {final_stream.config.name}")
            print(f"   Subjects: {len(final_stream.config.subjects)} 个")
            print(f"   最大消息数: {final_stream.config.max_msgs:,}")
            print(f"   最大存储: {final_stream.config.max_bytes / 1024 / 1024 / 1024:.1f} GB")
            print(f"   TTL: {final_stream.config.max_age / 3600:.1f} 小时")
            print(f"   当前消息数: {final_stream.state.messages:,}")
            print(f"   当前 Consumers: {getattr(final_stream.state, 'consumers', 'N/A')}")
            
            # 关闭连接
            await nc.close()
            print("✅ NATS Stream 初始化完成")
            
        except Exception as e:
            print(f"❌ 初始化失败: {e}")
            sys.exit(1)
    
    async def cleanup_consumers(self):
        """清理所有 consumers（可选）"""
        try:
            print("🧹 开始清理 consumers")
            
            nats_config = self.config.get('nats', {})
            nats_url = nats_config.get('url', 'nats://localhost:4222')
            
            nc = await nats.connect(nats_url)
            js = nc.jetstream()
            
            stream_name = nats_config.get('jetstream', {}).get('stream', {}).get('name', 'MARKET_DATA')
            
            # 获取所有 consumers
            try:
                stream_info = await js.stream_info(stream_name)
                consumer_names = []
                
                # 这里需要实际的 API 来获取 consumer 列表
                # 暂时使用预定义的名称列表
                potential_consumers = [
                    "simple_hot_storage_orderbook",
                    "simple_hot_storage_trade",
                    "simple_hot_storage_funding_rate",
                    "simple_hot_storage_open_interest",
                    "simple_hot_storage_liquidation",
                    "simple_hot_storage_lsr",
                    "simple_hot_storage_lsr_top_position",
                    "simple_hot_storage_lsr_all_account",
                    "simple_hot_storage_volatility_index"
                ]
                
                for consumer_name in potential_consumers:
                    try:
                        await js.delete_consumer(stream_name, consumer_name)
                        print(f"✅ 删除 consumer: {consumer_name}")
                    except Exception:
                        # Consumer 不存在，忽略错误
                        pass
                
            except Exception as e:
                print(f"⚠️ 清理 consumers 时出错: {e}")
            
            await nc.close()
            print("✅ Consumers 清理完成")
            
        except Exception as e:
            print(f"❌ 清理失败: {e}")


async def main():
    """主函数"""
    import argparse
    
    parser = argparse.ArgumentParser(description='NATS JetStream 初始化工具')
    parser.add_argument('--config', '-c', 
                       default='config/production_tiered_storage_config.yaml',
                       help='配置文件路径')
    parser.add_argument('--cleanup', action='store_true',
                       help='清理现有 consumers')
    
    args = parser.parse_args()
    
    # 检查配置文件
    config_path = Path(args.config)
    if not config_path.exists():
        print(f"❌ 配置文件不存在: {config_path}")
        sys.exit(1)
    
    initializer = NATSStreamInitializer(args.config)
    
    if args.cleanup:
        await initializer.cleanup_consumers()
    
    await initializer.initialize_stream()


if __name__ == "__main__":
    asyncio.run(main())
