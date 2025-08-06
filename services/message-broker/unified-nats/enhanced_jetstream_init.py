#!/usr/bin/env python3
"""
MarketPrism统一NATS容器 - 增强的JetStream初始化脚本

🎯 功能说明：
- 支持所有7种数据类型的JetStream流初始化
- 与unified_data_collection.yaml完全兼容
- 环境变量驱动的配置管理
- 自动流创建和更新

📊 支持的数据类型：
- orderbook: 订单簿数据（所有交易所）
- trade: 交易数据（所有交易所）
- funding_rate: 资金费率（衍生品交易所）
- open_interest: 未平仓量（衍生品交易所）
- lsr_top_position: LSR顶级持仓（衍生品交易所）
- lsr_all_account: LSR全账户（衍生品交易所）
- volatility_index: 波动率指数（Deribit）

🔧 设计理念：
- 简化Message Broker功能到NATS容器
- 保持与Data Collector的完全兼容性
- 支持环境变量配置覆盖
- 提供详细的初始化日志
"""

import asyncio
import os
import sys
import json
import logging
from pathlib import Path
from typing import Dict, List, Any, Optional
from datetime import datetime
import argparse

# 尝试导入NATS客户端
try:
    import nats
    from nats.js import JetStreamContext
    from nats.js.api import StreamConfig, RetentionPolicy, DiscardPolicy, StorageType
    NATS_AVAILABLE = True
except ImportError:
    print("❌ NATS客户端库未安装，请安装: pip install nats-py")
    NATS_AVAILABLE = False
    sys.exit(1)

# 设置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[logging.StreamHandler(sys.stdout)]
)
logger = logging.getLogger('EnhancedJetStreamInit')


class EnhancedJetStreamInitializer:
    """
    增强的JetStream初始化器
    
    专门为MarketPrism统一NATS容器设计，支持所有数据类型的流初始化
    """
    
    def __init__(self, nats_url: str = None):
        """
        初始化JetStream初始化器
        
        Args:
            nats_url: NATS服务器连接URL，默认从环境变量获取
        """
        self.nats_url = nats_url or os.getenv('NATS_URL', 'nats://localhost:4222')
        self.nc = None
        self.js = None
        
        # 支持的数据类型主题模式（与unified_data_collection.yaml兼容）
        self.supported_subjects = [
            "orderbook-data.>",           # 订单簿数据：所有交易所
            "trade-data.>",               # 交易数据：所有交易所
            "funding-rate-data.>",        # 资金费率：衍生品交易所
            "open-interest-data.>",       # 未平仓量：衍生品交易所
            "lsr-top-position-data.>",    # LSR顶级持仓：衍生品交易所
            "lsr-all-account-data.>",     # LSR全账户：衍生品交易所
            "volatility_index-data.>",    # 波动率指数：Deribit
            "liquidation-data.>"          # 强平订单数据：衍生品交易所
        ]
        
        # 从环境变量获取配置
        self.config = self._load_config_from_env()
        
        logger.info("增强的JetStream初始化器已创建")
        logger.info(f"NATS URL: {self.nats_url}")
        logger.info(f"支持的数据类型: {len(self.supported_subjects)} 种")
    
    def _load_config_from_env(self) -> Dict[str, Any]:
        """从环境变量加载配置"""
        return {
            # 流基础配置
            'stream_name': os.getenv('STREAM_NAME', 'MARKET_DATA'),
            'retention_policy': os.getenv('RETENTION_POLICY', 'limits'),
            'discard_policy': os.getenv('DISCARD_POLICY', 'old'),
            'storage_type': os.getenv('STORAGE_TYPE', 'file'),
            
            # 流容量配置
            'max_consumers': int(os.getenv('STREAM_MAX_CONSUMERS', '50')),
            'max_msgs': int(os.getenv('STREAM_MAX_MSGS', '1000000')),
            'max_bytes': int(os.getenv('STREAM_MAX_BYTES', '1073741824')),  # 1GB
            'max_age': int(os.getenv('STREAM_MAX_AGE', '7200')),  # 2小时
            'num_replicas': int(os.getenv('STREAM_REPLICAS', '1')),
            'duplicate_window': int(os.getenv('STREAM_DUPLICATE_WINDOW', '300')),  # 5分钟
            
            # 连接配置
            'connect_timeout': int(os.getenv('NATS_CONNECT_TIMEOUT', '10')),
            'max_reconnect_attempts': int(os.getenv('NATS_MAX_RECONNECT', '10')),
        }
    
    async def connect(self) -> bool:
        """连接到NATS服务器"""
        try:
            logger.info(f"连接到NATS服务器: {self.nats_url}")
            
            self.nc = await nats.connect(
                servers=[self.nats_url],
                connect_timeout=self.config['connect_timeout'],
                max_reconnect_attempts=self.config['max_reconnect_attempts']
            )
            
            self.js = self.nc.jetstream()
            
            logger.info("✅ NATS连接成功")
            return True
            
        except Exception as e:
            logger.error(f"❌ NATS连接失败: {e}")
            return False
    
    async def disconnect(self):
        """断开NATS连接"""
        try:
            if self.nc and not self.nc.is_closed:
                await self.nc.close()
                logger.info("✅ NATS连接已关闭")
        except Exception as e:
            logger.error(f"❌ 关闭NATS连接失败: {e}")
    
    async def initialize_market_data_stream(self) -> bool:
        """
        初始化MARKET_DATA流
        
        支持所有7种数据类型，与Data Collector完全兼容
        """
        try:
            stream_name = self.config['stream_name']
            
            logger.info(f"🔄 初始化JetStream流: {stream_name}")
            logger.info(f"📊 支持的主题数量: {len(self.supported_subjects)}")
            
            # 显示支持的数据类型
            for i, subject in enumerate(self.supported_subjects, 1):
                data_type = subject.replace('-data.>', '').replace('_', ' ').title()
                logger.info(f"  {i}. {data_type}: {subject}")
            
            # 创建流配置
            stream_config = StreamConfig(
                name=stream_name,
                subjects=self.supported_subjects,
                retention=self._get_retention_policy(),
                discard=self._get_discard_policy(),
                storage=self._get_storage_type(),
                max_consumers=self.config['max_consumers'],
                max_msgs=self.config['max_msgs'],
                max_bytes=self.config['max_bytes'],
                max_age=self.config['max_age'],
                num_replicas=self.config['num_replicas'],
                duplicate_window=self.config['duplicate_window']
            )
            
            # 检查流是否已存在
            try:
                existing_stream = await self.js.stream_info(stream_name)
                logger.info(f"📊 流已存在: {stream_name}")
                logger.info(f"   消息数: {existing_stream.state.messages:,}")
                logger.info(f"   字节数: {existing_stream.state.bytes:,}")
                logger.info(f"   消费者数: {existing_stream.state.consumer_count}")
                
                # 更新流配置
                await self.js.update_stream(stream_config)
                logger.info(f"🔄 流配置已更新: {stream_name}")
                
            except Exception as e:
                if "stream not found" in str(e).lower():
                    # 创建新流
                    logger.info(f"🆕 创建新流: {stream_name}")
                    await self.js.add_stream(stream_config)
                    logger.info(f"✅ 流创建成功: {stream_name}")
                else:
                    raise e
            
            # 验证流配置
            await self._verify_stream_config(stream_name)
            
            return True
            
        except Exception as e:
            logger.error(f"❌ 初始化流失败: {e}")
            return False
    
    def _get_retention_policy(self) -> RetentionPolicy:
        """获取保留策略"""
        policy_map = {
            'limits': RetentionPolicy.LIMITS,
            'interest': RetentionPolicy.INTEREST
        }
        return policy_map.get(self.config['retention_policy'], RetentionPolicy.LIMITS)
    
    def _get_discard_policy(self) -> DiscardPolicy:
        """获取丢弃策略"""
        policy_map = {
            'old': DiscardPolicy.OLD,
            'new': DiscardPolicy.NEW
        }
        return policy_map.get(self.config['discard_policy'], DiscardPolicy.OLD)
    
    def _get_storage_type(self) -> StorageType:
        """获取存储类型"""
        type_map = {
            'file': StorageType.FILE,
            'memory': StorageType.MEMORY
        }
        return type_map.get(self.config['storage_type'], StorageType.FILE)
    
    async def _verify_stream_config(self, stream_name: str):
        """验证流配置"""
        try:
            stream_info = await self.js.stream_info(stream_name)
            config = stream_info.config
            
            logger.info(f"📋 流配置验证: {stream_name}")
            logger.info(f"   保留策略: {config.retention}")
            logger.info(f"   存储类型: {config.storage}")
            logger.info(f"   最大消息数: {config.max_msgs:,}")
            logger.info(f"   最大字节数: {config.max_bytes:,}")
            logger.info(f"   最大消费者数: {config.max_consumers}")
            logger.info(f"   消息保留时间: {config.max_age}秒")
            
            # 验证主题配置
            missing_subjects = set(self.supported_subjects) - set(config.subjects)
            if missing_subjects:
                logger.warning(f"⚠️ 缺少主题: {missing_subjects}")
            else:
                logger.info("✅ 所有数据类型主题已配置")
                
        except Exception as e:
            logger.error(f"❌ 流配置验证失败: {e}")
    
    async def health_check(self) -> bool:
        """健康检查"""
        try:
            if not self.js:
                logger.error("❌ JetStream未初始化")
                return False
            
            stream_name = self.config['stream_name']
            stream_info = await self.js.stream_info(stream_name)
            
            logger.info(f"✅ 流健康检查通过: {stream_name}")
            logger.info(f"   状态: 正常")
            logger.info(f"   消息数: {stream_info.state.messages:,}")
            logger.info(f"   消费者数: {stream_info.state.consumer_count}")
            
            return True
            
        except Exception as e:
            logger.error(f"❌ 健康检查失败: {e}")
            return False
    
    async def get_stream_stats(self) -> Dict[str, Any]:
        """获取流统计信息"""
        try:
            stream_name = self.config['stream_name']
            stream_info = await self.js.stream_info(stream_name)
            
            return {
                'stream_name': stream_name,
                'messages': stream_info.state.messages,
                'bytes': stream_info.state.bytes,
                'first_seq': stream_info.state.first_seq,
                'last_seq': stream_info.state.last_seq,
                'consumer_count': stream_info.state.consumer_count,
                'subjects': len(stream_info.config.subjects),
                'max_msgs': stream_info.config.max_msgs,
                'max_bytes': stream_info.config.max_bytes,
                'max_age': stream_info.config.max_age,
                'storage': str(stream_info.config.storage),
                'retention': str(stream_info.config.retention)
            }
            
        except Exception as e:
            logger.error(f"❌ 获取流统计失败: {e}")
            return {}


async def main():
    """主函数"""
    parser = argparse.ArgumentParser(description='MarketPrism增强JetStream初始化器')
    parser.add_argument('--nats-url', default=None, help='NATS服务器URL')
    parser.add_argument('--wait', action='store_true', help='等待NATS服务器启动')
    parser.add_argument('--health-check', action='store_true', help='执行健康检查')
    parser.add_argument('--stats', action='store_true', help='显示流统计信息')
    parser.add_argument('--timeout', type=int, default=30, help='操作超时时间（秒）')
    
    args = parser.parse_args()
    
    logger.info("🚀 启动MarketPrism增强JetStream初始化器")
    logger.info(f"⏰ 启动时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    
    # 创建初始化器
    initializer = EnhancedJetStreamInitializer(args.nats_url)
    
    try:
        # 等待NATS服务器（如果需要）
        if args.wait:
            logger.info("⏳ 等待NATS服务器启动...")
            for i in range(args.timeout):
                if await initializer.connect():
                    await initializer.disconnect()
                    break
                await asyncio.sleep(1)
            else:
                logger.error("❌ 等待NATS服务器超时")
                return 1
        
        # 连接NATS
        if not await initializer.connect():
            logger.error("❌ 无法连接到NATS服务器")
            return 1
        
        # 执行操作
        if args.health_check:
            success = await initializer.health_check()
            if not success:
                return 1
        elif args.stats:
            stats = await initializer.get_stream_stats()
            if stats:
                print(json.dumps(stats, indent=2, ensure_ascii=False))
            else:
                return 1
        else:
            # 默认：初始化流
            success = await initializer.initialize_market_data_stream()
            if not success:
                return 1
        
        logger.info("✅ 操作完成")
        return 0
        
    except KeyboardInterrupt:
        logger.info("⏹️ 操作被用户中断")
        return 1
    except Exception as e:
        logger.error(f"❌ 操作异常: {e}")
        return 1
    finally:
        await initializer.disconnect()


if __name__ == "__main__":
    exit(asyncio.run(main()))
