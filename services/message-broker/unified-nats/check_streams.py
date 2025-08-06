#!/usr/bin/env python3
"""
MarketPrism统一NATS容器 - 流状态检查脚本

🎯 功能说明：
- 检查MARKET_DATA流的详细状态
- 验证所有7种数据类型主题配置
- 提供流统计信息和健康状态
- 支持JSON格式输出

📊 检查项目：
- 流存在性和配置
- 主题配置完整性
- 消息统计和存储状态
- 消费者状态
- 数据类型支持验证

🔧 设计理念：
- 详细的流状态检查
- 与健康检查脚本集成
- 支持多种输出格式
- 提供故障诊断信息
"""

import asyncio
import os
import sys
import json
import logging
import argparse
from typing import Dict, List, Any, Optional
from datetime import datetime

# 尝试导入NATS客户端
try:
    import nats
    from nats.js import JetStreamContext
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
logger = logging.getLogger('StreamChecker')


class StreamHealthChecker:
    """
    流健康检查器
    
    专门检查MARKET_DATA流的健康状态和配置
    """
    
    def __init__(self, nats_url: str = None):
        """
        初始化流健康检查器
        
        Args:
            nats_url: NATS服务器连接URL
        """
        self.nats_url = nats_url or os.getenv('NATS_URL', 'nats://localhost:4222')
        self.nc = None
        self.js = None
        
        # 预期的数据类型主题（与Data Collector兼容）
        self.expected_subjects = [
            "orderbook-data.>",           # 订单簿数据
            "trade-data.>",               # 交易数据
            "funding-rate-data.>",        # 资金费率
            "open-interest-data.>",       # 未平仓量
            "lsr-top-position-data.>",    # LSR顶级持仓
            "lsr-all-account-data.>",     # LSR全账户
            "volatility_index-data.>",    # 波动率指数
            "liquidation-data.>"          # 强平订单数据
        ]
        
        # 数据类型映射
        self.data_type_mapping = {
            "orderbook-data.>": "订单簿数据（所有交易所）",
            "trade-data.>": "交易数据（所有交易所）",
            "funding-rate-data.>": "资金费率（衍生品交易所）",
            "open-interest-data.>": "未平仓量（衍生品交易所）",
            "lsr-top-position-data.>": "LSR顶级持仓（衍生品交易所）",
            "lsr-all-account-data.>": "LSR全账户（衍生品交易所）",
            "volatility_index-data.>": "波动率指数（Deribit）",
            "liquidation-data.>": "强平订单数据（衍生品交易所）"
        }
        
        logger.info("流健康检查器已初始化")
    
    async def connect(self, timeout: int = 10) -> bool:
        """连接到NATS服务器"""
        try:
            logger.info(f"连接到NATS服务器: {self.nats_url}")
            
            self.nc = await nats.connect(
                servers=[self.nats_url],
                connect_timeout=timeout
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
    
    async def check_stream_exists(self, stream_name: str) -> bool:
        """检查流是否存在"""
        try:
            await self.js.stream_info(stream_name)
            return True
        except Exception:
            return False
    
    async def get_stream_info(self, stream_name: str) -> Optional[Dict[str, Any]]:
        """获取流详细信息"""
        try:
            stream_info = await self.js.stream_info(stream_name)
            
            return {
                'name': stream_info.config.name,
                'subjects': list(stream_info.config.subjects),
                'retention': str(stream_info.config.retention),
                'storage': str(stream_info.config.storage),
                'max_consumers': stream_info.config.max_consumers,
                'max_msgs': stream_info.config.max_msgs,
                'max_bytes': stream_info.config.max_bytes,
                'max_age': stream_info.config.max_age,
                'num_replicas': stream_info.config.num_replicas,
                'duplicate_window': stream_info.config.duplicate_window,
                
                # 状态信息
                'messages': stream_info.state.messages,
                'bytes': stream_info.state.bytes,
                'first_seq': stream_info.state.first_seq,
                'last_seq': stream_info.state.last_seq,
                'consumer_count': stream_info.state.consumer_count,
                'first_ts': getattr(stream_info.state, 'first_ts', None),
                'last_ts': getattr(stream_info.state, 'last_ts', None),
            }
            
        except Exception as e:
            logger.error(f"❌ 获取流信息失败: {e}")
            return None
    
    async def check_subjects_configuration(self, stream_info: Dict[str, Any]) -> Dict[str, Any]:
        """检查主题配置"""
        configured_subjects = set(stream_info['subjects'])
        expected_subjects = set(self.expected_subjects)
        
        # 检查缺失和多余的主题
        missing_subjects = expected_subjects - configured_subjects
        extra_subjects = configured_subjects - expected_subjects
        
        return {
            'total_configured': len(configured_subjects),
            'total_expected': len(expected_subjects),
            'missing_subjects': list(missing_subjects),
            'extra_subjects': list(extra_subjects),
            'all_expected_present': len(missing_subjects) == 0,
            'subject_details': [
                {
                    'subject': subject,
                    'description': self.data_type_mapping.get(subject, '未知数据类型'),
                    'configured': subject in configured_subjects
                }
                for subject in self.expected_subjects
            ]
        }
    
    async def get_consumers_info(self, stream_name: str) -> List[Dict[str, Any]]:
        """获取消费者信息"""
        try:
            consumers = []
            consumer_names = await self.js.consumers_info(stream_name)
            
            for consumer_info in consumer_names:
                consumers.append({
                    'name': consumer_info.name,
                    'durable_name': consumer_info.config.durable_name,
                    'deliver_policy': str(consumer_info.config.deliver_policy),
                    'ack_policy': str(consumer_info.config.ack_policy),
                    'max_deliver': consumer_info.config.max_deliver,
                    'ack_wait': consumer_info.config.ack_wait,
                    'delivered': consumer_info.delivered.consumer_seq,
                    'ack_pending': consumer_info.ack_pending,
                    'redelivered': consumer_info.redelivered,
                    'num_waiting': consumer_info.num_waiting,
                    'num_pending': consumer_info.num_pending,
                })
            
            return consumers
            
        except Exception as e:
            logger.error(f"❌ 获取消费者信息失败: {e}")
            return []
    
    async def perform_health_check(self, stream_name: str = "MARKET_DATA") -> Dict[str, Any]:
        """执行完整的健康检查"""
        health_result = {
            'timestamp': datetime.now().isoformat(),
            'stream_name': stream_name,
            'nats_url': self.nats_url,
            'overall_health': 'unknown',
            'checks': {}
        }
        
        try:
            # 1. 检查流存在性
            stream_exists = await self.check_stream_exists(stream_name)
            health_result['checks']['stream_exists'] = {
                'status': 'pass' if stream_exists else 'fail',
                'message': f"流 {stream_name} {'存在' if stream_exists else '不存在'}"
            }
            
            if not stream_exists:
                health_result['overall_health'] = 'fail'
                health_result['checks']['stream_exists']['message'] += f"，请运行初始化脚本创建流"
                return health_result
            
            # 2. 获取流信息
            stream_info = await self.get_stream_info(stream_name)
            if not stream_info:
                health_result['overall_health'] = 'fail'
                health_result['checks']['stream_info'] = {
                    'status': 'fail',
                    'message': '无法获取流信息'
                }
                return health_result
            
            health_result['stream_info'] = stream_info
            health_result['checks']['stream_info'] = {
                'status': 'pass',
                'message': '流信息获取成功'
            }
            
            # 3. 检查主题配置
            subjects_check = await self.check_subjects_configuration(stream_info)
            health_result['subjects_check'] = subjects_check
            health_result['checks']['subjects_configuration'] = {
                'status': 'pass' if subjects_check['all_expected_present'] else 'warn',
                'message': f"配置了 {subjects_check['total_configured']} 个主题，预期 {subjects_check['total_expected']} 个"
            }
            
            if subjects_check['missing_subjects']:
                health_result['checks']['subjects_configuration']['message'] += f"，缺失: {subjects_check['missing_subjects']}"
            
            # 4. 检查消费者
            consumers = await self.get_consumers_info(stream_name)
            health_result['consumers'] = consumers
            health_result['checks']['consumers'] = {
                'status': 'pass',
                'message': f"发现 {len(consumers)} 个消费者"
            }
            
            # 5. 检查流状态
            messages_count = stream_info['messages']
            consumer_count = stream_info['consumer_count']
            
            health_result['checks']['stream_status'] = {
                'status': 'pass',
                'message': f"消息数: {messages_count:,}，消费者数: {consumer_count}"
            }
            
            # 确定总体健康状态
            failed_checks = [check for check in health_result['checks'].values() if check['status'] == 'fail']
            warn_checks = [check for check in health_result['checks'].values() if check['status'] == 'warn']
            
            if failed_checks:
                health_result['overall_health'] = 'fail'
            elif warn_checks:
                health_result['overall_health'] = 'warn'
            else:
                health_result['overall_health'] = 'pass'
            
            return health_result
            
        except Exception as e:
            health_result['overall_health'] = 'fail'
            health_result['error'] = str(e)
            logger.error(f"❌ 健康检查异常: {e}")
            return health_result
    
    def print_health_report(self, health_result: Dict[str, Any], detailed: bool = False):
        """打印健康检查报告"""
        print("\n" + "="*80)
        print("🏥 MarketPrism MARKET_DATA流健康检查报告")
        print("="*80)
        print(f"检查时间: {health_result['timestamp']}")
        print(f"流名称: {health_result['stream_name']}")
        print(f"NATS URL: {health_result['nats_url']}")
        print(f"总体状态: {self._get_status_emoji(health_result['overall_health'])} {health_result['overall_health'].upper()}")
        
        # 检查结果
        print("\n📋 检查项目:")
        for check_name, check_result in health_result.get('checks', {}).items():
            status_emoji = self._get_status_emoji(check_result['status'])
            print(f"  {status_emoji} {check_name}: {check_result['message']}")
        
        # 详细信息
        if detailed and 'stream_info' in health_result:
            stream_info = health_result['stream_info']
            print(f"\n📊 流统计信息:")
            print(f"  消息数量: {stream_info['messages']:,}")
            print(f"  存储字节: {stream_info['bytes']:,}")
            print(f"  消费者数: {stream_info['consumer_count']}")
            print(f"  存储类型: {stream_info['storage']}")
            print(f"  保留策略: {stream_info['retention']}")
            print(f"  最大消息数: {stream_info['max_msgs']:,}")
            print(f"  最大字节数: {stream_info['max_bytes']:,}")
            print(f"  消息保留时间: {stream_info['max_age']}秒")
        
        # 主题配置
        if detailed and 'subjects_check' in health_result:
            subjects_check = health_result['subjects_check']
            print(f"\n📡 数据类型支持:")
            for subject_detail in subjects_check['subject_details']:
                status = "✅" if subject_detail['configured'] else "❌"
                print(f"  {status} {subject_detail['description']}")
                print(f"      主题: {subject_detail['subject']}")
        
        # 消费者信息
        if detailed and 'consumers' in health_result:
            consumers = health_result['consumers']
            if consumers:
                print(f"\n👥 消费者信息:")
                for consumer in consumers:
                    print(f"  - {consumer['name']} (持久名: {consumer['durable_name']})")
                    print(f"    已投递: {consumer['delivered']}, 待确认: {consumer['ack_pending']}")
            else:
                print(f"\n👥 消费者信息: 无活跃消费者")
        
        print("="*80 + "\n")
    
    def _get_status_emoji(self, status: str) -> str:
        """获取状态表情符号"""
        emoji_map = {
            'pass': '✅',
            'warn': '⚠️',
            'fail': '❌',
            'unknown': '❓'
        }
        return emoji_map.get(status, '❓')


async def main():
    """主函数"""
    parser = argparse.ArgumentParser(description='MarketPrism流状态检查器')
    parser.add_argument('--nats-url', default=None, help='NATS服务器URL')
    parser.add_argument('--stream', default='MARKET_DATA', help='要检查的流名称')
    parser.add_argument('--timeout', type=int, default=10, help='连接超时时间（秒）')
    parser.add_argument('--json', action='store_true', help='输出JSON格式结果')
    parser.add_argument('--detailed', action='store_true', help='显示详细信息')
    parser.add_argument('--quiet', action='store_true', help='静默模式，只输出结果')
    
    args = parser.parse_args()
    
    if args.quiet:
        logging.getLogger().setLevel(logging.ERROR)
    
    # 创建检查器
    checker = StreamHealthChecker(args.nats_url)
    
    try:
        # 连接NATS
        if not await checker.connect(args.timeout):
            return 1
        
        # 执行健康检查
        health_result = await checker.perform_health_check(args.stream)
        
        # 输出结果
        if args.json:
            print(json.dumps(health_result, indent=2, ensure_ascii=False))
        else:
            checker.print_health_report(health_result, args.detailed)
        
        # 返回退出码
        if health_result['overall_health'] == 'pass':
            return 0
        elif health_result['overall_health'] == 'warn':
            return 0  # 警告不算失败
        else:
            return 1
        
    except KeyboardInterrupt:
        logger.info("⏹️ 操作被用户中断")
        return 1
    except Exception as e:
        logger.error(f"❌ 操作异常: {e}")
        return 1
    finally:
        await checker.disconnect()


if __name__ == "__main__":
    exit(asyncio.run(main()))
