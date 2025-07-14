#!/usr/bin/env python3
"""
MarketPrism直接启动器 - 绕过自动安装问题
避免触发任何可能导致pip install循环的代码
"""

import asyncio
import sys
import os
import signal
from pathlib import Path
from datetime import datetime, timezone
import logging

# 添加项目根目录到Python路径
project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root))

print(f"🔧 项目根目录: {project_root}")
print(f"🔧 Python路径: {sys.path[:3]}")

# 配置基础日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

class DirectLauncher:
    """直接启动器 - 避免复杂的依赖和自动安装"""
    
    def __init__(self):
        self.is_running = False
        self.start_time = None
        self.orderbook_managers = {}
        self.nats_publisher = None
        
    async def start(self):
        """启动数据收集系统"""
        try:
            logger.info("🚀 启动MarketPrism数据收集系统")
            
            # 1. 加载配置
            config_path = project_root / "config" / "collector" / "unified_data_collection.yaml"
            if not config_path.exists():
                logger.error(f"配置文件不存在: {config_path}")
                return False
                
            logger.info(f"✅ 配置文件存在: {config_path}")
            
            # 2. 导入必要模块（小心导入）
            try:
                import yaml
                with open(config_path, 'r', encoding='utf-8') as f:
                    config = yaml.safe_load(f)
                logger.info(f"✅ 配置文件解析成功，包含 {len(config)} 个配置项")
            except Exception as e:
                logger.error(f"配置文件解析失败: {e}")
                return False
            
            # 3. 初始化NATS连接
            try:
                from core.messaging.nats_publisher import NATSPublisher
                
                nats_config = config.get('nats', {})
                nats_servers = nats_config.get('servers', ['nats://localhost:4222'])
                
                self.nats_publisher = NATSPublisher(servers=nats_servers)
                await self.nats_publisher.connect()
                logger.info("✅ NATS连接成功")
            except Exception as e:
                logger.warning(f"NATS连接失败: {e}")
                # 继续运行，但没有NATS推送
            
            # 4. 启动交易所数据收集
            exchanges_config = config.get('exchanges', {})
            connected_count = 0
            
            for exchange_name, exchange_config in exchanges_config.items():
                if not exchange_config.get('enabled', True):
                    logger.info(f"跳过禁用的交易所: {exchange_name}")
                    continue
                    
                try:
                    success = await self._start_exchange(exchange_name, exchange_config)
                    if success:
                        connected_count += 1
                        logger.info(f"✅ {exchange_name} 连接成功")
                    else:
                        logger.warning(f"⚠️  {exchange_name} 连接失败")
                except Exception as e:
                    logger.error(f"❌ {exchange_name} 启动异常: {e}")
            
            if connected_count == 0:
                logger.error("❌ 没有成功连接的交易所")
                return False
            
            # 5. 更新状态
            self.is_running = True
            self.start_time = datetime.now(timezone.utc)
            
            logger.info(f"🎉 数据收集系统启动成功！连接了 {connected_count} 个交易所")
            logger.info("📊 系统正在运行，按Ctrl+C停止...")
            
            return True
            
        except Exception as e:
            logger.error(f"❌ 启动失败: {e}", exc_info=True)
            return False
    
    async def _start_exchange(self, exchange_name, exchange_config):
        """启动单个交易所的数据收集"""
        try:
            # 导入订单簿管理器
            from services.data_collector.orderbook_manager import OrderBookManager
            
            # 创建订单簿管理器
            manager = OrderBookManager(
                exchange_name=exchange_name,
                market_type=exchange_config.get('market_type', 'spot'),
                symbols=exchange_config.get('symbols', ['BTC-USDT']),
                nats_publisher=self.nats_publisher,
                config=exchange_config
            )
            
            # 启动管理器
            success = await manager.start()
            if success:
                self.orderbook_managers[exchange_name] = manager
                return True
            else:
                return False
                
        except ImportError as e:
            logger.error(f"导入模块失败: {e}")
            return False
        except Exception as e:
            logger.error(f"启动交易所失败: {e}")
            return False
    
    async def stop(self):
        """停止数据收集系统"""
        logger.info("🛑 停止数据收集系统...")
        
        # 停止所有订单簿管理器
        for exchange_name, manager in self.orderbook_managers.items():
            try:
                await manager.stop()
                logger.info(f"✅ {exchange_name} 已停止")
            except Exception as e:
                logger.error(f"停止 {exchange_name} 失败: {e}")
        
        # 断开NATS连接
        if self.nats_publisher:
            try:
                await self.nats_publisher.disconnect()
                logger.info("✅ NATS连接已断开")
            except Exception as e:
                logger.error(f"断开NATS连接失败: {e}")
        
        self.is_running = False
        logger.info("✅ 数据收集系统已停止")
    
    async def run_forever(self):
        """持续运行直到收到停止信号"""
        while self.is_running:
            await asyncio.sleep(1)

async def main():
    """主函数"""
    launcher = DirectLauncher()
    
    # 设置信号处理
    def signal_handler(signum, frame):
        logger.info(f"收到信号 {signum}，准备停止...")
        asyncio.create_task(launcher.stop())
    
    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)
    
    try:
        # 启动系统
        success = await launcher.start()
        if not success:
            logger.error("❌ 系统启动失败")
            return 1
        
        # 持续运行
        await launcher.run_forever()
        return 0
        
    except KeyboardInterrupt:
        logger.info("收到键盘中断，停止系统...")
        await launcher.stop()
        return 0
    except Exception as e:
        logger.error(f"系统运行异常: {e}", exc_info=True)
        await launcher.stop()
        return 1

if __name__ == "__main__":
    print("🎯 MarketPrism直接启动器")
    print("避免自动依赖安装问题的简化启动方式")
    print("="*60)
    
    exit_code = asyncio.run(main())
    sys.exit(exit_code)
