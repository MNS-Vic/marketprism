#!/usr/bin/env python3
"""
MarketPrism Gap监控器
专门监控和分析序列gap情况
"""

import asyncio
import sys
import os
from pathlib import Path
from datetime import datetime, timezone
import logging
import time
from collections import defaultdict, deque
import statistics

# 添加项目根目录到Python路径
project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root))

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

class GapMonitor:
    """Gap监控器"""
    
    def __init__(self):
        self.gap_stats = defaultdict(lambda: {
            'total_gaps': 0,
            'small_gaps': 0,      # ≤100
            'medium_gaps': 0,     # 101-1000
            'large_gaps': 0,      # 1001-10000
            'huge_gaps': 0,       # >10000
            'gap_history': deque(maxlen=100),
            'last_update_id': None,
            'reconnections': 0
        })
        
        self.start_time = None
        self.is_running = False
        
    async def start_monitoring(self, duration_seconds=180):
        """启动gap监控"""
        try:
            logger.info(f"🔍 开始Gap监控，持续时间: {duration_seconds}秒")
            
            # 导入必要模块
            from services.data_collector.collector.orderbook_manager import OrderBookManager
            from core.messaging.nats_publisher import NATSPublisher
            import yaml
            
            # 加载配置
            config_path = project_root / "config" / "collector" / "unified_data_collection.yaml"
            with open(config_path, 'r', encoding='utf-8') as f:
                config = yaml.safe_load(f)
            
            # 初始化NATS
            nats_config = config.get('nats', {})
            nats_servers = nats_config.get('servers', ['nats://localhost:4222'])
            nats_publisher = NATSPublisher(servers=nats_servers)
            await nats_publisher.connect()
            
            # 创建监控回调函数
            def create_monitor_callback(exchange_name, market_type):
                def monitor_callback(symbol, data):
                    self._monitor_gap(exchange_name, market_type, symbol, data)
                return monitor_callback
            
            # 启动各交易所的订单簿管理器
            managers = []
            exchanges_config = config.get('exchanges', {})
            
            for exchange_name, exchange_config in exchanges_config.items():
                if not exchange_config.get('enabled', True):
                    continue
                    
                try:
                    manager = OrderBookManager(
                        exchange_name=exchange_name,
                        market_type=exchange_config.get('market_type', 'spot'),
                        symbols=exchange_config.get('symbols', ['BTC-USDT'])[:1],  # 只监控一个symbol
                        nats_publisher=nats_publisher,
                        config=exchange_config
                    )
                    
                    # 设置监控回调
                    original_callback = manager.update_callback
                    monitor_callback = create_monitor_callback(exchange_name, exchange_config.get('market_type', 'spot'))
                    
                    def combined_callback(symbol, data):
                        monitor_callback(symbol, data)
                        if original_callback:
                            return original_callback(symbol, data)
                    
                    manager.update_callback = combined_callback
                    
                    success = await manager.start()
                    if success:
                        managers.append((exchange_name, manager))
                        logger.info(f"✅ {exchange_name} Gap监控启动成功")
                    else:
                        logger.warning(f"⚠️ {exchange_name} Gap监控启动失败")
                        
                except Exception as e:
                    logger.error(f"❌ {exchange_name} Gap监控启动异常: {e}")
            
            if not managers:
                logger.error("❌ 没有成功启动的Gap监控器")
                return
            
            # 运行监控
            self.start_time = datetime.now(timezone.utc)
            self.is_running = True
            
            logger.info(f"🎯 Gap监控开始，监控 {len(managers)} 个交易所")
            
            # 定期输出统计信息
            for i in range(duration_seconds):
                await asyncio.sleep(1)
                if (i + 1) % 30 == 0:  # 每30秒输出一次
                    self._print_interim_stats(i + 1)
            
            # 停止所有管理器
            for exchange_name, manager in managers:
                try:
                    await manager.stop()
                    logger.info(f"✅ {exchange_name} Gap监控已停止")
                except Exception as e:
                    logger.error(f"停止 {exchange_name} Gap监控失败: {e}")
            
            # 断开NATS
            await nats_publisher.disconnect()
            
            # 输出最终分析报告
            self._print_final_report()
            
        except Exception as e:
            logger.error(f"❌ Gap监控失败: {e}", exc_info=True)
    
    def _monitor_gap(self, exchange_name, market_type, symbol, data):
        """监控单个更新的gap情况"""
        try:
            key = f"{exchange_name}_{market_type}_{symbol}"
            stats = self.gap_stats[key]
            
            # 提取序列ID
            current_id = None
            if 'binance' in exchange_name.lower():
                current_id = data.get('u') or data.get('final_update_id')
            elif 'okx' in exchange_name.lower():
                current_id = data.get('seqId') or data.get('seq_id')
            
            if current_id is not None and stats['last_update_id'] is not None:
                gap = abs(current_id - stats['last_update_id'])
                
                if gap > 1:  # 只记录有gap的情况
                    stats['total_gaps'] += 1
                    stats['gap_history'].append({
                        'timestamp': datetime.now(timezone.utc),
                        'gap': gap,
                        'current_id': current_id,
                        'last_id': stats['last_update_id']
                    })
                    
                    # 分类gap
                    if gap <= 100:
                        stats['small_gaps'] += 1
                        logger.debug(f"🔍 小gap: {key}, gap={gap}")
                    elif gap <= 1000:
                        stats['medium_gaps'] += 1
                        logger.info(f"⚠️ 中gap: {key}, gap={gap}")
                    elif gap <= 10000:
                        stats['large_gaps'] += 1
                        logger.warning(f"🚨 大gap: {key}, gap={gap}")
                    else:
                        stats['huge_gaps'] += 1
                        logger.error(f"💥 巨gap: {key}, gap={gap}")
            
            stats['last_update_id'] = current_id
            
        except Exception as e:
            logger.error(f"Gap监控失败: {e}", exc_info=True)
    
    def _print_interim_stats(self, elapsed_seconds):
        """输出中期统计信息"""
        logger.info(f"📊 Gap统计 ({elapsed_seconds}秒)")
        logger.info("-" * 60)
        
        for key, stats in self.gap_stats.items():
            if stats['total_gaps'] > 0:
                logger.info(f"{key}:")
                logger.info(f"  总gap数: {stats['total_gaps']}")
                logger.info(f"  小gap(≤100): {stats['small_gaps']}")
                logger.info(f"  中gap(101-1000): {stats['medium_gaps']}")
                logger.info(f"  大gap(1001-10000): {stats['large_gaps']}")
                logger.info(f"  巨gap(>10000): {stats['huge_gaps']}")
                
                # 计算平均gap
                if stats['gap_history']:
                    gaps = [item['gap'] for item in stats['gap_history']]
                    avg_gap = statistics.mean(gaps)
                    max_gap = max(gaps)
                    logger.info(f"  平均gap: {avg_gap:.1f}")
                    logger.info(f"  最大gap: {max_gap}")
    
    def _print_final_report(self):
        """输出最终Gap分析报告"""
        logger.info("🎯 Gap监控分析报告")
        logger.info("=" * 80)
        
        total_gaps = sum(stats['total_gaps'] for stats in self.gap_stats.values())
        total_small = sum(stats['small_gaps'] for stats in self.gap_stats.values())
        total_medium = sum(stats['medium_gaps'] for stats in self.gap_stats.values())
        total_large = sum(stats['large_gaps'] for stats in self.gap_stats.values())
        total_huge = sum(stats['huge_gaps'] for stats in self.gap_stats.values())
        
        if total_gaps > 0:
            logger.info(f"📈 总体Gap统计:")
            logger.info(f"  总gap数: {total_gaps}")
            logger.info(f"  小gap(≤100): {total_small} ({total_small/total_gaps*100:.1f}%)")
            logger.info(f"  中gap(101-1000): {total_medium} ({total_medium/total_gaps*100:.1f}%)")
            logger.info(f"  大gap(1001-10000): {total_large} ({total_large/total_gaps*100:.1f}%)")
            logger.info(f"  巨gap(>10000): {total_huge} ({total_huge/total_gaps*100:.1f}%)")
            logger.info("")
            
            logger.info(f"📊 各交易所详细Gap统计:")
            for key, stats in self.gap_stats.items():
                if stats['total_gaps'] > 0:
                    logger.info(f"  {key}:")
                    logger.info(f"    总gap: {stats['total_gaps']}")
                    logger.info(f"    小/中/大/巨: {stats['small_gaps']}/{stats['medium_gaps']}/{stats['large_gaps']}/{stats['huge_gaps']}")
                    
                    if stats['gap_history']:
                        gaps = [item['gap'] for item in stats['gap_history']]
                        avg_gap = statistics.mean(gaps)
                        max_gap = max(gaps)
                        min_gap = min(gaps)
                        logger.info(f"    平均/最大/最小gap: {avg_gap:.1f}/{max_gap}/{min_gap}")
        else:
            logger.info("🎉 没有检测到任何gap！序列完全连续！")

async def main():
    """主函数"""
    monitor = GapMonitor()
    
    try:
        await monitor.start_monitoring(duration_seconds=180)  # 监控3分钟
        return 0
    except KeyboardInterrupt:
        logger.info("收到键盘中断，停止监控...")
        return 0
    except Exception as e:
        logger.error(f"监控异常: {e}", exc_info=True)
        return 1

if __name__ == "__main__":
    print("🔍 MarketPrism Gap监控器")
    print("专门监控和分析序列gap情况")
    print("=" * 60)
    
    exit_code = asyncio.run(main())
    sys.exit(exit_code)
