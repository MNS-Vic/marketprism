"""
全市场多空持仓人数比例数据管理器基类（按账户数计算）

提供统一的架构模式和接口定义，专门处理全市场按账户数计算的多空比例数据
"""

import asyncio
from abc import ABC, abstractmethod
from datetime import datetime, timezone
from typing import Dict, Any, List, Optional
import aiohttp

import structlog
from collector.data_types import Exchange, MarketType, NormalizedLSRAllAccount
from collector.normalizer import DataNormalizer
from collector.log_sampler import should_log_data_processing


class BaseLSRAllAccountManager(ABC):
    """
    全市场多空持仓人数比例数据管理器基类（按账户数计算）

    架构特点：
    1. 定期REST API调用获取数据
    2. 数据标准化和NATS发布
    3. 错误处理和重试机制
    4. 统一的日志管理
    5. 专门处理全市场按账户数计算的多空比例数据
    """
    
    def __init__(self,
                 exchange: Exchange,
                 market_type: MarketType,
                 symbols: List[str],
                 normalizer: DataNormalizer,
                 nats_publisher: Any,  # 使用Any类型避免导入问题
                 config: dict):
        """
        初始化全市场多空持仓人数比例数据管理器

        Args:
            exchange: 交易所枚举
            market_type: 市场类型枚举
            symbols: 交易对列表
            normalizer: 数据标准化器
            nats_publisher: NATS发布器
            config: 配置信息
        """
        self.exchange = exchange
        self.market_type = market_type
        self.data_type = 'lsr_all_account'  # 固定为全市场账户数比例
        self.symbols = symbols
        self.normalizer = normalizer
        self.nats_publisher = nats_publisher
        self.config = config
        
        # 设置日志器
        self.logger = structlog.get_logger(
            f"lsr_all_account_{exchange.value}_{market_type.value}"
        )
        
        # 配置参数
        self.fetch_interval = config.get('fetch_interval', 10)  # 获取间隔（秒）
        self.period = config.get('period', '5m')  # 数据周期
        self.limit = config.get('limit', 30)  # 获取数据点数量
        self.max_retries = config.get('max_retries', 3)  # 最大重试次数
        self.retry_delay = config.get('retry_delay', 5)  # 重试延迟（秒）
        self.timeout = config.get('timeout', 30)  # 请求超时（秒）
        
        # 运行状态
        self.is_running = False
        self.fetch_task = None
        
        # 统计信息
        self.stats = {
            'total_requests': 0,
            'successful_requests': 0,
            'failed_requests': 0,
            'last_fetch_time': None,
            'last_error': None,
            'nats_publish_success_count': 0,  # 新增：NATS发布成功计数
            'nats_publish_fail_count': 0     # 新增：NATS发布失败计数
        }

        # 发布成功摘要日志频率控制（每N次成功发布输出一次INFO摘要）
        self.publish_summary_interval = 10
        
        # HTTP会话
        self.session = None

    async def start(self):
        """启动管理器"""
        try:
            self.logger.info("启动lsr_all_account数据管理器",
                           data_type=self.data_type,
                           exchange=self.exchange.value,
                           market_type=self.market_type.value)

            # 创建HTTP会话
            self.session = aiohttp.ClientSession(
                timeout=aiohttp.ClientTimeout(total=self.timeout)
            )

            self.is_running = True

            # 启动数据获取任务
            self.fetch_task = asyncio.create_task(self._fetch_loop())

            self.logger.info("lsr_all_account数据管理器启动成功",
                           data_type=self.data_type,
                           exchange=self.exchange.value,
                           market_type=self.market_type.value)

            return True  # 🔧 修复：返回True表示启动成功

        except Exception as e:
            self.logger.error("启动lsr_all_account数据管理器失败", error=e)
            await self.stop()
            return False  # 🔧 修复：返回False表示启动失败

    async def stop(self):
        """停止管理器"""
        try:
            self.logger.info("停止lsr_all_account数据管理器")
            
            self.is_running = False
            
            # 取消数据获取任务
            if self.fetch_task and not self.fetch_task.done():
                self.fetch_task.cancel()
                try:
                    await self.fetch_task
                except asyncio.CancelledError:
                    pass
            
            # 关闭HTTP会话
            if self.session:
                await self.session.close()
                self.session = None
            
            self.logger.info("lsr_all_account数据管理器已停止")
            
        except Exception as e:
            self.logger.error("停止lsr_all_account数据管理器失败", error=e)

    async def _fetch_loop(self):
        """数据获取循环"""
        # 延迟启动，避免启动时的并发压力
        self.logger.info("lsr_all_account数据管理器将在10秒后开始数据获取")
        await asyncio.sleep(10)

        self.logger.info("lsr_all_account数据管理器开始数据获取")
        
        while self.is_running:
            try:
                self.logger.info("开始收集lsr_all_account数据",
                               data_type=self.data_type,
                               exchange=self.exchange,
                               symbols=self.symbols)

                # 为每个交易对获取数据
                for symbol in self.symbols:
                    if not self.is_running:
                        break

                    await self._fetch_and_process_symbol(symbol)

                    # 在处理下一个交易对前短暂等待，避免API限制
                    await asyncio.sleep(1)

                self.logger.info("lsr_all_account数据收集完成",
                               data_type=self.data_type,
                               exchange=self.exchange)

                # 等待下一次获取
                await asyncio.sleep(self.fetch_interval)
                
            except asyncio.CancelledError:
                break
            except Exception as e:
                self.logger.error("数据获取循环异常", error=e)
                self.stats['last_error'] = str(e)
                await asyncio.sleep(self.fetch_interval)

    async def _fetch_and_process_symbol(self, symbol: str):
        """获取并处理单个交易对的数据"""
        try:
            self.stats['total_requests'] += 1
            
            # 从API获取原始数据
            raw_data = await self._fetch_data_from_api(symbol)
            if not raw_data:
                self.stats['failed_requests'] += 1
                return
            
            # 标准化数据
            normalized_data = await self._normalize_data(raw_data)
            if not normalized_data:
                self.stats['failed_requests'] += 1
                return
            
            # 发布到NATS
            await self._publish_to_nats(normalized_data)
            
            self.stats['successful_requests'] += 1
            self.stats['last_fetch_time'] = datetime.now(timezone.utc)
            
        except Exception as e:
            self.logger.error("处理交易对数据失败", symbol=symbol, error=e)
            self.stats['failed_requests'] += 1
            self.stats['last_error'] = str(e)

    async def _publish_to_nats(self, normalized_data: NormalizedLSRAllAccount):
        """发布数据到NATS"""
        try:
            # 构建NATS主题（统一下划线命名）
            topic = f"lsr_all_account.{normalized_data.exchange_name}.{normalized_data.product_type.value}.{normalized_data.symbol_name}"

            # 🔍 调试：LSR数据发布开始
            self.logger.debug("🔍 LSR数据开始发布到NATS",
                            data_type=self.data_type,
                            exchange=normalized_data.exchange_name,
                            symbol=normalized_data.symbol_name,
                            topic=topic)

            # 构建数据字典（统一时间戳为UTC毫秒字符串；字段命名 market_type/symbol；增加collected_at）
            def _to_ms_str(dt):
                try:
                    if dt.tzinfo is None:
                        dt = dt.replace(tzinfo=timezone.utc)
                    else:
                        dt = dt.astimezone(timezone.utc)
                    return dt.strftime('%Y-%m-%d %H:%M:%S.%f')[:-3]
                except Exception:
                    return None
            data_dict = {
                'exchange': normalized_data.exchange_name,
                'market_type': normalized_data.product_type.value,
                'symbol': normalized_data.symbol_name,
                'instrument_id': normalized_data.instrument_id,
                'timestamp': _to_ms_str(normalized_data.timestamp),
                'collected_at': _to_ms_str(datetime.now(timezone.utc)),
                'long_short_ratio': str(normalized_data.long_short_ratio),
                'period': normalized_data.period,
                'data_source': 'api',
                'data_type': self.data_type
            }

            # 添加全市场账户数比例特定字段
            data_dict.update({
                'long_account_ratio': str(normalized_data.long_account_ratio),
                'short_account_ratio': str(normalized_data.short_account_ratio)
            })

            # 🔍 调试：准备调用NATS发布器
            self.logger.debug("🔍 准备调用NATS发布器",
                            data_type=self.data_type,
                            data_dict_keys=list(data_dict.keys()))

            # 发布到NATS
            success = await self.nats_publisher.publish_data(
                data_type=self.data_type,
                exchange=normalized_data.exchange_name,
                market_type=normalized_data.product_type.value,
                symbol=normalized_data.symbol_name,
                data=data_dict
            )

            # 🔍 调试：NATS发布结果
            if success:
                self.stats['nats_publish_success_count'] += 1
                self.logger.debug("🔍 LSR数据NATS发布成功",
                                symbol=normalized_data.symbol_name,
                                topic=topic,
                                data_type=self.data_type)

                # 📊 INFO级别摘要日志（降频输出 + 抽样控制）
                if should_log_data_processing(
                    data_type=self.data_type,
                    exchange=normalized_data.exchange_name,
                    market_type=normalized_data.product_type.value,
                    symbol=normalized_data.symbol_name,
                    is_error=False
                ) and self.stats['nats_publish_success_count'] % self.publish_summary_interval == 0:
                    self.logger.info("📡 LSR数据NATS发布摘要",
                                   data_type=self.data_type,
                                   exchange=normalized_data.exchange_name,
                                   success_count=self.stats['nats_publish_success_count'],
                                   fail_count=self.stats['nats_publish_fail_count'],
                                   success_rate=f"{(self.stats['nats_publish_success_count'] / (self.stats['nats_publish_success_count'] + self.stats['nats_publish_fail_count']) * 100):.1f}%" if (self.stats['nats_publish_success_count'] + self.stats['nats_publish_fail_count']) > 0 else "100.0%")
            else:
                self.stats['nats_publish_fail_count'] += 1
                self.logger.warning("🔍 LSR数据NATS发布失败",
                                  symbol=normalized_data.symbol_name,
                                  topic=topic,
                                  data_type=self.data_type)
                
        except Exception as e:
            self.logger.error("发布到NATS失败", error=e, symbol=normalized_data.symbol_name)

    def get_stats(self) -> Dict[str, Any]:
        """获取统计信息"""
        return self.stats.copy()

    @abstractmethod
    async def _fetch_data_from_api(self, symbol: str) -> Optional[Dict[str, Any]]:
        """从API获取数据 - 子类实现"""
        pass

    @abstractmethod
    async def _normalize_data(self, raw_data: Dict[str, Any]) -> Optional[NormalizedLSRAllAccount]:
        """标准化数据 - 子类实现"""
        pass
