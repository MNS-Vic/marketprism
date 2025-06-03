#!/usr/bin/env python3
"""
MarketPrism 服务路由引擎

这个模块实现了智能服务路由引擎，提供：
- 多样化路由规则
- 动态路由决策
- 流量分发策略
- A/B测试支持
- 灰度发布支持

Week 6 Day 2: 微服务服务发现系统 - 服务路由引擎
"""

import asyncio
import logging
import re
import time
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Dict, List, Optional, Set, Any, Callable, Union, Pattern
import threading
from collections import defaultdict
import random

from .service_registry import ServiceInstance, ServiceMetadata, ServiceEndpoint

logger = logging.getLogger(__name__)

class RoutingStrategy(Enum):
    """路由策略"""
    EXACT_MATCH = "exact_match"
    PREFIX_MATCH = "prefix_match"
    REGEX_MATCH = "regex_match"
    HEADER_BASED = "header_based"
    WEIGHT_BASED = "weight_based"
    VERSION_BASED = "version_based"
    CANARY = "canary"
    A_B_TEST = "a_b_test"
    BLUE_GREEN = "blue_green"

@dataclass
class RouteMatch:
    """路由匹配条件"""
    path: Optional[str] = None
    path_regex: Optional[str] = None
    method: Optional[str] = None
    headers: Dict[str, str] = field(default_factory=dict)
    query_params: Dict[str, str] = field(default_factory=dict)
    host: Optional[str] = None
    
    def __post_init__(self):
        if self.path_regex:
            self._compiled_regex = re.compile(self.path_regex)
        else:
            self._compiled_regex = None
    
    def matches(self, request_context: Dict[str, Any]) -> bool:
        """检查是否匹配请求"""
        # 路径匹配
        if self.path:
            request_path = request_context.get("path", "")
            if not request_path.startswith(self.path):
                return False
        
        # 正则匹配
        if self._compiled_regex:
            request_path = request_context.get("path", "")
            if not self._compiled_regex.match(request_path):
                return False
        
        # 方法匹配
        if self.method:
            request_method = request_context.get("method", "GET")
            if request_method.upper() != self.method.upper():
                return False
        
        # 请求头匹配
        request_headers = request_context.get("headers", {})
        for header_name, header_value in self.headers.items():
            if request_headers.get(header_name) != header_value:
                return False
        
        # 查询参数匹配
        request_params = request_context.get("query_params", {})
        for param_name, param_value in self.query_params.items():
            if request_params.get(param_name) != param_value:
                return False
        
        # 主机匹配
        if self.host:
            request_host = request_context.get("host", "")
            if request_host != self.host:
                return False
        
        return True

@dataclass
class RoutingTarget:
    """路由目标"""
    service_name: str
    service_version: Optional[str] = None
    weight: int = 100
    environment: Optional[str] = None
    tags: Set[str] = field(default_factory=set)
    metadata: Dict[str, Any] = field(default_factory=dict)
    
    # 高级路由配置
    timeout: Optional[int] = None
    retry_count: Optional[int] = None
    circuit_breaker: bool = False
    rate_limit: Optional[int] = None

@dataclass
class RoutingRule:
    """路由规则"""
    name: str
    match: RouteMatch
    targets: List[RoutingTarget]
    strategy: RoutingStrategy = RoutingStrategy.WEIGHT_BASED
    priority: int = 0  # 优先级，数字越大优先级越高
    enabled: bool = True
    
    # 高级配置
    description: Optional[str] = None
    created_at: datetime = field(default_factory=datetime.now)
    updated_at: datetime = field(default_factory=datetime.now)
    
    # A/B测试配置
    ab_test_config: Optional[Dict[str, Any]] = None
    
    # 灰度发布配置
    canary_config: Optional[Dict[str, Any]] = None
    
    def is_applicable(self, request_context: Dict[str, Any]) -> bool:
        """检查规则是否适用于请求"""
        return self.enabled and self.match.matches(request_context)

@dataclass
class RoutingContext:
    """路由上下文"""
    request_id: str
    path: str
    method: str = "GET"
    headers: Dict[str, str] = field(default_factory=dict)
    query_params: Dict[str, str] = field(default_factory=dict)
    host: str = ""
    user_id: Optional[str] = None
    session_id: Optional[str] = None
    client_ip: Optional[str] = None
    timestamp: datetime = field(default_factory=datetime.now)
    
    def to_dict(self) -> Dict[str, Any]:
        """转换为字典"""
        return {
            "request_id": self.request_id,
            "path": self.path,
            "method": self.method,
            "headers": self.headers,
            "query_params": self.query_params,
            "host": self.host,
            "user_id": self.user_id,
            "session_id": self.session_id,
            "client_ip": self.client_ip,
            "timestamp": self.timestamp
        }

@dataclass
class RoutingDecision:
    """路由决策"""
    target_service: str
    target_version: Optional[str]
    selected_instance: Optional[ServiceInstance]
    matched_rule: Optional[RoutingRule]
    strategy_used: RoutingStrategy
    decision_time: datetime
    decision_duration_ms: int
    
    # 决策元数据
    alternatives_considered: int = 0
    weight_used: Optional[int] = None
    ab_test_group: Optional[str] = None
    canary_percentage: Optional[float] = None

@dataclass
class RoutingPolicy:
    """路由策略"""
    default_strategy: RoutingStrategy = RoutingStrategy.WEIGHT_BASED
    enable_fallback: bool = True
    fallback_service: Optional[str] = None
    max_retries: int = 3
    timeout: int = 30
    
    # 负载均衡配置
    load_balance_algorithm: str = "round_robin"
    sticky_sessions: bool = False
    session_affinity_header: str = "X-Session-ID"
    
    # 故障转移配置
    enable_circuit_breaker: bool = True
    circuit_breaker_threshold: int = 10
    circuit_breaker_timeout: int = 60

@dataclass
class RoutingMetrics:
    """路由指标"""
    total_requests: int = 0
    successful_routes: int = 0
    failed_routes: int = 0
    average_decision_time: float = 0.0
    
    # 按规则统计
    rule_usage: Dict[str, int] = field(default_factory=dict)
    
    # 按服务统计
    service_usage: Dict[str, int] = field(default_factory=dict)
    
    # 按策略统计
    strategy_usage: Dict[str, int] = field(default_factory=dict)

# 异常类
class ServiceRoutingError(Exception):
    """服务路由基础异常"""
    pass

class RoutingRuleError(ServiceRoutingError):
    """路由规则异常"""
    pass

class RoutingTargetError(ServiceRoutingError):
    """路由目标异常"""
    pass

@dataclass
class ServiceRoutingConfig:
    """服务路由配置"""
    # 基本配置
    enable_routing: bool = True
    default_timeout: int = 30
    max_concurrent_routes: int = 1000
    
    # 策略配置
    default_policy: RoutingPolicy = field(default_factory=RoutingPolicy)
    
    # 缓存配置
    enable_rule_cache: bool = True
    rule_cache_ttl: int = 300
    
    # 监控配置
    enable_metrics: bool = True
    metrics_collection_interval: int = 60
    
    # 调试配置
    enable_debug_logging: bool = False
    log_routing_decisions: bool = False

class ServiceRouter:
    """
    智能服务路由引擎
    
    提供完整的服务路由、流量分发和路由策略管理功能
    """
    
    def __init__(self, config: ServiceRoutingConfig = None):
        self.config = config or ServiceRoutingConfig()
        
        self._rules: List[RoutingRule] = []
        self._rule_index: Dict[str, RoutingRule] = {}
        self._metrics = RoutingMetrics()
        self._running = False
        self._lock = threading.RLock()
        
        # 策略实现映射
        self._strategy_handlers = {
            RoutingStrategy.EXACT_MATCH: self._exact_match_routing,
            RoutingStrategy.PREFIX_MATCH: self._prefix_match_routing,
            RoutingStrategy.REGEX_MATCH: self._regex_match_routing,
            RoutingStrategy.HEADER_BASED: self._header_based_routing,
            RoutingStrategy.WEIGHT_BASED: self._weight_based_routing,
            RoutingStrategy.VERSION_BASED: self._version_based_routing,
            RoutingStrategy.CANARY: self._canary_routing,
            RoutingStrategy.A_B_TEST: self._ab_test_routing,
            RoutingStrategy.BLUE_GREEN: self._blue_green_routing
        }
        
        # 会话亲和性缓存
        self._session_cache: Dict[str, str] = {}
        
        logger.info("服务路由引擎初始化完成")
    
    async def start(self):
        """启动服务路由引擎"""
        if self._running:
            return
        
        logger.info("启动服务路由引擎")
        self._running = True
        
        # 启动指标收集任务
        if self.config.enable_metrics:
            asyncio.create_task(self._metrics_collection_loop())
        
        logger.info("服务路由引擎启动完成")
    
    async def stop(self):
        """停止服务路由引擎"""
        if not self._running:
            return
        
        logger.info("停止服务路由引擎")
        self._running = False
        
        logger.info("服务路由引擎已停止")
    
    def add_routing_rule(self, rule: RoutingRule):
        """添加路由规则"""
        with self._lock:
            # 检查规则名称唯一性
            if rule.name in self._rule_index:
                raise RoutingRuleError(f"路由规则已存在: {rule.name}")
            
            # 添加规则
            self._rules.append(rule)
            self._rule_index[rule.name] = rule
            
            # 按优先级排序
            self._rules.sort(key=lambda r: r.priority, reverse=True)
            
            logger.info(f"添加路由规则: {rule.name}")
    
    def remove_routing_rule(self, rule_name: str) -> bool:
        """移除路由规则"""
        with self._lock:
            if rule_name not in self._rule_index:
                return False
            
            rule = self._rule_index[rule_name]
            self._rules.remove(rule)
            del self._rule_index[rule_name]
            
            logger.info(f"移除路由规则: {rule_name}")
            return True
    
    def update_routing_rule(self, rule: RoutingRule):
        """更新路由规则"""
        with self._lock:
            if rule.name not in self._rule_index:
                raise RoutingRuleError(f"路由规则不存在: {rule.name}")
            
            # 移除旧规则
            old_rule = self._rule_index[rule.name]
            self._rules.remove(old_rule)
            
            # 添加新规则
            rule.updated_at = datetime.now()
            self._rules.append(rule)
            self._rule_index[rule.name] = rule
            
            # 重新排序
            self._rules.sort(key=lambda r: r.priority, reverse=True)
            
            logger.info(f"更新路由规则: {rule.name}")
    
    def get_routing_rules(self) -> List[RoutingRule]:
        """获取所有路由规则"""
        with self._lock:
            return self._rules.copy()
    
    def get_routing_rule(self, rule_name: str) -> Optional[RoutingRule]:
        """获取单个路由规则"""
        with self._lock:
            return self._rule_index.get(rule_name)
    
    async def route_request(self, context: RoutingContext, 
                          available_services: List[ServiceInstance]) -> Optional[RoutingDecision]:
        """路由请求"""
        start_time = time.time()
        
        try:
            with self._lock:
                self._metrics.total_requests += 1
            
            # 查找匹配的路由规则
            matched_rule = self._find_matching_rule(context)
            
            if not matched_rule:
                # 使用默认路由策略
                return await self._default_routing(context, available_services, start_time)
            
            # 应用匹配的规则
            decision = await self._apply_routing_rule(
                matched_rule, context, available_services, start_time
            )
            
            if decision:
                with self._lock:
                    self._metrics.successful_routes += 1
                    self._metrics.rule_usage[matched_rule.name] = \
                        self._metrics.rule_usage.get(matched_rule.name, 0) + 1
                    self._metrics.service_usage[decision.target_service] = \
                        self._metrics.service_usage.get(decision.target_service, 0) + 1
                    self._metrics.strategy_usage[decision.strategy_used.value] = \
                        self._metrics.strategy_usage.get(decision.strategy_used.value, 0) + 1
                
                if self.config.log_routing_decisions:
                    logger.info(f"路由决策: {context.request_id} -> {decision.target_service}")
            
            return decision
            
        except Exception as e:
            with self._lock:
                self._metrics.failed_routes += 1
            
            logger.error(f"路由请求失败: {e}")
            return None
    
    def get_metrics(self) -> RoutingMetrics:
        """获取路由指标"""
        with self._lock:
            return RoutingMetrics(
                total_requests=self._metrics.total_requests,
                successful_routes=self._metrics.successful_routes,
                failed_routes=self._metrics.failed_routes,
                average_decision_time=self._metrics.average_decision_time,
                rule_usage=self._metrics.rule_usage.copy(),
                service_usage=self._metrics.service_usage.copy(),
                strategy_usage=self._metrics.strategy_usage.copy()
            )
    
    # 私有方法
    def _find_matching_rule(self, context: RoutingContext) -> Optional[RoutingRule]:
        """查找匹配的路由规则"""
        request_dict = context.to_dict()
        
        for rule in self._rules:
            if rule.is_applicable(request_dict):
                return rule
        
        return None
    
    async def _apply_routing_rule(self, rule: RoutingRule, context: RoutingContext,
                                available_services: List[ServiceInstance],
                                start_time: float) -> Optional[RoutingDecision]:
        """应用路由规则"""
        # 过滤可用服务
        filtered_services = self._filter_services_by_targets(available_services, rule.targets)
        
        if not filtered_services:
            logger.warning(f"没有找到匹配的服务实例: {rule.name}")
            return None
        
        # 应用路由策略
        handler = self._strategy_handlers.get(rule.strategy)
        if not handler:
            logger.error(f"不支持的路由策略: {rule.strategy}")
            return None
        
        selected_target, selected_instance = await handler(
            rule, context, filtered_services
        )
        
        if not selected_target or not selected_instance:
            return None
        
        decision_time = int((time.time() - start_time) * 1000)
        
        return RoutingDecision(
            target_service=selected_target.service_name,
            target_version=selected_target.service_version,
            selected_instance=selected_instance,
            matched_rule=rule,
            strategy_used=rule.strategy,
            decision_time=datetime.now(),
            decision_duration_ms=decision_time,
            alternatives_considered=len(filtered_services),
            weight_used=selected_target.weight
        )
    
    async def _default_routing(self, context: RoutingContext,
                             available_services: List[ServiceInstance],
                             start_time: float) -> Optional[RoutingDecision]:
        """默认路由"""
        if not available_services:
            return None
        
        # 简单随机选择
        selected_instance = random.choice(available_services)
        decision_time = int((time.time() - start_time) * 1000)
        
        return RoutingDecision(
            target_service=selected_instance.metadata.name,
            target_version=selected_instance.metadata.version,
            selected_instance=selected_instance,
            matched_rule=None,
            strategy_used=self.config.default_policy.default_strategy,
            decision_time=datetime.now(),
            decision_duration_ms=decision_time,
            alternatives_considered=len(available_services)
        )
    
    def _filter_services_by_targets(self, services: List[ServiceInstance],
                                   targets: List[RoutingTarget]) -> List[tuple]:
        """根据目标过滤服务"""
        filtered = []
        
        for target in targets:
            for service in services:
                # 服务名称匹配
                if service.metadata.name != target.service_name:
                    continue
                
                # 版本匹配
                if target.service_version and service.metadata.version != target.service_version:
                    continue
                
                # 环境匹配
                if target.environment and service.metadata.environment != target.environment:
                    continue
                
                # 标签匹配
                if target.tags and not target.tags.issubset(service.metadata.tags):
                    continue
                
                filtered.append((target, service))
        
        return filtered
    
    # 策略实现方法
    async def _exact_match_routing(self, rule: RoutingRule, context: RoutingContext,
                                 filtered_services: List[tuple]) -> tuple:
        """精确匹配路由"""
        if not filtered_services:
            return None, None
        
        # 选择第一个匹配的服务
        return filtered_services[0]
    
    async def _prefix_match_routing(self, rule: RoutingRule, context: RoutingContext,
                                  filtered_services: List[tuple]) -> tuple:
        """前缀匹配路由"""
        return await self._exact_match_routing(rule, context, filtered_services)
    
    async def _regex_match_routing(self, rule: RoutingRule, context: RoutingContext,
                                 filtered_services: List[tuple]) -> tuple:
        """正则匹配路由"""
        return await self._exact_match_routing(rule, context, filtered_services)
    
    async def _header_based_routing(self, rule: RoutingRule, context: RoutingContext,
                                  filtered_services: List[tuple]) -> tuple:
        """基于请求头的路由"""
        # 根据特定请求头选择服务
        routing_header = context.headers.get("X-Route-Target")
        
        if routing_header:
            for target, service in filtered_services:
                if service.metadata.name == routing_header:
                    return target, service
        
        # 如果没有指定或找不到，使用权重路由
        return await self._weight_based_routing(rule, context, filtered_services)
    
    async def _weight_based_routing(self, rule: RoutingRule, context: RoutingContext,
                                  filtered_services: List[tuple]) -> tuple:
        """基于权重的路由"""
        if not filtered_services:
            return None, None
        
        # 计算总权重
        total_weight = sum(target.weight for target, _ in filtered_services)
        
        if total_weight == 0:
            return random.choice(filtered_services)
        
        # 加权随机选择
        r = random.uniform(0, total_weight)
        current_weight = 0
        
        for target, service in filtered_services:
            current_weight += target.weight
            if r <= current_weight:
                return target, service
        
        return filtered_services[-1]
    
    async def _version_based_routing(self, rule: RoutingRule, context: RoutingContext,
                                   filtered_services: List[tuple]) -> tuple:
        """基于版本的路由"""
        # 根据请求头选择版本
        version_header = context.headers.get("X-Service-Version")
        
        if version_header:
            for target, service in filtered_services:
                if service.metadata.version == version_header:
                    return target, service
        
        # 选择最新版本
        if filtered_services:
            latest = max(filtered_services, 
                        key=lambda x: x[1].metadata.version)
            return latest
        
        return None, None
    
    async def _canary_routing(self, rule: RoutingRule, context: RoutingContext,
                            filtered_services: List[tuple]) -> tuple:
        """金丝雀路由"""
        canary_config = rule.canary_config or {}
        canary_percentage = canary_config.get("percentage", 10)  # 默认10%
        canary_version = canary_config.get("version")
        
        # 生成随机数决定是否使用金丝雀版本
        if random.randint(1, 100) <= canary_percentage and canary_version:
            # 查找金丝雀版本
            for target, service in filtered_services:
                if service.metadata.version == canary_version:
                    return target, service
        
        # 使用稳定版本
        stable_services = [
            (target, service) for target, service in filtered_services
            if service.metadata.version != canary_version
        ]
        
        if stable_services:
            return await self._weight_based_routing(rule, context, stable_services)
        
        return await self._weight_based_routing(rule, context, filtered_services)
    
    async def _ab_test_routing(self, rule: RoutingRule, context: RoutingContext,
                             filtered_services: List[tuple]) -> tuple:
        """A/B测试路由"""
        ab_config = rule.ab_test_config or {}
        
        # 获取用户ID用于一致性分组
        user_id = context.user_id or context.session_id or context.client_ip
        
        if not user_id:
            # 没有用户标识，随机分配
            return random.choice(filtered_services) if filtered_services else (None, None)
        
        # 基于用户ID的哈希值确定分组
        user_hash = hash(user_id) % 100
        
        groups = ab_config.get("groups", {"A": 50, "B": 50})
        current_percentage = 0
        
        for group_name, percentage in groups.items():
            current_percentage += percentage
            if user_hash < current_percentage:
                # 查找对应分组的服务
                group_version = ab_config.get("versions", {}).get(group_name)
                if group_version:
                    for target, service in filtered_services:
                        if service.metadata.version == group_version:
                            return target, service
                break
        
        # 如果没有找到对应版本，使用默认路由
        return await self._weight_based_routing(rule, context, filtered_services)
    
    async def _blue_green_routing(self, rule: RoutingRule, context: RoutingContext,
                                filtered_services: List[tuple]) -> tuple:
        """蓝绿部署路由"""
        # 检查是否有切换标志
        switch_header = context.headers.get("X-Blue-Green-Switch")
        
        if switch_header == "green":
            # 路由到绿色环境
            green_services = [
                (target, service) for target, service in filtered_services
                if "green" in service.metadata.tags
            ]
            if green_services:
                return random.choice(green_services)
        
        # 默认路由到蓝色环境
        blue_services = [
            (target, service) for target, service in filtered_services
            if "blue" in service.metadata.tags or "green" not in service.metadata.tags
        ]
        
        if blue_services:
            return random.choice(blue_services)
        
        # 如果没有找到，使用任意可用服务
        return random.choice(filtered_services) if filtered_services else (None, None)
    
    async def _metrics_collection_loop(self):
        """指标收集循环"""
        while self._running:
            try:
                # 计算平均决策时间
                if self._metrics.total_requests > 0:
                    self._metrics.average_decision_time = (
                        sum(self._get_recent_decision_times()) / 
                        min(self._metrics.total_requests, 100)
                    )
                
                await asyncio.sleep(self.config.metrics_collection_interval)
                
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"指标收集任务异常: {e}")
                await asyncio.sleep(5)
    
    def _get_recent_decision_times(self) -> List[float]:
        """获取最近的决策时间（模拟实现）"""
        # 在实际实现中，这里应该维护一个滑动窗口的决策时间
        return [random.uniform(1, 10) for _ in range(min(self._metrics.total_requests, 100))]