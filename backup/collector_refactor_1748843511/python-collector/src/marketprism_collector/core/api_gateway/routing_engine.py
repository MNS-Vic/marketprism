"""
MarketPrism API网关 - 请求路由引擎

基于Trie树的高性能路由匹配引擎，支持动态路由配置、
路径匹配和重写、请求转发和代理功能。

Week 6 Day 1 核心组件
"""

import re
import time
import logging
from typing import Dict, List, Optional, Tuple, Any, Callable, Union
from dataclasses import dataclass, field
from enum import Enum
from urllib.parse import urlparse, parse_qs
import threading
from concurrent.futures import ThreadPoolExecutor

# 设置日志
logger = logging.getLogger(__name__)

class RouteMatchType(Enum):
    """路由匹配类型"""
    EXACT = "exact"           # 精确匹配
    PREFIX = "prefix"         # 前缀匹配
    REGEX = "regex"           # 正则表达式匹配
    WILDCARD = "wildcard"     # 通配符匹配
    PARAMETER = "parameter"   # 参数匹配 (/user/{id})

class HTTPMethod(Enum):
    """HTTP方法枚举"""
    GET = "GET"
    POST = "POST"
    PUT = "PUT"
    DELETE = "DELETE"
    PATCH = "PATCH"
    HEAD = "HEAD"
    OPTIONS = "OPTIONS"
    ANY = "*"

@dataclass
class RouteMatch:
    """路由匹配结果"""
    matched: bool = False
    route_rule: Optional['RouteRule'] = None
    path_params: Dict[str, str] = field(default_factory=dict)
    query_params: Dict[str, List[str]] = field(default_factory=dict)
    match_score: float = 0.0  # 匹配分数，用于冲突解决
    execution_time: float = 0.0  # 匹配执行时间

@dataclass
class RouteRewrite:
    """路由重写规则"""
    enabled: bool = True
    target_path: str = ""
    preserve_query: bool = True
    add_headers: Dict[str, str] = field(default_factory=dict)
    remove_headers: List[str] = field(default_factory=list)

@dataclass
class RouteRule:
    """路由规则定义"""
    # 基本信息
    rule_id: str
    name: str
    path_pattern: str
    methods: List[HTTPMethod] = field(default_factory=lambda: [HTTPMethod.ANY])
    match_type: RouteMatchType = RouteMatchType.PREFIX
    
    # 目标配置
    target_service: str = ""
    target_path: str = ""
    target_host: str = ""
    target_port: int = 80
    
    # 高级配置
    priority: int = 100  # 优先级，数字越小优先级越高
    enabled: bool = True
    timeout: float = 30.0
    retry_count: int = 3
    
    # 路由重写
    rewrite: Optional[RouteRewrite] = None
    
    # 中间件配置
    middleware: List[str] = field(default_factory=list)
    
    # 限流配置
    rate_limit: Optional[Dict[str, Any]] = None
    
    # 元数据
    created_at: float = field(default_factory=time.time)
    updated_at: float = field(default_factory=time.time)
    tags: Dict[str, str] = field(default_factory=dict)
    
    def __post_init__(self):
        """初始化后处理"""
        # 编译正则表达式（如果需要）
        if self.match_type == RouteMatchType.REGEX:
            try:
                self._compiled_regex = re.compile(self.path_pattern)
            except re.error as e:
                logger.error(f"Invalid regex pattern {self.path_pattern}: {e}")
                self._compiled_regex = None
        
        # 解析参数模式（如果需要）
        if self.match_type == RouteMatchType.PARAMETER:
            self._param_pattern, self._param_names = self._parse_parameter_pattern()
    
    def _parse_parameter_pattern(self) -> Tuple[re.Pattern, List[str]]:
        """解析参数模式，转换为正则表达式"""
        pattern = self.path_pattern
        param_names = []
        
        # 查找所有参数 {param_name}
        import re
        param_regex = re.compile(r'\{([^}]+)\}')
        matches = param_regex.findall(pattern)
        
        for param_name in matches:
            param_names.append(param_name)
            # 替换 {param_name} 为正则表达式组
            pattern = pattern.replace(f'{{{param_name}}}', r'([^/]+)')
        
        try:
            compiled_pattern = re.compile(f'^{pattern}$')
            return compiled_pattern, param_names
        except re.error as e:
            logger.error(f"Failed to compile parameter pattern {pattern}: {e}")
            return re.compile('^$'), []

class TrieNode:
    """Trie树节点，用于高效路径匹配"""
    
    def __init__(self):
        self.children: Dict[str, 'TrieNode'] = {}
        self.route_rules: List[RouteRule] = []
        self.is_endpoint: bool = False
        self.wildcard_child: Optional['TrieNode'] = None
        self.param_child: Optional['TrieNode'] = None
        self.param_name: Optional[str] = None

class RoutingEngine:
    """
    高性能路由引擎
    
    基于Trie树实现的路由匹配引擎，支持多种匹配模式：
    - 精确匹配: /api/users
    - 前缀匹配: /api/*
    - 正则匹配: /api/users/\d+
    - 参数匹配: /api/users/{id}
    - 通配符匹配: /api/**
    """
    
    def __init__(self, enable_metrics: bool = True):
        self.trie_root = TrieNode()
        self.route_rules: Dict[str, RouteRule] = {}
        self.regex_routes: List[RouteRule] = []
        self.enable_metrics = enable_metrics
        self._lock = threading.RLock()
        
        # 性能统计
        self.stats = {
            'total_matches': 0,
            'successful_matches': 0,
            'failed_matches': 0,
            'average_match_time': 0.0,
            'total_match_time': 0.0,
            'route_hits': {},
        }
        
        # 线程池用于异步操作
        self.executor = ThreadPoolExecutor(max_workers=4, thread_name_prefix="routing-engine")
        
        logger.info("RoutingEngine initialized")
    
    def add_route(self, route_rule: RouteRule) -> bool:
        """
        添加路由规则
        
        Args:
            route_rule: 路由规则
            
        Returns:
            bool: 是否添加成功
        """
        try:
            with self._lock:
                # 检查规则ID是否已存在
                if route_rule.rule_id in self.route_rules:
                    logger.warning(f"Route rule {route_rule.rule_id} already exists, updating")
                
                # 根据匹配类型添加到不同的数据结构
                if route_rule.match_type == RouteMatchType.REGEX:
                    self._add_regex_route(route_rule)
                else:
                    self._add_trie_route(route_rule)
                
                # 存储到规则字典
                self.route_rules[route_rule.rule_id] = route_rule
                
                # 初始化统计
                if self.enable_metrics:
                    self.stats['route_hits'][route_rule.rule_id] = 0
                
                logger.info(f"Added route rule: {route_rule.rule_id} -> {route_rule.path_pattern}")
                return True
                
        except Exception as e:
            logger.error(f"Failed to add route rule {route_rule.rule_id}: {e}")
            return False
    
    def _add_trie_route(self, route_rule: RouteRule):
        """将路由规则添加到Trie树"""
        path_parts = self._parse_path(route_rule.path_pattern)
        current_node = self.trie_root
        
        for part in path_parts:
            if part.startswith('{') and part.endswith('}'):
                # 参数节点
                if current_node.param_child is None:
                    current_node.param_child = TrieNode()
                    current_node.param_child.param_name = part[1:-1]
                current_node = current_node.param_child
            elif part == '*':
                # 通配符节点
                if current_node.wildcard_child is None:
                    current_node.wildcard_child = TrieNode()
                current_node = current_node.wildcard_child
            else:
                # 普通节点
                if part not in current_node.children:
                    current_node.children[part] = TrieNode()
                current_node = current_node.children[part]
        
        current_node.is_endpoint = True
        current_node.route_rules.append(route_rule)
        # 按优先级排序
        current_node.route_rules.sort(key=lambda r: r.priority)
    
    def _add_regex_route(self, route_rule: RouteRule):
        """添加正则表达式路由"""
        self.regex_routes.append(route_rule)
        # 按优先级排序
        self.regex_routes.sort(key=lambda r: r.priority)
    
    def _parse_path(self, path: str) -> List[str]:
        """解析路径为部分列表"""
        if not path.startswith('/'):
            path = '/' + path
        parts = path.strip('/').split('/')
        return [part for part in parts if part]
    
    def match_route(self, path: str, method: HTTPMethod = HTTPMethod.GET, 
                   headers: Optional[Dict[str, str]] = None) -> RouteMatch:
        """
        匹配路由规则
        
        Args:
            path: 请求路径
            method: HTTP方法
            headers: 请求头
            
        Returns:
            RouteMatch: 匹配结果
        """
        start_time = time.time()
        
        try:
            with self._lock:
                # 更新统计
                if self.enable_metrics:
                    self.stats['total_matches'] += 1
                
                # 解析路径和查询参数
                parsed_url = urlparse(path)
                clean_path = parsed_url.path
                query_params = parse_qs(parsed_url.query)
                
                # 首先尝试Trie树匹配
                trie_match = self._match_trie_route(clean_path, method, headers)
                if trie_match.matched:
                    trie_match.query_params = query_params
                    execution_time = time.time() - start_time
                    trie_match.execution_time = execution_time
                    self._update_stats(trie_match, execution_time)
                    return trie_match
                
                # 然后尝试正则表达式匹配
                regex_match = self._match_regex_route(clean_path, method, headers)
                if regex_match.matched:
                    regex_match.query_params = query_params
                    execution_time = time.time() - start_time
                    regex_match.execution_time = execution_time
                    self._update_stats(regex_match, execution_time)
                    return regex_match
                
                # 没有匹配的路由
                execution_time = time.time() - start_time
                no_match = RouteMatch(matched=False, execution_time=execution_time)
                self._update_stats(no_match, execution_time)
                return no_match
                
        except Exception as e:
            logger.error(f"Error matching route for {path}: {e}")
            execution_time = time.time() - start_time
            return RouteMatch(matched=False, execution_time=execution_time)
    
    def _match_trie_route(self, path: str, method: HTTPMethod, 
                         headers: Optional[Dict[str, str]]) -> RouteMatch:
        """使用Trie树匹配路由"""
        path_parts = self._parse_path(path)
        current_node = self.trie_root
        path_params = {}
        match_score = 0.0
        
        # 遍历路径部分
        for i, part in enumerate(path_parts):
            # 尝试精确匹配
            if part in current_node.children:
                current_node = current_node.children[part]
                match_score += 1.0  # 精确匹配得分更高
            # 尝试参数匹配
            elif current_node.param_child:
                path_params[current_node.param_child.param_name] = part
                current_node = current_node.param_child
                match_score += 0.8  # 参数匹配得分较高
            # 尝试通配符匹配
            elif current_node.wildcard_child:
                current_node = current_node.wildcard_child
                match_score += 0.5  # 通配符匹配得分较低
            else:
                # 无法匹配
                return RouteMatch(matched=False)
        
        # 检查是否到达终点
        if current_node.is_endpoint:
            # 找到匹配的路由规则
            for route_rule in current_node.route_rules:
                if self._method_matches(route_rule.methods, method) and route_rule.enabled:
                    return RouteMatch(
                        matched=True,
                        route_rule=route_rule,
                        path_params=path_params,
                        match_score=match_score
                    )
        
        return RouteMatch(matched=False)
    
    def _match_regex_route(self, path: str, method: HTTPMethod,
                          headers: Optional[Dict[str, str]]) -> RouteMatch:
        """使用正则表达式匹配路由"""
        for route_rule in self.regex_routes:
            if not route_rule.enabled:
                continue
                
            if not self._method_matches(route_rule.methods, method):
                continue
            
            if hasattr(route_rule, '_compiled_regex') and route_rule._compiled_regex:
                match = route_rule._compiled_regex.match(path)
                if match:
                    # 提取捕获组作为路径参数
                    path_params = {}
                    groups = match.groups()
                    for i, group in enumerate(groups):
                        path_params[f'param_{i}'] = group
                    
                    return RouteMatch(
                        matched=True,
                        route_rule=route_rule,
                        path_params=path_params,
                        match_score=0.6  # 正则匹配得分中等
                    )
        
        return RouteMatch(matched=False)
    
    def _method_matches(self, rule_methods: List[HTTPMethod], request_method: HTTPMethod) -> bool:
        """检查HTTP方法是否匹配"""
        return HTTPMethod.ANY in rule_methods or request_method in rule_methods
    
    def _update_stats(self, match_result: RouteMatch, execution_time: float):
        """更新性能统计"""
        if not self.enable_metrics:
            return
            
        self.stats['total_match_time'] += execution_time
        self.stats['average_match_time'] = (
            self.stats['total_match_time'] / self.stats['total_matches']
        )
        
        if match_result.matched:
            self.stats['successful_matches'] += 1
            if match_result.route_rule:
                rule_id = match_result.route_rule.rule_id
                self.stats['route_hits'][rule_id] = self.stats['route_hits'].get(rule_id, 0) + 1
        else:
            self.stats['failed_matches'] += 1
    
    def remove_route(self, rule_id: str) -> bool:
        """
        移除路由规则
        
        Args:
            rule_id: 规则ID
            
        Returns:
            bool: 是否移除成功
        """
        try:
            with self._lock:
                if rule_id not in self.route_rules:
                    logger.warning(f"Route rule {rule_id} not found")
                    return False
                
                route_rule = self.route_rules[rule_id]
                
                # 从相应数据结构中移除
                if route_rule.match_type == RouteMatchType.REGEX:
                    self.regex_routes = [r for r in self.regex_routes if r.rule_id != rule_id]
                else:
                    self._remove_trie_route(route_rule)
                
                # 从规则字典中移除
                del self.route_rules[rule_id]
                
                # 清理统计
                if self.enable_metrics and rule_id in self.stats['route_hits']:
                    del self.stats['route_hits'][rule_id]
                
                logger.info(f"Removed route rule: {rule_id}")
                return True
                
        except Exception as e:
            logger.error(f"Failed to remove route rule {rule_id}: {e}")
            return False
    
    def _remove_trie_route(self, route_rule: RouteRule):
        """从Trie树中移除路由规则"""
        # 这是一个简化实现，实际中可能需要更复杂的逻辑来清理空节点
        path_parts = self._parse_path(route_rule.path_pattern)
        current_node = self.trie_root
        
        # 导航到正确的节点
        for part in path_parts:
            if part.startswith('{') and part.endswith('}'):
                if current_node.param_child:
                    current_node = current_node.param_child
                else:
                    return  # 路径不存在
            elif part == '*':
                if current_node.wildcard_child:
                    current_node = current_node.wildcard_child
                else:
                    return  # 路径不存在
            else:
                if part in current_node.children:
                    current_node = current_node.children[part]
                else:
                    return  # 路径不存在
        
        # 移除规则
        current_node.route_rules = [
            r for r in current_node.route_rules if r.rule_id != route_rule.rule_id
        ]
        
        # 如果节点为空，标记为非终点
        if not current_node.route_rules:
            current_node.is_endpoint = False
    
    def get_route(self, rule_id: str) -> Optional[RouteRule]:
        """获取路由规则"""
        return self.route_rules.get(rule_id)
    
    def list_routes(self, enabled_only: bool = False) -> List[RouteRule]:
        """列出所有路由规则"""
        with self._lock:
            routes = list(self.route_rules.values())
            if enabled_only:
                routes = [r for r in routes if r.enabled]
            return sorted(routes, key=lambda r: r.priority)
    
    def update_route(self, rule_id: str, **updates) -> bool:
        """
        更新路由规则
        
        Args:
            rule_id: 规则ID
            **updates: 要更新的字段
            
        Returns:
            bool: 是否更新成功
        """
        try:
            with self._lock:
                if rule_id not in self.route_rules:
                    logger.warning(f"Route rule {rule_id} not found")
                    return False
                
                route_rule = self.route_rules[rule_id]
                
                # 更新字段
                for key, value in updates.items():
                    if hasattr(route_rule, key):
                        setattr(route_rule, key, value)
                
                route_rule.updated_at = time.time()
                
                # 如果路径模式或匹配类型变化，需要重新添加路由
                if 'path_pattern' in updates or 'match_type' in updates:
                    self.remove_route(rule_id)
                    self.add_route(route_rule)
                
                logger.info(f"Updated route rule: {rule_id}")
                return True
                
        except Exception as e:
            logger.error(f"Failed to update route rule {rule_id}: {e}")
            return False
    
    def get_stats(self) -> Dict[str, Any]:
        """获取性能统计"""
        with self._lock:
            stats = self.stats.copy()
            stats['total_routes'] = len(self.route_rules)
            stats['enabled_routes'] = len([r for r in self.route_rules.values() if r.enabled])
            stats['success_rate'] = (
                self.stats['successful_matches'] / max(self.stats['total_matches'], 1) * 100
            )
            return stats
    
    def cleanup(self):
        """清理资源"""
        logger.info("Cleaning up RoutingEngine")
        self.executor.shutdown(wait=True)
        with self._lock:
            self.route_rules.clear()
            self.regex_routes.clear()
            self.trie_root = TrieNode()
            self.stats = {
                'total_matches': 0,
                'successful_matches': 0,
                'failed_matches': 0,
                'average_match_time': 0.0,
                'total_match_time': 0.0,
                'route_hits': {},
            }

# 便利函数
def create_route_rule(rule_id: str, path_pattern: str, target_service: str,
                     methods: List[str] = None, **kwargs) -> RouteRule:
    """创建路由规则的便利函数"""
    if methods is None:
        methods = ["GET"]
    
    http_methods = [HTTPMethod(method.upper()) for method in methods]
    
    return RouteRule(
        rule_id=rule_id,
        name=kwargs.get('name', rule_id),
        path_pattern=path_pattern,
        methods=http_methods,
        target_service=target_service,
        **{k: v for k, v in kwargs.items() if k != 'name'}
    )