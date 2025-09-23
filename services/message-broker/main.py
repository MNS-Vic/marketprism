"""
Message Broker Service - Phase 3
消息代理服务，作为NATS客户端进行流管理和消息路由

这是MarketPrism微服务架构的消息中枢，提供：
1. JetStream持久化消息流
2. 消息路由和分发
3. 消息持久化存储
4. 消息订阅管理
5. 集群健康监控
6. 消息统计和分析
"""

import asyncio
import sys
import json
import subprocess
import signal
import os
from pathlib import Path
from typing import Dict, Any, List, Optional, Callable
import structlog
from datetime import datetime, timedelta, timezone
import aiohttp
from aiohttp import web
import tempfile
import yaml
import logging
import nats
from nats.aio.client import Client as NATSClient
from nats.aio.errors import ErrConnectionClosed, ErrTimeout, ErrNoServers
import traceback

# 尝试导入NATS客户端
try:
    import nats
    from nats.js import JetStreamContext
    NATS_AVAILABLE = True
except ImportError:
    print("警告: NATS客户端库未安装，某些功能可能不可用")
    NATS_AVAILABLE = False

# 添加项目路径 - 在Docker容器中调整路径
try:
    # 在Docker容器中，当前目录就是/app
    project_root = Path(__file__).resolve().parent
    sys.path.insert(0, str(project_root))
    sys.path.insert(0, '/app')
except Exception as e:
    print(f"路径配置警告: {e}")
    sys.path.insert(0, '/app')

# 导入微服务框架
from core.service_framework import BaseService




class NATSStreamManager:
    """NATS Stream管理器"""

    def __init__(self, config: Dict[str, Any]):
        self.config = config
        self.logger = structlog.get_logger(__name__)
        self.nc = None
        self.js = None

        # 流配置
        self.streams_config = config.get('streams', {})
        self.nats_url = config.get('nats_url', 'nats://localhost:4222')
        self.server_url = self.nats_url  # 对齐用于状态展示

        # 默认流配置 - 与 collector 配置对齐
        self.default_streams = {
            'MARKET_DATA': {
                'subjects': [
                    'orderbook.>',
                    'trade.>',
                    'funding_rate.>',
                    'open_interest.>',
                    'liquidation.>',
                    'volatility_index.>',
                    'lsr_top_position.>',
                    'lsr_all_account.>'
                ],
                'retention': 'limits',
                'max_age': 172800,  # 48小时（与 collector 一致）
                'max_msgs': 5000000,  # 500万条消息（与 collector 一致）
                'max_bytes': 2147483648,  # 2GB（与 collector 一致）
                'storage': 'file',
                'discard': 'old',
                'replicas': 1
            },
            'SYSTEM_EVENTS': {
                'subjects': ['system.>'],
                'retention': 'limits',
                'max_age': 86400,  # 24小时
                'max_msgs': 100000,
                'storage': 'file'
            },
            'SERVICE_LOGS': {
                'subjects': ['service.>'],
                'retention': 'limits',
                'max_age': 604800,  # 7天
                'max_msgs': 500000,
                'storage': 'file'
            }
        }

    async def connect(self) -> bool:
        """连接到NATS服务器"""
        if not NATS_AVAILABLE:
            self.logger.error("NATS客户端库不可用")
            return False

        try:
            self.nc = await nats.connect(self.nats_url)
            self.js = self.nc.jetstream()

            self.logger.info("已连接到NATS服务器")
            return True

        except Exception as e:
            self.logger.error(f"连接NATS服务器失败: {e}")
            return False

    async def disconnect(self):
        """断开NATS连接"""
        try:
            if self.nc:
                await self.nc.close()
                self.nc = None
                self.js = None
                self.logger.info("已断开NATS连接")
        except Exception as e:
            self.logger.error(f"断开NATS连接失败: {e}")

    async def create_streams(self) -> bool:
        """创建/对齐JetStream流（严格模式：以配置为准，移除不在配置内的subjects）"""
        if not self.js:
            self.logger.error("JetStream未初始化")
            return False

        try:
            strict = bool(self.config.get('strict_subjects', True))
            # 合并默认流和配置的流
            all_streams = {**self.default_streams, **self.streams_config}
            from nats.js.api import StreamConfig, RetentionPolicy, StorageType, DiscardPolicy

            for stream_name, stream_config in all_streams.items():
                desired_subjects = sorted(set(stream_config.get('subjects', [])))
                try:
                    # 尝试获取现有流
                    try:
                        existing = await self.js.stream_info(stream_name)
                        existing_subjects = sorted(set(getattr(existing.config, 'subjects', []) or []))

                        # 严格模式：仅保留配置内subjects，移除多余（如 *-data.>）
                        if strict:
                            if set(existing_subjects) != set(desired_subjects):
                                update_cfg = StreamConfig(
                                    name=stream_name,
                                    subjects=desired_subjects,
                                    retention=RetentionPolicy.LIMITS if stream_config.get('retention', 'limits')=='limits' else RetentionPolicy.INTEREST,
                                    max_msgs=stream_config.get('max_msgs', 5000000),
                                    max_bytes=stream_config.get('max_bytes', 2147483648),
                                    max_age=stream_config.get('max_age', 172800),
                                    max_consumers=stream_config.get('max_consumers', 50),
                                    num_replicas=stream_config.get('replicas', 1),
                                    storage=StorageType.FILE if stream_config.get('storage', 'file')=='file' else StorageType.MEMORY,
                                    discard=DiscardPolicy.OLD,
                                )
                                await self.js.update_stream(update_cfg)
                                self.logger.info("严格对齐流subjects已完成", stream=stream_name)
                            else:
                                self.logger.info(f"流 {stream_name} 已存在且subjects完全匹配")
                        else:
                            # 兼容模式：只追加缺失subjects
                            if not set(desired_subjects).issubset(existing_subjects):
                                merged_subjects = sorted(set(existing_subjects).union(desired_subjects))
                                update_cfg = StreamConfig(
                                    name=stream_name,
                                    subjects=merged_subjects,
                                    retention=RetentionPolicy.LIMITS,
                                    max_msgs=stream_config.get('max_msgs', 5000000),
                                    max_bytes=stream_config.get('max_bytes', 2147483648),
                                    max_age=stream_config.get('max_age', 172800),
                                    max_consumers=stream_config.get('max_consumers', 50),
                                    num_replicas=stream_config.get('replicas', 1),
                                    storage=StorageType.FILE if stream_config.get('storage', 'file')=='file' else StorageType.MEMORY,
                                    discard=DiscardPolicy.OLD,
                                )
                                await self.js.update_stream(update_cfg)
                                self.logger.info("已追加缺失subjects", stream=stream_name)
                            else:
                                self.logger.info(f"流 {stream_name} 已存在且主题已满足")
                        continue
                    except Exception:
                        pass

                    # 流不存在，新建
                    retention = RetentionPolicy.LIMITS if stream_config.get('retention', 'limits')=='limits' else RetentionPolicy.INTEREST
                    storage = StorageType.FILE if stream_config.get('storage', 'file')=='file' else StorageType.MEMORY
                    config = StreamConfig(
                        name=stream_name,
                        subjects=desired_subjects,
                        retention=retention,
                        max_age=stream_config.get('max_age', 172800),
                        max_msgs=stream_config.get('max_msgs', 5000000),
                        max_bytes=stream_config.get('max_bytes', 2147483648),
                        storage=storage,
                        discard=DiscardPolicy.OLD,
                        num_replicas=stream_config.get('replicas', 1),
                        max_consumers=stream_config.get('max_consumers', 50),
                    )
                    await self.js.add_stream(config)
                    self.logger.info(f"创建流 {stream_name} 成功")

                except Exception as e:
                    self.logger.error(f"创建/更新流 {stream_name} 失败: {e}")

            return True

        except Exception as e:
            self.logger.error(f"创建流失败: {e}")
            return False

    async def get_streams_info(self) -> List[Dict[str, Any]]:
        """获取流信息"""
        if not self.js:
            return []

        try:
            # nats-py: streams_info 返回协程，需 await；也可使用 streams_info_iterator 获取迭代器
            streams = []
            try:
                infos = await self.js.streams_info()
            except TypeError:
                # 兼容旧版本：如果 self.js 没有该方法，尝试从管理器获取
                jsm = getattr(self.js, '_jsm', None)
                if jsm is not None and hasattr(jsm, 'streams_info'):
                    infos = await jsm.streams_info()
                else:
                    raise
            for stream_info in infos:
                streams.append({
                    'name': getattr(stream_info.config, 'name', getattr(stream_info, 'name', None)),
                    'subjects': getattr(stream_info.config, 'subjects', []),
                    'messages': getattr(stream_info.state, 'messages', 0),
                    'bytes': getattr(stream_info.state, 'bytes', 0),
                    'first_seq': getattr(stream_info.state, 'first_seq', 0),
                    'last_seq': getattr(stream_info.state, 'last_seq', 0),
                    'consumer_count': getattr(stream_info.state, 'consumer_count', 0)
                })
            return streams
        except Exception as e:
            self.logger.error(f"获取流信息失败: {e}")
            return []

    async def publish_message(self, subject: str, message: Any) -> bool:
        """发布消息"""
        if not self.js:
            return False

        try:
            if isinstance(message, dict):
                message = json.dumps(message).encode()
            elif isinstance(message, str):
                message = message.encode()

            await self.js.publish(subject, message)
            return True

        except Exception as e:
            self.logger.error(f"发布消息失败: {e}")
            return False

    def get_client_status(self) -> Dict[str, Any]:
        """获取客户端状态"""
        return {
            'connected': self.nc is not None and self.nc.is_connected if self.nc else False,
            'jetstream_enabled': self.js is not None,
            'server_url': getattr(self, 'server_url', 'nats://localhost:4222'),
            'connection_time': datetime.now(timezone.utc).isoformat() if self.nc and self.nc.is_connected else None
        }


class MessageBrokerService(BaseService):
    """
    消息代理服务

    提供NATS消息代理功能：
    - 仅作为NATS客户端进行JetStream流管理与消息路由
    - 消息发布和订阅
    - 消息持久化存储
    - 消息统计和监控
    """

    def __init__(self, config: Dict[str, Any]):
        super().__init__("message-broker", config)


        self.stream_manager = NATSStreamManager(config.get('nats_client', {}))
        # 打印最终使用的 NATS URL（非敏感信息）
        try:
            nurl = getattr(self.stream_manager, 'nats_url', 'nats://localhost:4222')
            self.logger.info("NATS客户端配置", nats_url=nurl)
        except Exception:
            pass

        self.is_running = False
        self.nc: Optional[NATSClient] = None

        # Collector 心跳聚合（health.collector.*）
        self.collector_heartbeats: Dict[str, Dict[str, Any]] = {}
        self._hb_sub = None

    async def on_startup(self):
        """服务启动时的钩子"""
        await self.initialize_service()
        await self.start_service()

    async def on_shutdown(self):
        """服务关闭时的钩子"""
        await self.stop_service()

    def setup_routes(self):
        """设置API路由"""
        # 标准化API端点
        self.app.router.add_get("/api/v1/status", self._get_service_status)

        # Message Broker特有的API端点
        self.app.router.add_get("/api/v1/broker/status", self._get_broker_status)
        self.app.router.add_post("/api/v1/broker/streams", self._create_stream)
        self.app.router.add_get("/api/v1/broker/streams", self._list_streams)
        self.app.router.add_delete("/api/v1/broker/streams/{stream_name}", self._delete_stream)
        self.app.router.add_post("/api/v1/broker/publish", self._publish_message)
        self.app.router.add_get("/api/v1/broker/health", self._get_broker_health)

        # 兼容性路由（保持向后兼容）
        self.app.router.add_get("/api/v1/streams", self._list_streams)
        self.app.router.add_post("/api/v1/publish", self._publish_message)

    def _create_success_response(self, data: Any, message: str = "Success") -> web.Response:
        """
        创建标准化成功响应

        Args:
            data: 响应数据
            message: 成功消息

        Returns:
            标准化的成功响应
        """
        return web.json_response({
            "status": "success",
            "message": message,
            "data": data,
            "timestamp": datetime.now(timezone.utc).isoformat()
        })

    def _create_error_response(self, message: str, error_code: str = "INTERNAL_ERROR",
                              status_code: int = 500) -> web.Response:
        """
        创建标准化错误响应

        Args:
            message: 错误描述信息
            error_code: 标准化错误代码
            status_code: HTTP状态码

        Returns:
            标准化的错误响应
        """
        return web.json_response({
            "status": "error",
            "error_code": error_code,
            "message": message,
            "data": None,
            "timestamp": datetime.now(timezone.utc).isoformat()
        }, status=status_code)

    # 标准化错误代码常量
    ERROR_CODES = {
        'NATS_CONNECTION_ERROR': 'NATS_CONNECTION_ERROR',
        'NATS_SERVER_ERROR': 'NATS_SERVER_ERROR',
        'STREAM_NOT_FOUND': 'STREAM_NOT_FOUND',
        'STREAM_CREATION_ERROR': 'STREAM_CREATION_ERROR',
        'MESSAGE_PUBLISH_ERROR': 'MESSAGE_PUBLISH_ERROR',
        'INVALID_STREAM_DATA': 'INVALID_STREAM_DATA',
        'INVALID_MESSAGE_DATA': 'INVALID_MESSAGE_DATA',
        'JETSTREAM_ERROR': 'JETSTREAM_ERROR',
        'INVALID_PARAMETERS': 'INVALID_PARAMETERS',
        'SERVICE_UNAVAILABLE': 'SERVICE_UNAVAILABLE',
        'INTERNAL_ERROR': 'INTERNAL_ERROR'
    }

    async def initialize_service(self) -> bool:
        """初始化消息代理服务（仅作为外部 NATS 的客户端）"""
        try:
            self.logger.info("连接外部NATS...")
            success = await self.stream_manager.connect()
            if not success:
                self.logger.error("NATS客户端未能连接")
                self.logger.warning("将以降级模式运行，不支持NATS功能")
            else:
                self.logger.info("创建JetStream流...")
                await self.stream_manager.create_streams()
                self.logger.info("NATS功能初始化完成")

            self.logger.info("Message Broker Service 初始化完成")
            return True
        except Exception as e:
            self.logger.error(f"Message Broker Service 初始化异常: {e}")
            # 即使出现异常，也尝试启动基本服务
            self.logger.warning("初始化异常，将以基本模式运行")
            return True

    async def start_service(self) -> bool:
        """启动服务"""
        self.logger.info("Message Broker Service 已启动")
        self.is_running = True

        # 订阅 Collector 心跳
        try:
            if self.stream_manager and self.stream_manager.nc:
                async def _hb_handler(msg):
                    try:
                        data = json.loads(msg.data.decode('utf-8')) if msg.data else {}
                        # instance 来自 subject 尾部，或 payload.instance
                        parts = msg.subject.split('.')
                        instance = data.get('instance') or (parts[-1] if parts else 'unknown')
                        data['last_receive_ts'] = int(datetime.now(timezone.utc).timestamp())
                        self.collector_heartbeats[instance] = data
                    except Exception as e:
                        self.logger.warning("解析collector心跳失败", error=str(e))
                self._hb_sub = await self.stream_manager.nc.subscribe('health.collector.>', cb=_hb_handler)
                self.logger.info("已订阅Collector心跳", subject='health.collector.>')
            else:
                self.logger.warning("NATS未连接，无法订阅Collector心跳")
        except Exception as e:
            self.logger.error("订阅Collector心跳失败", error=str(e))

        return True

    async def stop_service(self) -> bool:
        """停止服务"""
        self.logger.info("停止消息代理服务...")
        try:
            if self._hb_sub is not None:
                try:
                    await self._hb_sub.unsubscribe()
                except Exception:
                    pass
                self._hb_sub = None
        finally:
            await self.stream_manager.disconnect()

        self.logger.info("消息代理服务关闭")
        self.is_running = False
        return True

    async def get_broker_status(self) -> Dict[str, Any]:
        """获取服务状态"""

        client_status = self.stream_manager.get_client_status()

        # 获取JetStream流信息
        streams_info = await self.stream_manager.get_streams_info()

        status = {
            'service': self.service_name,
            'service_name': self.service_name,  # 保持向后兼容
            'is_running': self.is_running,

            'nats_client': client_status,
            'jetstream_streams': streams_info,
            'message_stats': {
                'published': 0,  # 这里可以添加实际的统计
                'consumed': 0,
                'errors': 0
            }
        }
        return status

    async def _get_service_status(self, request: web.Request) -> web.Response:
        """获取服务状态 - 标准化API端点"""
        try:
            # 获取基础服务信息
            uptime_seconds = None
            try:
                uptime_seconds = (datetime.now(timezone.utc) - self.start_time).total_seconds()  # 兼容BaseService未设置start_time的情况
            except Exception:
                pass

            # 获取NATS相关状态

            client_status = self.stream_manager.get_client_status()
            streams_info = await self.stream_manager.get_streams_info()

            status_data = {
                "service": "message-broker",
                "status": "running" if self.is_running else "stopped",
                "uptime_seconds": round(uptime_seconds, 2) if uptime_seconds is not None else 0,
                "version": "1.0.0",
                "environment": self.config.get('environment', 'production'),
                "port": self.config.get('port', 8086),
                "features": {
                    "jetstream": True,
                    "message_routing": True,
                    "stream_management": True,
                    "message_persistence": True
                },
                "nats_info": {
                    "client_connected": client_status.get('connected', False) if client_status else False,
                    "streams_count": len(streams_info) if streams_info else 0
                },
                "statistics": {
                    "messages_published": 0,  # 可以添加实际统计
                    "messages_consumed": 0,
                    "active_streams": len(streams_info) if streams_info else 0,
                    "connection_errors": 0
                }
            }

            # Collector 心跳聚合信息 + 过期实例TTL清理
            try:
                now_ts = int(datetime.now(timezone.utc).timestamp())
                ttl_sec = int(os.getenv('COLLECTOR_TTL_SEC', '600'))  # 默认10分钟

                # TTL清理：移除长时间未上报的collector实例
                try:
                    to_delete = []
                    for inst, data in (self.collector_heartbeats or {}).items():
                        ts = int(data.get('ts', data.get('last_receive_ts', now_ts)))
                        if now_ts - ts > ttl_sec:
                            to_delete.append(inst)
                    for inst in to_delete:
                        self.collector_heartbeats.pop(inst, None)
                    if to_delete:
                        self.logger.info("已清理过期collector实例", removed=len(to_delete), ttl_sec=ttl_sec)
                except Exception:
                    pass

                # 构建实例列表（保留轻度stale标记用于观测）
                instances = []
                for inst, data in (self.collector_heartbeats or {}).items():
                    ts = int(data.get('ts', data.get('last_receive_ts', now_ts)))
                    age = max(0, now_ts - ts)
                    instances.append({
                        "instance": inst,
                        "hostname": data.get('hostname'),
                        "pid": data.get('pid'),
                        "last_ts": ts,
                        "age_sec": age,
                        "uptime_sec": data.get('uptime_sec'),
                        "active_managers": data.get('active_managers'),
                        "exchanges": data.get('exchanges'),
                        "stale": age > 30
                    })
                status_data["collectors"] = {
                    "count": len(instances),
                    "instances": sorted(instances, key=lambda x: x["instance"])
                }
            except Exception:
                status_data["collectors"] = {"count": 0, "instances": []}

            return self._create_success_response(status_data, "Service status retrieved successfully")

        except Exception as e:
            self.logger.error(f"获取服务状态失败: {e}", exc_info=True)
            return self._create_error_response(
                f"Failed to retrieve service status: {str(e)}",
                self.ERROR_CODES['INTERNAL_ERROR']
            )

    async def _get_broker_status(self, request: web.Request) -> web.Response:
        """获取详细的broker状态信息"""
        try:
            # 获取详细的broker状态

            client_status = self.stream_manager.get_client_status()
            streams_info = await self.stream_manager.get_streams_info()

            broker_data = {
                "service_name": "message-broker",
                "is_running": self.is_running,

                "nats_client": client_status,
                "jetstream_streams": streams_info,
                "message_stats": {
                    "published": 0,
                    "consumed": 0,
                    "errors": 0
                },
                "uptime_seconds": (datetime.now(timezone.utc) - getattr(self, 'start_time', datetime.now(timezone.utc))).total_seconds()
            }

            return self._create_success_response(broker_data, "Broker status retrieved successfully")

        except Exception as e:
            self.logger.error(f"获取broker状态失败: {e}", exc_info=True)
            return self._create_error_response(
                f"Failed to retrieve broker status: {str(e)}",
                self.ERROR_CODES['JETSTREAM_ERROR']
            )

    async def _get_broker_health(self, request: web.Request) -> web.Response:
        """获取broker健康状态"""
        try:
            client_status = self.stream_manager.get_client_status()
            client_healthy = client_status and client_status.get('connected', False)

            health_data = {
                "healthy": bool(client_healthy),
                "components": {
                    "nats_client": {
                        "healthy": bool(client_healthy),
                        "connected": client_status.get('connected', False) if client_status else False
                    }
                },
                "last_check": datetime.now(timezone.utc).isoformat()
            }

            return self._create_success_response(health_data, "Broker health retrieved successfully")

        except Exception as e:
            self.logger.error(f"获取broker健康状态失败: {e}", exc_info=True)
            return self._create_error_response(
                f"Failed to retrieve broker health: {str(e)}",
                self.ERROR_CODES['NATS_CONNECTION_ERROR']
            )

    async def _create_stream(self, request: web.Request) -> web.Response:
        """创建JetStream流"""
        try:
            # 解析请求数据
            data = await request.json()

            # 验证必需字段
            stream_name = data.get("name")
            subjects = data.get("subjects")

            if not stream_name:
                return self._create_error_response(
                    "Stream name is required",
                    self.ERROR_CODES['INVALID_STREAM_DATA'],
                    400
                )

            if not subjects or not isinstance(subjects, list):
                return self._create_error_response(
                    "Subjects must be a non-empty list",
                    self.ERROR_CODES['INVALID_STREAM_DATA'],
                    400
                )

            # 检查NATS连接
            if not self.stream_manager.nc or not self.stream_manager.js:
                return self._create_error_response(
                    "NATS JetStream not available",
                    self.ERROR_CODES['JETSTREAM_ERROR'],
                    503
                )

            # 创建流
            try:
                await self.stream_manager.js.add_stream(
                    name=stream_name,
                    subjects=subjects,
                    retention=data.get("retention", "limits"),
                    max_msgs=data.get("max_msgs", 1000000),
                    max_bytes=data.get("max_bytes", 1024*1024*1024),  # 1GB
                    max_age=data.get("max_age", 24*60*60)  # 24 hours
                )

                stream_data = {
                    "name": stream_name,
                    "subjects": subjects,
                    "created_at": datetime.now(timezone.utc).isoformat(),
                    "config": {
                        "retention": data.get("retention", "limits"),
                        "max_msgs": data.get("max_msgs", 1000000),
                        "max_bytes": data.get("max_bytes", 1024*1024*1024),
                        "max_age": data.get("max_age", 24*60*60)
                    }
                }

                return self._create_success_response(stream_data, f"Stream '{stream_name}' created successfully")

            except Exception as e:
                if "stream name already in use" in str(e).lower():
                    return self._create_error_response(
                        f"Stream '{stream_name}' already exists",
                        self.ERROR_CODES['STREAM_CREATION_ERROR'],
                        409
                    )
                else:
                    raise e

        except json.JSONDecodeError:
            return self._create_error_response(
                "Invalid JSON data",
                self.ERROR_CODES['INVALID_STREAM_DATA'],
                400
            )
        except Exception as e:
            self.logger.error(f"创建流失败: {e}", exc_info=True)
            return self._create_error_response(
                f"Failed to create stream: {str(e)}",
                self.ERROR_CODES['STREAM_CREATION_ERROR']
            )

    async def _list_streams(self, request: web.Request) -> web.Response:
        """获取JetStream流列表"""
        try:
            # 检查NATS连接
            if not self.stream_manager.nc or not self.stream_manager.js:
                return self._create_error_response(
                    "NATS JetStream not available",
                    self.ERROR_CODES['JETSTREAM_ERROR'],
                    503
                )

            # 获取流信息
            streams_info = await self.stream_manager.get_streams_info()

            # 格式化流信息
            streams = []
            for stream_info in streams_info:
                stream_data = {
                    "name": stream_info.get("name", "unknown"),
                    "subjects": stream_info.get("subjects", []),
                    "messages": stream_info.get("messages", 0),
                    "bytes": stream_info.get("bytes", 0),
                    "consumers": stream_info.get("consumers", 0),
                    "created": stream_info.get("created", None),
                    "config": {
                        "retention": stream_info.get("retention", "limits"),
                        "max_msgs": stream_info.get("max_msgs", 0),
                        "max_bytes": stream_info.get("max_bytes", 0),
                        "max_age": stream_info.get("max_age", 0)
                    }
                }
                streams.append(stream_data)

            list_data = {
                "streams": streams,
                "total_count": len(streams),
                "total_messages": sum(s["messages"] for s in streams),
                "total_bytes": sum(s["bytes"] for s in streams)
            }

            return self._create_success_response(list_data, "Streams retrieved successfully")

        except Exception as e:
            self.logger.error(f"获取流列表失败: {e}", exc_info=True)
            return self._create_error_response(
                f"Failed to retrieve streams: {str(e)}",
                self.ERROR_CODES['JETSTREAM_ERROR']
            )

    async def _delete_stream(self, request: web.Request) -> web.Response:
        """删除JetStream流"""
        try:
            stream_name = request.match_info.get('stream_name')

            if not stream_name:
                return self._create_error_response(
                    "Stream name is required",
                    self.ERROR_CODES['INVALID_PARAMETERS'],
                    400
                )

            # 检查NATS连接
            if not self.stream_manager.nc or not self.stream_manager.js:
                return self._create_error_response(
                    "NATS JetStream not available",
                    self.ERROR_CODES['JETSTREAM_ERROR'],
                    503
                )

            # 检查流是否存在
            try:
                await self.stream_manager.js.stream_info(stream_name)
            except Exception:
                return self._create_error_response(
                    f"Stream '{stream_name}' not found",
                    self.ERROR_CODES['STREAM_NOT_FOUND'],
                    404
                )

            # 删除流
            await self.stream_manager.js.delete_stream(stream_name)

            delete_data = {
                "stream_name": stream_name,
                "deleted_at": datetime.now(timezone.utc).isoformat()
            }

            return self._create_success_response(delete_data, f"Stream '{stream_name}' deleted successfully")

        except Exception as e:
            self.logger.error(f"删除流失败: {e}", exc_info=True)
            return self._create_error_response(
                f"Failed to delete stream: {str(e)}",
                self.ERROR_CODES['STREAM_CREATION_ERROR']
            )

    async def _publish_message(self, request: web.Request) -> web.Response:
        """发布消息到JetStream"""
        try:
            # 解析请求数据
            data = await request.json()

            # 验证必需字段
            subject = data.get("subject")
            message = data.get("message")

            if not subject:
                return self._create_error_response(
                    "Subject is required",
                    self.ERROR_CODES['INVALID_MESSAGE_DATA'],
                    400
                )

            if message is None:
                return self._create_error_response(
                    "Message is required",
                    self.ERROR_CODES['INVALID_MESSAGE_DATA'],
                    400
                )

            # 检查NATS连接
            if not self.stream_manager.nc or not self.stream_manager.js:
                return self._create_error_response(
                    "NATS JetStream not available",
                    self.ERROR_CODES['JETSTREAM_ERROR'],
                    503
                )

            # 准备消息数据
            if isinstance(message, dict):
                message_bytes = json.dumps(message).encode()
            elif isinstance(message, str):
                message_bytes = message.encode()
            else:
                message_bytes = str(message).encode()

            # 发布消息
            ack = await self.stream_manager.js.publish(subject, message_bytes)

            publish_data = {
                "subject": subject,
                "message_id": ack.seq if ack else None,
                "stream": ack.stream if ack else None,
                "published_at": datetime.now(timezone.utc).isoformat(),
                "message_size": len(message_bytes)
            }

            return self._create_success_response(publish_data, "Message published successfully")

        except json.JSONDecodeError:
            return self._create_error_response(
                "Invalid JSON data",
                self.ERROR_CODES['INVALID_MESSAGE_DATA'],
                400
            )
        except Exception as e:
            self.logger.error(f"发布消息失败: {e}", exc_info=True)
            return self._create_error_response(
                f"Failed to publish message: {str(e)}",
                self.ERROR_CODES['MESSAGE_PUBLISH_ERROR']
            )



async def main():
    """服务主入口点"""
    try:
        # 在Docker容器中调整配置路径
        try:
            project_root = Path(__file__).resolve().parents[2]
            config_path = project_root / 'config' / 'services' / 'services.yml'
        except IndexError:
            # Docker容器中的路径
            config_path = Path('/app/config/services/services.yml')
            if not config_path.exists():
                # 使用默认配置
                config_path = None

        if config_path and config_path.exists():
            with open(config_path, 'r', encoding='utf-8') as f:
                full_config = yaml.safe_load(f) or {}
            service_config = full_config.get('services', {}).get('message-broker', {})
        else:
            # 使用环境变量配置
            service_config = {
                'port': int(os.getenv('API_PORT', '8086')),
                'nats_url': os.getenv('NATS_URL', 'nats://nats:4222'),
                'log_level': os.getenv('LOG_LEVEL', 'INFO')
            }

        service = MessageBrokerService(config=service_config)
        await service.run()

    except Exception:
        logging.basicConfig()
        logging.critical("Message Broker Service failed to start", exc_info=True)
        traceback.print_exc(file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    import argparse
    # 统一入口：支持从 YAML 指定配置，默认使用 services/message-broker/config/unified_message_broker.yaml
    parser = argparse.ArgumentParser(description="MarketPrism Message Broker Service")
    parser.add_argument("--config", "-c", type=str, default=str(Path(__file__).resolve().parent / "config" / "unified_message_broker.yaml"), help="配置文件路径 (YAML)")
    args = parser.parse_args()

    # 若提供 YAML，则覆盖 main() 内的自动探测，直接使用该 YAML
    async def _run_with_yaml(cfg_path: Path):
        try:
            if cfg_path and cfg_path.exists():
                with open(cfg_path, 'r', encoding='utf-8') as f:
                    full_config = yaml.safe_load(f) or {}
                # 与 Unified 配置兼容：顶层 service 与 nats_client/streams
                merged = {
                    **(full_config.get('service', {}) or {}),
                    'nats_client': {**(full_config.get('nats_client', {}) or {}), 'streams': full_config.get('streams', {})}
                }
                service = MessageBrokerService(config=merged)
                await service.run()
                return
        except Exception as e:
            logging.basicConfig()
            logging.critical("Failed to start Message Broker with YAML", exc_info=True)
            traceback.print_exc(file=sys.stderr)
            sys.exit(1)

    # 优先使用 CLI 指定的配置文件
    try:
        asyncio.run(_run_with_yaml(Path(args.config)))
    except SystemExit:
        raise
    except Exception:
        # 兜底：回退到原有 main() 的自动探测逻辑
        asyncio.run(main())



# 统一入口：请使用 `python services/message-broker/main.py -c services/message-broker/config/unified_message_broker.yaml` 启动