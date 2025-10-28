"""
MarketPrism 监控告警服务 - BaseService重构版本

基于BaseService框架的监控告警服务，提供：
- 统一的API响应格式
- 标准化的错误处理机制
- 完整的服务生命周期管理
- 告警规则和指标管理功能
"""

import asyncio
import sys
import json
import os
from pathlib import Path
from typing import Dict, Any, Optional, List
from datetime import datetime, timezone
import structlog
from aiohttp import web

# 添加项目根目录、当前模块目录与 src 目录到Python路径（避免重复插入）
project_root = str(Path(__file__).parent.parent.parent)
module_dir = str(Path(__file__).parent)
src_dir = str(Path(__file__).parent / 'src')
if project_root not in sys.path:
    sys.path.insert(0, project_root)
if module_dir not in sys.path:
    sys.path.insert(0, module_dir)
if src_dir not in sys.path:
    sys.path.insert(0, src_dir)

# 导入BaseService框架
from core.service_framework import BaseService
from core.api_response import APIResponse

from core.logging_config import configure_logging, get_logger

from src.clients.alertmanager_client import fetch_alerts as am_fetch_alerts
from src.clients.prometheus_client import fetch_alert_rules as prom_fetch_rules
from src.fixtures.mock_data import get_mock_alerts, get_mock_rules, get_mock_metrics


logger = None  # will be configured at process start


class MonitoringAlertingService(BaseService):
    """
    MarketPrism 监控告警服务 - BaseService重构版本

    基于BaseService框架，提供：
    - 统一的服务生命周期管理
    - 标准化的API响应格式
    - 完整的错误处理机制
    - 告警规则和指标管理功能
    - Prometheus指标集成
    """

    def __init__(self, config: Dict[str, Any]):
        super().__init__("monitoring-alerting", config)

        # 服务状态
        self.start_time = datetime.now(timezone.utc)
        self.is_initialized = False

        # 告警相关数据
        self.alert_rules = []
        self.alerts = []
        self.component_health = {}
        self.metrics_data = {}

        # 统计信息
        self.stats = {
            'total_alerts': 0,
            'active_alerts': 0,
            'alert_rules_count': 0,
            'last_alert_time': None,
            'request_count': 0
        }

        # 行为控制与后端配置
        self.use_mock = os.getenv('USE_MOCK_DATA', 'false').lower() == 'true'
        self.prometheus_base_url = os.getenv('PROMETHEUS_BASE_URL', 'http://localhost:9090')
        self.alertmanager_base_url = os.getenv('ALERTMANAGER_BASE_URL', 'http://localhost:9093')

        logger.info("🎉 监控告警服务初始化完成")

    def setup_routes(self):
        """设置API路由"""
        # 可选中间件接入（通过环境变量开关，默认关闭）
        enable_auth = os.getenv('MARKETPRISM_ENABLE_AUTH', 'false').lower() == 'true'
        enable_validation = os.getenv('MARKETPRISM_ENABLE_VALIDATION', 'false').lower() == 'true'

        if enable_auth:
            try:
                from src.auth import create_auth_middleware
                auth_mw = create_auth_middleware()
                if auth_mw is None:
                    raise RuntimeError("create_auth_middleware() returned None")
                self.app.middlewares.append(auth_mw)
                logger.info("认证中间件已启用（MARKETPRISM_ENABLE_AUTH=true）")
            except ImportError as e:
                logger.error(f"认证中间件导入失败: {e}")
                raise
            except Exception as e:
                logger.error(f"创建认证中间件失败: {e}")
                raise

        if enable_validation:
            try:
                from src.validation import create_validation_middleware
                validation_mw = create_validation_middleware()
                if validation_mw is None:
                    raise RuntimeError("create_validation_middleware() returned None")
                self.app.middlewares.append(validation_mw)
                logger.info("验证中间件已启用（MARKETPRISM_ENABLE_VALIDATION=true）")
            except ImportError as e:
                logger.error(f"验证中间件导入失败: {e}")
                raise
            except Exception as e:
                logger.error(f"创建验证中间件失败: {e}")
                raise

        # 基础路由已在BaseService中设置，这里添加monitoring-alerting特定的API端点
        self.app.router.add_get("/api/v1/status", self._get_service_status)
        self.app.router.add_get("/api/v1/alerts", self._get_alerts)
        self.app.router.add_post("/api/v1/alerts", self._create_alert)
        self.app.router.add_get("/api/v1/alerts/rules", self._get_alert_rules)
        self.app.router.add_post("/api/v1/alerts/rules", self._create_alert_rule)
        self.app.router.add_get("/api/v1/metrics", self._get_metrics)
        self.app.router.add_get("/api/v1/health/components", self._get_component_health)

        # 登录端点（公开），用于获取 Bearer Token
        try:
            from src.auth import login_handler
            self.app.router.add_post("/login", login_handler)
        except Exception as e:
            logger.error(f"注册 /login 端点失败: {e}")

    def _create_success_response(self, data: Any, message: str = "Success") -> web.Response:
        """兼容旧实现：委托到统一API响应工具"""
        return APIResponse.success(data, message)

    def _create_error_response(self, message: str, error_code: str = "INTERNAL_ERROR",
                               status_code: int = 500) -> web.Response:
        """兼容旧实现：委托到统一API响应工具"""
        return APIResponse.error(message, error_code, status=status_code)



    # 标准化错误代码常量
    ERROR_CODES = {
        'ALERT_NOT_FOUND': 'ALERT_NOT_FOUND',
        'RULE_NOT_FOUND': 'RULE_NOT_FOUND',
        'INVALID_ALERT_DATA': 'INVALID_ALERT_DATA',
        'INVALID_RULE_DATA': 'INVALID_RULE_DATA',
        'METRICS_UNAVAILABLE': 'METRICS_UNAVAILABLE',
        'COMPONENT_HEALTH_ERROR': 'COMPONENT_HEALTH_ERROR',
        'INVALID_PARAMETERS': 'INVALID_PARAMETERS',
        'SERVICE_UNAVAILABLE': 'SERVICE_UNAVAILABLE',
        'OPERATION_NOT_ALLOWED': 'OPERATION_NOT_ALLOWED',
        'INTERNAL_ERROR': 'INTERNAL_ERROR'
    }

    async def on_startup(self):
        """服务启动初始化"""
        try:
            logger.info("开始初始化监控告警服务...")

            # 1. 初始化告警数据
            self._initialize_alert_data()

            # 2. 初始化组件健康状态
            self._initialize_component_health()

            # 3. 初始化指标数据
            self._initialize_metrics_data()

            # 4. 标记服务已初始化
            self.is_initialized = True

            logger.info("🎉 监控告警服务初始化成功")
            logger.info(f"   - 告警规则: {len(self.alert_rules)}个")
            logger.info(f"   - 活跃告警: {len(self.alerts)}个")
            logger.info(f"   - 监控组件: {len(self.component_health)}个")

        except Exception as e:
            logger.error(f"服务初始化失败: {e}", exc_info=True)
            self.is_initialized = False
            # 不抛出异常，允许服务以降级模式运行
            logger.warning("服务将以降级模式运行")

    def _initialize_alert_data(self):
        """初始化告警数据（支持 mock 与真实后端）"""
        if self.use_mock:
            self.alert_rules = get_mock_rules()
            self.alerts = get_mock_alerts()
        else:
            # 实时从后端获取，初始化仅设置为空，按需在请求时拉取
            self.alert_rules = []
            self.alerts = []

        # 更新统计信息
        self.stats['alert_rules_count'] = len(self.alert_rules)
        self.stats['total_alerts'] = len(self.alerts)
        self.stats['active_alerts'] = len([a for a in self.alerts if a.get('status') == 'active'])

        logger.info(f"✅ 告警数据初始化完成: {len(self.alert_rules)}个规则, {len(self.alerts)}个告警 (use_mock={self.use_mock})")

    def _initialize_component_health(self):
        """初始化组件健康状态"""
        # 组件健康状态
        self.component_health = {
            'alert_manager': {
                'status': 'healthy',
                'last_check': datetime.now(timezone.utc).isoformat(),
                'uptime_seconds': 0,
                'version': '2.0.0'
            },
            'rule_engine': {
                'status': 'healthy',
                'last_check': datetime.now(timezone.utc).isoformat(),
                'rules_loaded': len(self.alert_rules),
                'version': '2.0.0'
            },
            'data_collector': {
                'status': 'healthy',
                'last_check': datetime.now(timezone.utc).isoformat(),
                'endpoint': 'http://marketprism-data-collector:8084',
                'version': '1.0.0'
            },
            'message_broker': {
                'status': 'healthy',
                'last_check': datetime.now(timezone.utc).isoformat(),
                'endpoint': 'http://marketprism-message-broker:8086',
                'version': '1.0.0'
            },
            'task_worker': {
                'status': 'healthy',
                'last_check': datetime.now(timezone.utc).isoformat(),
                'endpoint': 'http://marketprism-task-worker:8090',
                'version': '1.0.0'
            },
            'prometheus': {
                'status': 'healthy',
                'last_check': datetime.now(timezone.utc).isoformat(),
                'endpoint': 'http://marketprism-prometheus:9090',
                'version': 'latest'
            }
        }

        logger.info(f"✅ 组件健康状态初始化完成: {len(self.component_health)}个组件")

    def _initialize_metrics_data(self):
        """初始化指标数据（mock 可用）"""
        if self.use_mock:
            self.metrics_data = get_mock_metrics()
        else:
            self.metrics_data = {}
        logger.info("✅ 指标数据初始化完成 (use_mock=%s)", self.use_mock)

    async def _get_service_status(self, request: web.Request) -> web.Response:
        """获取服务状态 - 标准化API端点"""
        try:
            self.stats['request_count'] += 1

            # 计算运行时间
            uptime_seconds = (datetime.now(timezone.utc) - self.start_time).total_seconds()

            status_data = {
                "service": "monitoring-alerting",
                "status": "running" if self.is_initialized else "initializing",
                "uptime_seconds": round(uptime_seconds, 2),
                "version": "2.0.0",
                "environment": self.config.get('environment', 'production'),
                "port": self.config.get('port', 8082),
                "features": {
                    "alert_management": True,
                    "rule_engine": True,
                    "metrics_collection": True,
                    "prometheus_integration": True,
                    "grafana_support": True
                },
                "statistics": {
                    "total_alerts": self.stats['total_alerts'],
                    "active_alerts": self.stats['active_alerts'],
                    "alert_rules_count": self.stats['alert_rules_count'],
                    "request_count": self.stats['request_count'],
                    "last_alert_time": self.stats['last_alert_time']
                },
                "component_health": {
                    name: comp['status'] for name, comp in self.component_health.items()
                }
            }

            return self._create_success_response(status_data, "Service status retrieved successfully")

        except Exception as e:
            logger.error(f"获取服务状态失败: {e}", exc_info=True)
            return self._create_error_response(
                f"Failed to retrieve service status: {str(e)}",
                self.ERROR_CODES['INTERNAL_ERROR']
            )

    async def _get_alerts(self, request: web.Request) -> web.Response:
        """获取告警列表"""
        try:
            self.stats['request_count'] += 1

            # 获取查询参数
            status = request.query.get('status')
            severity = request.query.get('severity')
            category = request.query.get('category')
            limit = int(request.query.get('limit', 100))

            if self.use_mock:
                filtered_alerts = self.alerts.copy()
                if status:
                    filtered_alerts = [a for a in filtered_alerts if a.get('status') == status]
                if severity:
                    filtered_alerts = [a for a in filtered_alerts if a.get('severity') == severity]
                if category:
                    filtered_alerts = [a for a in filtered_alerts if a.get('category') == category]
                total = len(self.alerts)
            else:
                # 实时从 Alertmanager 获取
                filtered_alerts = await am_fetch_alerts(
                    self.alertmanager_base_url, status=status, severity=severity, limit=limit
                )
                if category:
                    filtered_alerts = [a for a in filtered_alerts if a.get('category') == category]
                total = len(filtered_alerts)

            # 限制返回数量
            filtered_alerts = filtered_alerts[:limit]

            return self._create_success_response({
                "alerts": filtered_alerts,
                "total_count": total,
                "filtered_count": len(filtered_alerts),
                "filters_applied": {
                    "status": status,
                    "severity": severity,
                    "category": category,
                    "limit": limit
                }
            }, "Alerts retrieved successfully")

        except ValueError as e:
            return self._create_error_response(
                f"Invalid parameters: {str(e)}",
                self.ERROR_CODES['INVALID_PARAMETERS'],
                400
            )
        except Exception as e:
            logger.error(f"获取告警列表失败: {e}", exc_info=True)
            return self._create_error_response(
                f"Failed to retrieve alerts: {str(e)}",
                self.ERROR_CODES['INTERNAL_ERROR']
            )

    async def _create_alert(self, request: web.Request) -> web.Response:
        """创建新告警"""
        try:

            # 非 mock 模式下，禁止通过本服务直接创建告警
            if not self.use_mock:
                return self._create_error_response(
                    "Alert creation not supported when USE_MOCK_DATA=false",
                    self.ERROR_CODES['OPERATION_NOT_ALLOWED'],
                    501
                )

            self.stats['request_count'] += 1

            # 解析请求数据
            data = await request.json()

            # 验证必需字段
            required_fields = ['name', 'severity', 'description', 'source']
            for field in required_fields:
                if field not in data:
                    return self._create_error_response(
                        f"Missing required field: {field}",
                        self.ERROR_CODES['INVALID_ALERT_DATA'],
                        400
                    )

            # 创建新告警
            new_alert = {
                'id': f"alert-{len(self.alerts) + 1:03d}",
                'rule_id': data.get('rule_id'),
                'name': data['name'],
                'severity': data['severity'],
                'status': data.get('status', 'active'),
                'category': data.get('category', 'custom'),
                'timestamp': datetime.now(timezone.utc).isoformat(),
                'description': data['description'],
                'source': data['source'],
                'labels': data.get('labels', {})
            }

            # 添加到告警列表
            self.alerts.append(new_alert)

            # 更新统计信息
            self.stats['total_alerts'] = len(self.alerts)
            self.stats['active_alerts'] = len([a for a in self.alerts if a['status'] == 'active'])
            self.stats['last_alert_time'] = new_alert['timestamp']

            return self._create_success_response(new_alert, "Alert created successfully")

        except json.JSONDecodeError:
            return self._create_error_response(
                "Invalid JSON data",
                self.ERROR_CODES['INVALID_ALERT_DATA'],
                400
            )
        except Exception as e:
            logger.error(f"创建告警失败: {e}", exc_info=True)
            return self._create_error_response(
                f"Failed to create alert: {str(e)}",
                self.ERROR_CODES['INTERNAL_ERROR']
            )

    async def _get_alert_rules(self, request: web.Request) -> web.Response:
        """获取告警规则列表"""
        try:
            self.stats['request_count'] += 1

            # 获取查询参数
            enabled = request.query.get('enabled')
            category = request.query.get('category')
            severity = request.query.get('severity')

            if self.use_mock:
                rules = self.alert_rules.copy()
                total = len(self.alert_rules)
            else:
                # 从 Prometheus 拉取告警规则
                rules = await prom_fetch_rules(self.prometheus_base_url)
                total = len(rules)

            # 过滤规则
            filtered_rules = rules
            if enabled is not None:
                enabled_bool = enabled.lower() == 'true'
                filtered_rules = [r for r in filtered_rules if r.get('enabled') == enabled_bool]
            if category:
                filtered_rules = [r for r in filtered_rules if r.get('category') == category]
            if severity:
                filtered_rules = [r for r in filtered_rules if r.get('severity') == severity]

            return self._create_success_response({
                "rules": filtered_rules,
                "total_count": total,
                "filtered_count": len(filtered_rules),
                "filters_applied": {
                    "enabled": enabled,
                    "category": category,
                    "severity": severity
                }
            }, "Alert rules retrieved successfully")

        except Exception as e:
            logger.error(f"获取告警规则失败: {e}", exc_info=True)
            return self._create_error_response(
                f"Failed to retrieve alert rules: {str(e)}",
                self.ERROR_CODES['INTERNAL_ERROR']
            )

    async def _create_alert_rule(self, request: web.Request) -> web.Response:
        """创建新告警规则"""
        try:
            # 非 mock 模式下，禁止通过本服务直接创建告警规则
            if not self.use_mock:
                return self._create_error_response(
                    "Alert rule creation not supported when USE_MOCK_DATA=false",
                    self.ERROR_CODES['OPERATION_NOT_ALLOWED'],
                    501
                )

            self.stats['request_count'] += 1

            # 解析请求数据
            data = await request.json()

            # 验证必需字段
            required_fields = ['name', 'description', 'severity', 'conditions']
            for field in required_fields:
                if field not in data:
                    return self._create_error_response(
                        f"Missing required field: {field}",
                        self.ERROR_CODES['INVALID_RULE_DATA'],
                        400
                    )

            # 验证条件格式
            if not isinstance(data['conditions'], list) or not data['conditions']:
                return self._create_error_response(
                    "Conditions must be a non-empty list",
                    self.ERROR_CODES['INVALID_RULE_DATA'],
                    400
                )

            # 创建新规则
            new_rule = {
                'id': f"rule-{len(self.alert_rules) + 1:03d}",
                'name': data['name'],
                'description': data['description'],
                'severity': data['severity'],
                'category': data.get('category', 'custom'),
                'enabled': data.get('enabled', True),
                'conditions': data['conditions'],
                'created_at': datetime.now(timezone.utc).isoformat(),
                'updated_at': datetime.now(timezone.utc).isoformat()
            }

            # 添加到规则列表
            self.alert_rules.append(new_rule)

            # 更新统计信息
            self.stats['alert_rules_count'] = len(self.alert_rules)

            return self._create_success_response(new_rule, "Alert rule created successfully")

        except json.JSONDecodeError:
            return self._create_error_response(
                "Invalid JSON data",
                self.ERROR_CODES['INVALID_RULE_DATA'],
                400
            )
        except Exception as e:
            logger.error(f"创建告警规则失败: {e}", exc_info=True)
            return self._create_error_response(
                f"Failed to create alert rule: {str(e)}",
                self.ERROR_CODES['INTERNAL_ERROR']
            )

    async def _get_metrics(self, request: web.Request) -> web.Response:
        """获取监控指标"""
        try:
            self.stats['request_count'] += 1

            # 获取查询参数
            category = request.query.get('category')  # system, service, business
            format_type = request.query.get('format', 'json')  # json, prometheus

            # 过滤指标
            if category and category in self.metrics_data:
                metrics = {category: self.metrics_data[category]}
            else:
                metrics = self.metrics_data

            # 如果请求Prometheus格式
            if format_type == 'prometheus':
                prometheus_metrics = self._format_prometheus_metrics(metrics)
                return web.Response(text=prometheus_metrics, content_type='text/plain')

            return self._create_success_response({
                "metrics": metrics,
                "available_categories": list(self.metrics_data.keys()),
                "last_updated": datetime.now(timezone.utc).isoformat()
            }, "Metrics retrieved successfully")

        except Exception as e:
            logger.error(f"获取指标失败: {e}", exc_info=True)
            return self._create_error_response(
                f"Failed to retrieve metrics: {str(e)}",
                self.ERROR_CODES['METRICS_UNAVAILABLE']
            )

    async def _get_component_health(self, request: web.Request) -> web.Response:
        """获取组件健康状态"""
        try:
            self.stats['request_count'] += 1

            # 更新组件健康状态（模拟实时检查）
            self._update_component_health()

            # 计算总体健康状态
            healthy_count = sum(1 for comp in self.component_health.values()
                              if comp['status'] == 'healthy')
            total_count = len(self.component_health)
            overall_health = 'healthy' if healthy_count == total_count else 'degraded'

            return self._create_success_response({
                "overall_health": overall_health,
                "healthy_components": healthy_count,
                "total_components": total_count,
                "components": self.component_health,
                "last_check": datetime.now(timezone.utc).isoformat()
            }, "Component health retrieved successfully")

        except Exception as e:
            logger.error(f"获取组件健康状态失败: {e}", exc_info=True)
            return self._create_error_response(
                f"Failed to retrieve component health: {str(e)}",
                self.ERROR_CODES['COMPONENT_HEALTH_ERROR']
            )

    def _format_prometheus_metrics(self, metrics: Dict[str, Any]) -> str:
        """格式化为Prometheus指标格式"""
        prometheus_lines = []

        for category, category_metrics in metrics.items():
            for metric_name, value in category_metrics.items():
                if metric_name == 'last_updated':
                    continue

                if isinstance(value, (int, float)):
                    prometheus_lines.append(f"marketprism_{category}_{metric_name} {value}")

        return '\n'.join(prometheus_lines) + '\n'

    def _update_component_health(self):
        """更新组件健康状态（模拟）"""
        current_time = datetime.now(timezone.utc).isoformat()

        for component_name, component_info in self.component_health.items():
            # 模拟健康检查
            component_info['last_check'] = current_time
            # 在实际实现中，这里会进行真实的健康检查

    async def on_shutdown(self):
        """服务关闭清理"""
        try:
            logger.info("开始关闭监控告警服务...")

            # 清理资源
            self.is_initialized = False

            # 保存统计信息（如果需要持久化）
            logger.info(f"服务运行统计:")
            logger.info(f"  - 处理请求: {self.stats['request_count']}个")
            logger.info(f"  - 告警规则: {self.stats['alert_rules_count']}个")
            logger.info(f"  - 总告警数: {self.stats['total_alerts']}个")

            logger.info("🎉 监控告警服务已安全关闭")

        except Exception as e:
            logger.error(f"服务关闭时发生错误: {e}", exc_info=True)




async def main():
    """主函数"""
    # 默认配置
    config = {
        'environment': 'production',
        'port': 8082,
        'host': '0.0.0.0',
        'log_level': 'INFO'
    }

    # 创建服务实例
    service = MonitoringAlertingService(config)

    try:
        # 启动服务 - 使用BaseService的run方法
        # run() 方法包含完整的生命周期管理：
        # 1. 创建应用和路由
        # 2. 调用 on_startup()
        # 3. 启动 HTTP 服务器
        # 4. 等待停止信号（SIGINT/SIGTERM）
        # 5. 调用 on_shutdown()
        # 6. 清理资源
        await service.run()

    except KeyboardInterrupt:
        # run() 方法已经处理了 SIGINT，这里通常不会到达
        logger.info("收到中断信号，正在关闭服务...")
    except Exception as e:
        logger.error(f"服务运行时发生错误: {e}", exc_info=True)
        raise  # 重新抛出异常以便调试


if __name__ == "__main__":
    # 统一日志初始化
    configure_logging(service_name="monitoring-alerting")
    logger = get_logger(__name__, service="monitoring-alerting")

    # 运行服务
    asyncio.run(main())
