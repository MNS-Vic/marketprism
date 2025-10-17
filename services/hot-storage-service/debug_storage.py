#!/usr/bin/env python3
"""
调试版本热存储服务 - 找出数据格式问题
"""

import asyncio
import json
import logging
import nats

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class DebugStorageService:
    def __init__(self):
        self.nc = None
        self.message_count = 0
        
    async def connect_nats(self):
        try:
            self.nc = await nats.connect("nats://localhost:4222")
            logger.info("✅ 连接到NATS成功")
            return True
        except Exception as e:
            logger.error(f"❌ 连接NATS失败: {e}")
            return False
    
    async def message_handler(self, msg):
        try:
            self.message_count += 1
            data = json.loads(msg.data.decode())
            subject = msg.subject

            # 对波动率指数主题，始终记录（其为低频关键指标）
            if subject.startswith('volatility_index.'):
                logger.info(f"📈 波动率指数消息 | 主题: {subject} | 关键字段:"
                            f" exchange={data.get('exchange')} market_type={data.get('market_type')}"
                            f" symbol={data.get('symbol')} vol_index={data.get('vol_index') or data.get('volatility_index')}"
                            f" timestamp={data.get('timestamp')}")

            # 只记录前几条消息的详细信息
            if self.message_count <= 5:
                logger.info(f"📨 消息 #{self.message_count}")
                logger.info(f"   主题: {subject}")
                logger.info(f"   数据字段: {list(data.keys())}")
                logger.info(f"   数据内容: {json.dumps(data, indent=2)[:500]}...")
                logger.info("---")
            elif self.message_count % 100 == 0:
                logger.info(f"📊 已处理 {self.message_count} 条消息")

        except Exception as e:
            logger.error(f"❌ 消息处理失败: {e}")
    
    async def start(self):
        logger.info("🚀 启动调试存储服务...")
        
        if not await self.connect_nats():
            return False
            
        # 订阅所有数据流（无 -data 后缀，统一命名）
        subjects = [
            "orderbook.>",
            "trade.>",
            "funding_rate.>",
            "open_interest.>",
            "liquidation.>",
            "lsr_top_position.>",
            "lsr_all_account.>",
            "volatility_index.>"
        ]

        for subject in subjects:
            await self.nc.subscribe(subject, cb=self.message_handler)
            logger.info(f"✅ 订阅成功: {subject}")
        
        logger.info("✅ 调试存储服务启动成功，开始监听消息...")
        
        try:
            while True:
                await asyncio.sleep(1)
        except KeyboardInterrupt:
            logger.info("收到停止信号")
        finally:
            if self.nc:
                await self.nc.close()

async def main():
    service = DebugStorageService()
    await service.start()

if __name__ == "__main__":
    asyncio.run(main())
