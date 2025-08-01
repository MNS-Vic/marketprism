#!/usr/bin/env python3
"""
NATS JetStream 初始化脚本
用于Docker容器启动时初始化JetStream配置
"""

import asyncio
import yaml
import nats
from nats.js import JetStreamContext
from nats.js.api import StreamConfig, RetentionPolicy, DiscardPolicy, StorageType
import logging
import sys
from pathlib import Path
import time


class JetStreamInitializer:
    """JetStream 初始化器"""
    
    def __init__(self, config_path: str = "nats_config.yaml"):
        """初始化"""
        self.config_path = Path(config_path)
        self.config = self._load_config()
        self._setup_logging()
        
    def _load_config(self) -> dict:
        """加载配置文件"""
        try:
            with open(self.config_path, 'r', encoding='utf-8') as f:
                return yaml.safe_load(f)
        except Exception as e:
            print(f"❌ 加载配置文件失败: {e}")
            sys.exit(1)
    
    def _setup_logging(self):
        """设置日志"""
        logging.basicConfig(
            level=logging.INFO,
            format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
        )
        self.logger = logging.getLogger('JetStreamInitializer')
    
    async def wait_for_nats(self, max_retries: int = 30, retry_interval: int = 2):
        """等待NATS服务器启动"""
        self.logger.info("等待NATS服务器启动...")
        
        for attempt in range(max_retries):
            try:
                nc = await nats.connect("nats://localhost:4222", connect_timeout=5)
                await nc.close()
                self.logger.info("✅ NATS服务器已就绪")
                return True
            except Exception as e:
                self.logger.info(f"尝试 {attempt + 1}/{max_retries}: NATS未就绪 - {e}")
                if attempt < max_retries - 1:
                    await asyncio.sleep(retry_interval)
        
        self.logger.error("❌ NATS服务器启动超时")
        return False
    
    async def initialize_streams(self):
        """初始化所有streams"""
        try:
            self.logger.info("🚀 开始初始化JetStream")
            
            # 连接NATS
            nc = await nats.connect("nats://localhost:4222")
            js = nc.jetstream()
            
            # 获取streams配置
            streams_config = self.config.get('streams', [])
            
            for stream_config in streams_config:
                await self._create_or_update_stream(js, stream_config)
            
            await nc.close()
            self.logger.info("✅ JetStream初始化完成")
            
        except Exception as e:
            self.logger.error(f"❌ JetStream初始化失败: {e}")
            raise
    
    async def _create_or_update_stream(self, js: JetStreamContext, config: dict):
        """创建或更新stream"""
        stream_name = config['name']
        subjects = config['subjects']
        
        self.logger.info(f"📝 配置Stream: {stream_name}")
        self.logger.info(f"   Subjects: {len(subjects)} 个")
        
        # 创建stream配置
        stream_config = StreamConfig(
            name=stream_name,
            subjects=subjects,
            retention=RetentionPolicy.LIMITS,
            max_consumers=config.get('max_consumers', 50),
            max_msgs=config.get('max_msgs', 10000000),
            max_bytes=config.get('max_bytes', 10737418240),
            max_age=config.get('max_age', 259200),
            discard=DiscardPolicy.OLD,
            storage=StorageType.FILE,
            num_replicas=config.get('num_replicas', 1),
            duplicate_window=config.get('duplicate_window', 300),
        )
        
        try:
            # 检查stream是否存在
            existing_stream = await js.stream_info(stream_name)
            self.logger.info(f"📊 更新现有Stream: {stream_name}")
            
            # 更新stream
            await js.update_stream(stream_config)
            self.logger.info(f"🔄 Stream更新成功: {stream_name}")
            
        except Exception as e:
            if "stream not found" in str(e).lower():
                # 创建新stream
                self.logger.info(f"🆕 创建新Stream: {stream_name}")
                await js.add_stream(stream_config)
                self.logger.info(f"✅ Stream创建成功: {stream_name}")
            else:
                raise e
        
        # 验证最终配置
        final_stream = await js.stream_info(stream_name)
        self.logger.info(f"📋 Stream配置验证:")
        self.logger.info(f"   名称: {final_stream.config.name}")
        self.logger.info(f"   Subjects: {len(final_stream.config.subjects)} 个")
        self.logger.info(f"   最大消息数: {final_stream.config.max_msgs:,}")
        self.logger.info(f"   当前消息数: {final_stream.state.messages:,}")
    
    async def health_check(self):
        """健康检查"""
        try:
            nc = await nats.connect("nats://localhost:4222", connect_timeout=5)
            js = nc.jetstream()
            
            # 检查所有配置的streams
            streams_config = self.config.get('streams', [])
            for stream_config in streams_config:
                stream_name = stream_config['name']
                stream_info = await js.stream_info(stream_name)
                self.logger.info(f"✅ Stream健康: {stream_name} - 消息数: {stream_info.state.messages:,}")
            
            await nc.close()
            return True
            
        except Exception as e:
            self.logger.error(f"❌ 健康检查失败: {e}")
            return False


async def main():
    """主函数"""
    import argparse
    
    parser = argparse.ArgumentParser(description='JetStream初始化工具')
    parser.add_argument('--config', '-c', 
                       default='nats_config.yaml',
                       help='配置文件路径')
    parser.add_argument('--health-check', action='store_true',
                       help='执行健康检查')
    parser.add_argument('--wait', action='store_true',
                       help='等待NATS服务器启动')
    
    args = parser.parse_args()
    
    initializer = JetStreamInitializer(args.config)
    
    if args.wait:
        if not await initializer.wait_for_nats():
            sys.exit(1)
    
    if args.health_check:
        if await initializer.health_check():
            print("✅ JetStream健康检查通过")
        else:
            print("❌ JetStream健康检查失败")
            sys.exit(1)
    else:
        await initializer.initialize_streams()


if __name__ == "__main__":
    asyncio.run(main())
