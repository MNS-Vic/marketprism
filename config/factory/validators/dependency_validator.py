"""
配置依赖验证器
"""

import logging
from typing import Dict, Any, List, Set


class DependencyValidator:
    """配置依赖验证器"""
    
    def __init__(self):
        self.logger = logging.getLogger(__name__)
        
        # 服务依赖映射
        self.service_dependencies = {
            "monitoring-alerting": ["redis", "clickhouse"],
            "frontend-dashboard": ["monitoring-alerting"],
            "data-collector": ["redis", "nats"],
            "api-gateway": ["redis"]
        }
        
        # 基础设施依赖
        self.infrastructure_dependencies = {
            "prometheus": [],
            "grafana": ["prometheus"],
            "jaeger": [],
            "redis": [],
            "clickhouse": [],
            "postgresql": [],
            "nats": []
        }
    
    def validate(self, service_name: str, config: Dict[str, Any]) -> bool:
        """验证服务配置的依赖关系"""
        try:
            # 检查服务依赖
            if not self._validate_service_dependencies(service_name, config):
                return False
            
            # 检查配置完整性
            if not self._validate_config_completeness(service_name, config):
                return False
            
            # 检查循环依赖
            if not self._validate_no_circular_dependencies(service_name):
                return False
            
            self.logger.debug(f"依赖验证通过: {service_name}")
            return True
            
        except Exception as e:
            self.logger.error(f"依赖验证失败 {service_name}: {e}")
            return False
    
    def _validate_service_dependencies(self, service_name: str, config: Dict[str, Any]) -> bool:
        """验证服务依赖"""
        expected_deps = self.service_dependencies.get(service_name, [])
        config_deps = config.get('dependencies', [])
        
        # 检查必需依赖是否存在
        for dep in expected_deps:
            if dep not in config_deps:
                self.logger.error(f"缺少必需依赖 {service_name}: {dep}")
                return False
        
        # 检查配置的依赖是否有效
        for dep in config_deps:
            if dep not in self.service_dependencies and dep not in self.infrastructure_dependencies:
                self.logger.warning(f"未知依赖 {service_name}: {dep}")
        
        return True
    
    def _validate_config_completeness(self, service_name: str, config: Dict[str, Any]) -> bool:
        """验证配置完整性"""
        required_sections = {
            "monitoring-alerting": ["service", "database", "api"],
            "frontend-dashboard": ["service", "api"],
            "data-collector": ["service", "exchanges"],
            "api-gateway": ["service", "routing"]
        }
        
        required = required_sections.get(service_name, ["service"])
        
        for section in required:
            if section not in config:
                self.logger.error(f"缺少必需配置节 {service_name}: {section}")
                return False
        
        return True
    
    def _validate_no_circular_dependencies(self, service_name: str) -> bool:
        """检查循环依赖"""
        visited = set()
        rec_stack = set()
        
        def has_cycle(service: str) -> bool:
            visited.add(service)
            rec_stack.add(service)
            
            deps = self.service_dependencies.get(service, [])
            for dep in deps:
                if dep in self.service_dependencies:  # 只检查服务依赖
                    if dep not in visited:
                        if has_cycle(dep):
                            return True
                    elif dep in rec_stack:
                        return True
            
            rec_stack.remove(service)
            return False
        
        if has_cycle(service_name):
            self.logger.error(f"检测到循环依赖: {service_name}")
            return False
        
        return True
    
    def get_dependency_graph(self) -> Dict[str, List[str]]:
        """获取完整的依赖图"""
        return {
            **self.service_dependencies,
            **{k: v for k, v in self.infrastructure_dependencies.items()}
        }
    
    def get_service_dependencies(self, service_name: str) -> List[str]:
        """获取服务的所有依赖（包括传递依赖）"""
        all_deps = set()
        
        def collect_deps(service: str):
            deps = self.service_dependencies.get(service, [])
            for dep in deps:
                if dep not in all_deps:
                    all_deps.add(dep)
                    if dep in self.service_dependencies:
                        collect_deps(dep)
        
        collect_deps(service_name)
        return list(all_deps)
    
    def validate_deployment_order(self, services: List[str]) -> List[str]:
        """验证并返回正确的部署顺序"""
        # 拓扑排序
        in_degree = {service: 0 for service in services}
        graph = {}
        
        # 构建图和入度
        for service in services:
            graph[service] = []
            deps = self.service_dependencies.get(service, [])
            for dep in deps:
                if dep in services:
                    graph[dep].append(service)
                    in_degree[service] += 1
        
        # 拓扑排序
        queue = [service for service in services if in_degree[service] == 0]
        result = []
        
        while queue:
            service = queue.pop(0)
            result.append(service)
            
            for neighbor in graph[service]:
                in_degree[neighbor] -= 1
                if in_degree[neighbor] == 0:
                    queue.append(neighbor)
        
        if len(result) != len(services):
            self.logger.error("存在循环依赖，无法确定部署顺序")
            return services  # 返回原顺序
        
        return result
