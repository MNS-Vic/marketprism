#!/usr/bin/env python3
"""
MarketPrism序列验证分析器
专门分析订单簿序列ID验证和更新的效果
"""

import asyncio
import sys
import os
from pathlib import Path
from datetime import datetime, timezone
import logging
import time
from collections import defaultdict, deque

# 添加项目根目录到Python路径
project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root))

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

class SequenceValidationAnalyzer:
    """序列验证分析器"""
    
    def __init__(self):
        self.validation_stats = defaultdict(lambda: {
            'total_updates': 0,
            'successful_validations': 0,
            'failed_validations': 0,
            'sequence_gaps': 0,
            'checksum_failures': 0,
            'reconnections': 0,
            'last_update_id': None,
            'sequence_history': deque(maxlen=100)
        })
        
        self.start_time = None
        self.is_running = False
        
    async def start_analysis(self, duration_seconds=60):
        """启动序列验证分析"""
        try:
            logger.info(f"🔍 开始序列验证分析，持续时间: {duration_seconds}秒")
            
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
            
            # 创建分析回调函数
            def create_analysis_callback(exchange_name, market_type):
                def analysis_callback(symbol, data):
                    self._analyze_update(exchange_name, market_type, symbol, data)
                return analysis_callback
            
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
                        symbols=exchange_config.get('symbols', ['BTC-USDT'])[:1],  # 只分析一个symbol
                        nats_publisher=nats_publisher,
                        config=exchange_config
                    )
                    
                    # 设置分析回调
                    original_callback = manager.update_callback
                    analysis_callback = create_analysis_callback(exchange_name, exchange_config.get('market_type', 'spot'))
                    
                    def combined_callback(symbol, data):
                        analysis_callback(symbol, data)
                        if original_callback:
                            return original_callback(symbol, data)
                    
                    manager.update_callback = combined_callback
                    
                    success = await manager.start()
                    if success:
                        managers.append((exchange_name, manager))
                        logger.info(f"✅ {exchange_name} 分析器启动成功")
                    else:
                        logger.warning(f"⚠️ {exchange_name} 分析器启动失败")
                        
                except Exception as e:
                    logger.error(f"❌ {exchange_name} 分析器启动异常: {e}")
            
            if not managers:
                logger.error("❌ 没有成功启动的分析器")
                return
            
            # 运行分析
            self.start_time = datetime.now(timezone.utc)
            self.is_running = True
            
            logger.info(f"🎯 序列验证分析开始，监控 {len(managers)} 个交易所")
            
            # 定期输出统计信息
            for i in range(duration_seconds):
                await asyncio.sleep(1)
                if (i + 1) % 10 == 0:  # 每10秒输出一次
                    self._print_interim_stats(i + 1)
            
            # 停止所有管理器
            for exchange_name, manager in managers:
                try:
                    await manager.stop()
                    logger.info(f"✅ {exchange_name} 分析器已停止")
                except Exception as e:
                    logger.error(f"停止 {exchange_name} 分析器失败: {e}")
            
            # 断开NATS
            await nats_publisher.disconnect()
            
            # 输出最终分析报告
            self._print_final_report()
            
        except Exception as e:
            logger.error(f"❌ 序列验证分析失败: {e}", exc_info=True)
    
    def _analyze_update(self, exchange_name, market_type, symbol, data):
        """分析单个更新的序列验证情况"""
        try:
            key = f"{exchange_name}_{market_type}_{symbol}"
            stats = self.validation_stats[key]
            stats['total_updates'] += 1
            
            # 分析Binance序列验证
            if 'binance' in exchange_name.lower():
                self._analyze_binance_sequence(stats, data)
            
            # 分析OKX序列验证
            elif 'okx' in exchange_name.lower():
                self._analyze_okx_sequence(stats, data)
            
            # 记录序列历史
            current_time = datetime.now(timezone.utc)
            stats['sequence_history'].append({
                'timestamp': current_time,
                'update_id': self._extract_update_id(data),
                'data_type': self._get_data_type(data)
            })
            
        except Exception as e:
            logger.error(f"分析更新失败: {e}", exc_info=True)
    
    def _analyze_binance_sequence(self, stats, data):
        """分析Binance序列验证"""
        try:
            # 提取Binance序列ID
            first_update_id = data.get('U')
            final_update_id = data.get('u')
            prev_update_id = data.get('pu')  # 永续合约特有
            
            if final_update_id is not None:
                if stats['last_update_id'] is not None:
                    # 检查序列连续性
                    if prev_update_id is not None:
                        # 永续合约验证
                        if prev_update_id == stats['last_update_id']:
                            stats['successful_validations'] += 1
                        else:
                            stats['failed_validations'] += 1
                            stats['sequence_gaps'] += 1
                    else:
                        # 现货验证
                        expected_first = stats['last_update_id'] + 1
                        if first_update_id is not None and first_update_id <= expected_first <= final_update_id:
                            stats['successful_validations'] += 1
                        else:
                            stats['failed_validations'] += 1
                            stats['sequence_gaps'] += 1
                else:
                    # 首次更新
                    stats['successful_validations'] += 1
                
                stats['last_update_id'] = final_update_id
            
        except Exception as e:
            logger.error(f"Binance序列分析失败: {e}")
    
    def _analyze_okx_sequence(self, stats, data):
        """分析OKX序列验证"""
        try:
            # 提取OKX序列ID
            seq_id = data.get('seqId')
            prev_seq_id = data.get('prevSeqId')
            checksum = data.get('checksum')
            
            if seq_id is not None and prev_seq_id is not None:
                if stats['last_update_id'] is not None:
                    # 检查序列连续性
                    if prev_seq_id == stats['last_update_id']:
                        stats['successful_validations'] += 1
                    elif prev_seq_id == -1:
                        # 快照消息
                        stats['successful_validations'] += 1
                    else:
                        stats['failed_validations'] += 1
                        stats['sequence_gaps'] += 1
                else:
                    # 首次更新
                    stats['successful_validations'] += 1
                
                stats['last_update_id'] = seq_id
            
            # 检查checksum
            if checksum is not None:
                # 这里可以添加checksum验证逻辑
                pass
            
        except Exception as e:
            logger.error(f"OKX序列分析失败: {e}")
    
    def _extract_update_id(self, data):
        """提取更新ID"""
        return data.get('u') or data.get('seqId') or data.get('ts')
    
    def _get_data_type(self, data):
        """获取数据类型"""
        if 'e' in data and data.get('e') == 'depthUpdate':
            return 'binance_depth_update'
        elif 'seqId' in data:
            return 'okx_update'
        else:
            return 'unknown'
    
    def _print_interim_stats(self, elapsed_seconds):
        """输出中期统计信息"""
        logger.info(f"📊 序列验证统计 ({elapsed_seconds}秒)")
        logger.info("-" * 60)
        
        for key, stats in self.validation_stats.items():
            if stats['total_updates'] > 0:
                success_rate = (stats['successful_validations'] / stats['total_updates']) * 100
                logger.info(f"{key}:")
                logger.info(f"  总更新: {stats['total_updates']}")
                logger.info(f"  验证成功: {stats['successful_validations']} ({success_rate:.1f}%)")
                logger.info(f"  验证失败: {stats['failed_validations']}")
                logger.info(f"  序列跳跃: {stats['sequence_gaps']}")
    
    def _print_final_report(self):
        """输出最终分析报告"""
        logger.info("🎯 序列验证分析报告")
        logger.info("=" * 80)
        
        total_updates = sum(stats['total_updates'] for stats in self.validation_stats.values())
        total_successful = sum(stats['successful_validations'] for stats in self.validation_stats.values())
        total_failed = sum(stats['failed_validations'] for stats in self.validation_stats.values())
        total_gaps = sum(stats['sequence_gaps'] for stats in self.validation_stats.values())
        
        if total_updates > 0:
            overall_success_rate = (total_successful / total_updates) * 100
            logger.info(f"📈 总体统计:")
            logger.info(f"  总更新数: {total_updates}")
            logger.info(f"  验证成功: {total_successful} ({overall_success_rate:.2f}%)")
            logger.info(f"  验证失败: {total_failed}")
            logger.info(f"  序列跳跃: {total_gaps}")
            logger.info("")
            
            logger.info(f"📊 各交易所详细统计:")
            for key, stats in self.validation_stats.items():
                if stats['total_updates'] > 0:
                    success_rate = (stats['successful_validations'] / stats['total_updates']) * 100
                    logger.info(f"  {key}:")
                    logger.info(f"    更新数: {stats['total_updates']}")
                    logger.info(f"    成功率: {success_rate:.2f}%")
                    logger.info(f"    序列跳跃: {stats['sequence_gaps']}")
                    logger.info(f"    最后更新ID: {stats['last_update_id']}")
        else:
            logger.warning("❌ 没有收到任何更新数据")

async def main():
    """主函数"""
    analyzer = SequenceValidationAnalyzer()
    
    try:
        await analyzer.start_analysis(duration_seconds=60)
        return 0
    except KeyboardInterrupt:
        logger.info("收到键盘中断，停止分析...")
        return 0
    except Exception as e:
        logger.error(f"分析异常: {e}", exc_info=True)
        return 1

if __name__ == "__main__":
    print("🔍 MarketPrism序列验证分析器")
    print("专门分析订单簿序列ID验证和更新的效果")
    print("=" * 60)
    
    exit_code = asyncio.run(main())
    sys.exit(exit_code)
