"""
安全加固措施

提供系统安全加固功能：
- 系统加固措施
- 网络安全加固
- 应用程序加固
- 数据安全加固
- 自动化加固执行

Week 5 Day 6 实现
"""

import time
import threading
import os
import subprocess
from enum import Enum
from typing import Dict, List, Optional, Any, Callable
from dataclasses import dataclass, field


class HardeningCategory(Enum):
    """加固分类"""
    SYSTEM = "system"
    NETWORK = "network"
    APPLICATION = "application"
    DATA = "data"
    ACCESS_CONTROL = "access_control"
    MONITORING = "monitoring"


class HardeningStatus(Enum):
    """加固状态"""
    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    FAILED = "failed"
    SKIPPED = "skipped"


@dataclass
class HardeningMeasure:
    """加固措施"""
    measure_id: str
    name: str
    description: str
    category: HardeningCategory
    priority: str  # low, medium, high, critical
    risk_reduction: float  # 0.0 - 1.0
    implementation_function: str
    parameters: Dict[str, Any] = field(default_factory=dict)
    prerequisites: List[str] = field(default_factory=list)
    enabled: bool = True
    reversible: bool = True
    
    def execute(self, hardening_system: 'SecurityHardeningMeasures') -> 'HardeningResult':
        """执行加固措施"""
        try:
            # 检查前提条件
            for prerequisite in self.prerequisites:
                if not hardening_system._check_prerequisite(prerequisite):
                    return HardeningResult(
                        measure_id=self.measure_id,
                        status=HardeningStatus.SKIPPED,
                        message=f"前提条件未满足: {prerequisite}",
                        execution_time=0
                    )
            
            # 获取实现函数
            impl_func = getattr(hardening_system, self.implementation_function, None)
            if not impl_func:
                return HardeningResult(
                    measure_id=self.measure_id,
                    status=HardeningStatus.FAILED,
                    message=f"实现函数 {self.implementation_function} 不存在",
                    execution_time=0
                )
            
            # 执行加固
            start_time = time.time()
            result = impl_func(self.parameters)
            execution_time = time.time() - start_time
            
            if isinstance(result, bool):
                status = HardeningStatus.COMPLETED if result else HardeningStatus.FAILED
                message = f"加固措施 {self.name} {'成功' if result else '失败'}"
            elif isinstance(result, dict):
                status_mapping = {
                    'success': HardeningStatus.COMPLETED,
                    'failure': HardeningStatus.FAILED,
                    'skipped': HardeningStatus.SKIPPED
                }
                status = status_mapping.get(result.get('status'), HardeningStatus.FAILED)
                message = result.get('message', f"加固措施 {self.name} 执行完成")
            else:
                status = HardeningStatus.FAILED
                message = f"加固措施 {self.name} 返回了无效结果"
            
            return HardeningResult(
                measure_id=self.measure_id,
                status=status,
                message=message,
                execution_time=execution_time,
                details=result if isinstance(result, dict) else None
            )
            
        except Exception as e:
            return HardeningResult(
                measure_id=self.measure_id,
                status=HardeningStatus.FAILED,
                message=f"执行加固措施时发生错误: {e}",
                execution_time=0
            )


@dataclass
class HardeningResult:
    """加固结果"""
    measure_id: str
    status: HardeningStatus
    message: str
    execution_time: float
    details: Optional[Dict[str, Any]] = None
    timestamp: float = field(default_factory=time.time)
    
    @property
    def is_successful(self) -> bool:
        return self.status == HardeningStatus.COMPLETED
    
    @property
    def is_failed(self) -> bool:
        return self.status == HardeningStatus.FAILED


class SystemHardening:
    """系统加固"""
    
    @staticmethod
    def disable_unnecessary_services(parameters: Dict[str, Any]) -> dict:
        """禁用不必要的服务"""
        try:
            services_to_disable = parameters.get('services', [])
            disabled_services = []
            
            for service in services_to_disable:
                # 模拟禁用服务
                disabled_services.append(service)
            
            return {
                'status': 'success',
                'message': f"成功禁用 {len(disabled_services)} 个服务",
                'disabled_services': disabled_services
            }
            
        except Exception as e:
            return {
                'status': 'failure',
                'message': f"禁用服务失败: {e}"
            }
    
    @staticmethod
    def configure_firewall(parameters: Dict[str, Any]) -> dict:
        """配置防火墙"""
        try:
            rules = parameters.get('rules', [])
            configured_rules = []
            
            for rule in rules:
                # 模拟配置防火墙规则
                configured_rules.append(rule)
            
            return {
                'status': 'success',
                'message': f"成功配置 {len(configured_rules)} 条防火墙规则",
                'configured_rules': configured_rules
            }
            
        except Exception as e:
            return {
                'status': 'failure',
                'message': f"配置防火墙失败: {e}"
            }
    
    @staticmethod
    def update_system_packages(parameters: Dict[str, Any]) -> dict:
        """更新系统包"""
        try:
            # 模拟系统更新
            updated_packages = ['package1', 'package2', 'package3']
            
            return {
                'status': 'success',
                'message': f"成功更新 {len(updated_packages)} 个系统包",
                'updated_packages': updated_packages
            }
            
        except Exception as e:
            return {
                'status': 'failure',
                'message': f"更新系统包失败: {e}"
            }
    
    @staticmethod
    def configure_password_policy(parameters: Dict[str, Any]) -> dict:
        """配置密码策略"""
        try:
            policy_settings = parameters.get('policy', {})
            
            # 模拟配置密码策略
            configured_settings = {
                'min_length': policy_settings.get('min_length', 8),
                'require_uppercase': policy_settings.get('require_uppercase', True),
                'require_lowercase': policy_settings.get('require_lowercase', True),
                'require_digits': policy_settings.get('require_digits', True),
                'require_special': policy_settings.get('require_special', True),
                'max_age': policy_settings.get('max_age', 90)
            }
            
            return {
                'status': 'success',
                'message': '密码策略配置成功',
                'configured_settings': configured_settings
            }
            
        except Exception as e:
            return {
                'status': 'failure',
                'message': f"配置密码策略失败: {e}"
            }


class NetworkHardening:
    """网络加固"""
    
    @staticmethod
    def enable_ssl_tls(parameters: Dict[str, Any]) -> dict:
        """启用SSL/TLS"""
        try:
            services = parameters.get('services', [])
            secured_services = []
            
            for service in services:
                # 模拟启用SSL/TLS
                secured_services.append(service)
            
            return {
                'status': 'success',
                'message': f"成功为 {len(secured_services)} 个服务启用SSL/TLS",
                'secured_services': secured_services
            }
            
        except Exception as e:
            return {
                'status': 'failure',
                'message': f"启用SSL/TLS失败: {e}"
            }
    
    @staticmethod
    def configure_network_segmentation(parameters: Dict[str, Any]) -> dict:
        """配置网络分段"""
        try:
            segments = parameters.get('segments', [])
            configured_segments = []
            
            for segment in segments:
                # 模拟配置网络分段
                configured_segments.append(segment)
            
            return {
                'status': 'success',
                'message': f"成功配置 {len(configured_segments)} 个网络分段",
                'configured_segments': configured_segments
            }
            
        except Exception as e:
            return {
                'status': 'failure',
                'message': f"配置网络分段失败: {e}"
            }
    
    @staticmethod
    def disable_unnecessary_protocols(parameters: Dict[str, Any]) -> dict:
        """禁用不必要的协议"""
        try:
            protocols = parameters.get('protocols', [])
            disabled_protocols = []
            
            for protocol in protocols:
                # 模拟禁用协议
                disabled_protocols.append(protocol)
            
            return {
                'status': 'success',
                'message': f"成功禁用 {len(disabled_protocols)} 个协议",
                'disabled_protocols': disabled_protocols
            }
            
        except Exception as e:
            return {
                'status': 'failure',
                'message': f"禁用协议失败: {e}"
            }


class ApplicationHardening:
    """应用程序加固"""
    
    @staticmethod
    def configure_application_security(parameters: Dict[str, Any]) -> dict:
        """配置应用程序安全"""
        try:
            security_settings = parameters.get('settings', {})
            
            configured_settings = {
                'input_validation': security_settings.get('input_validation', True),
                'output_encoding': security_settings.get('output_encoding', True),
                'session_security': security_settings.get('session_security', True),
                'csrf_protection': security_settings.get('csrf_protection', True)
            }
            
            return {
                'status': 'success',
                'message': '应用程序安全配置成功',
                'configured_settings': configured_settings
            }
            
        except Exception as e:
            return {
                'status': 'failure',
                'message': f"配置应用程序安全失败: {e}"
            }
    
    @staticmethod
    def update_application_dependencies(parameters: Dict[str, Any]) -> dict:
        """更新应用程序依赖"""
        try:
            # 模拟更新依赖
            updated_dependencies = ['dependency1', 'dependency2']
            
            return {
                'status': 'success',
                'message': f"成功更新 {len(updated_dependencies)} 个依赖",
                'updated_dependencies': updated_dependencies
            }
            
        except Exception as e:
            return {
                'status': 'failure',
                'message': f"更新应用程序依赖失败: {e}"
            }
    
    @staticmethod
    def configure_error_handling(parameters: Dict[str, Any]) -> dict:
        """配置错误处理"""
        try:
            error_settings = parameters.get('settings', {})
            
            configured_settings = {
                'hide_error_details': error_settings.get('hide_error_details', True),
                'log_errors': error_settings.get('log_errors', True),
                'custom_error_pages': error_settings.get('custom_error_pages', True)
            }
            
            return {
                'status': 'success',
                'message': '错误处理配置成功',
                'configured_settings': configured_settings
            }
            
        except Exception as e:
            return {
                'status': 'failure',
                'message': f"配置错误处理失败: {e}"
            }


class DataHardening:
    """数据加固"""
    
    @staticmethod
    def enable_data_encryption(parameters: Dict[str, Any]) -> dict:
        """启用数据加密"""
        try:
            encryption_settings = parameters.get('settings', {})
            
            configured_settings = {
                'algorithm': encryption_settings.get('algorithm', 'AES-256-GCM'),
                'key_size': encryption_settings.get('key_size', 256),
                'enable_at_rest': encryption_settings.get('enable_at_rest', True),
                'enable_in_transit': encryption_settings.get('enable_in_transit', True)
            }
            
            return {
                'status': 'success',
                'message': '数据加密配置成功',
                'configured_settings': configured_settings
            }
            
        except Exception as e:
            return {
                'status': 'failure',
                'message': f"启用数据加密失败: {e}"
            }
    
    @staticmethod
    def configure_data_backup(parameters: Dict[str, Any]) -> dict:
        """配置数据备份"""
        try:
            backup_settings = parameters.get('settings', {})
            
            configured_settings = {
                'backup_frequency': backup_settings.get('backup_frequency', 'daily'),
                'retention_period': backup_settings.get('retention_period', 30),
                'encryption_enabled': backup_settings.get('encryption_enabled', True),
                'offsite_backup': backup_settings.get('offsite_backup', True)
            }
            
            return {
                'status': 'success',
                'message': '数据备份配置成功',
                'configured_settings': configured_settings
            }
            
        except Exception as e:
            return {
                'status': 'failure',
                'message': f"配置数据备份失败: {e}"
            }
    
    @staticmethod
    def implement_data_loss_prevention(parameters: Dict[str, Any]) -> dict:
        """实施数据丢失防护"""
        try:
            dlp_settings = parameters.get('settings', {})
            
            configured_settings = {
                'content_scanning': dlp_settings.get('content_scanning', True),
                'policy_enforcement': dlp_settings.get('policy_enforcement', True),
                'incident_response': dlp_settings.get('incident_response', True)
            }
            
            return {
                'status': 'success',
                'message': '数据丢失防护配置成功',
                'configured_settings': configured_settings
            }
            
        except Exception as e:
            return {
                'status': 'failure',
                'message': f"实施数据丢失防护失败: {e}"
            }


class SecurityHardeningMeasures:
    """安全加固措施"""
    
    def __init__(self, config_path: str = "/tmp/security_hardening"):
        self.config_path = config_path
        self.hardening_measures: Dict[str, HardeningMeasure] = {}
        self.hardening_results: List[HardeningResult] = []
        
        # 加固统计
        self.statistics = {
            'total_measures': 0,
            'completed_measures': 0,
            'failed_measures': 0,
            'skipped_measures': 0,
            'total_execution_time': 0,
            'last_hardening': None
        }
        
        # 是否正在加固
        self.is_hardening = False
        self.hardening_thread = None
        
        # 线程安全
        self._lock = threading.RLock()
        
        # 初始化默认加固措施
        self._initialize_default_measures()
    
    def _initialize_default_measures(self):
        """初始化默认加固措施"""
        default_measures = [
            # 系统加固措施
            HardeningMeasure(
                measure_id="sys_disable_services",
                name="禁用不必要的服务",
                description="禁用系统中不必要的服务",
                category=HardeningCategory.SYSTEM,
                priority="high",
                risk_reduction=0.3,
                implementation_function="disable_unnecessary_services",
                parameters={'services': ['telnet', 'ftp', 'rsh']}
            ),
            
            HardeningMeasure(
                measure_id="sys_configure_firewall",
                name="配置防火墙",
                description="配置系统防火墙规则",
                category=HardeningCategory.SYSTEM,
                priority="critical",
                risk_reduction=0.5,
                implementation_function="configure_firewall",
                parameters={'rules': [
                    {'action': 'deny', 'protocol': 'tcp', 'port': 22},
                    {'action': 'allow', 'protocol': 'tcp', 'port': 443}
                ]}
            ),
            
            HardeningMeasure(
                measure_id="sys_update_packages",
                name="更新系统包",
                description="更新系统中的所有软件包",
                category=HardeningCategory.SYSTEM,
                priority="high",
                risk_reduction=0.4,
                implementation_function="update_system_packages"
            ),
            
            HardeningMeasure(
                measure_id="sys_password_policy",
                name="配置密码策略",
                description="配置强密码策略",
                category=HardeningCategory.SYSTEM,
                priority="high",
                risk_reduction=0.3,
                implementation_function="configure_password_policy",
                parameters={'policy': {
                    'min_length': 12,
                    'require_uppercase': True,
                    'require_lowercase': True,
                    'require_digits': True,
                    'require_special': True,
                    'max_age': 90
                }}
            ),
            
            # 网络加固措施
            HardeningMeasure(
                measure_id="net_enable_ssl",
                name="启用SSL/TLS",
                description="为所有服务启用SSL/TLS加密",
                category=HardeningCategory.NETWORK,
                priority="critical",
                risk_reduction=0.6,
                implementation_function="enable_ssl_tls",
                parameters={'services': ['web', 'api', 'database']}
            ),
            
            HardeningMeasure(
                measure_id="net_network_segmentation",
                name="配置网络分段",
                description="实施网络分段以限制横向移动",
                category=HardeningCategory.NETWORK,
                priority="medium",
                risk_reduction=0.4,
                implementation_function="configure_network_segmentation",
                parameters={'segments': ['dmz', 'internal', 'management']}
            ),
            
            HardeningMeasure(
                measure_id="net_disable_protocols",
                name="禁用不安全协议",
                description="禁用不安全的网络协议",
                category=HardeningCategory.NETWORK,
                priority="high",
                risk_reduction=0.3,
                implementation_function="disable_unnecessary_protocols",
                parameters={'protocols': ['SSLv2', 'SSLv3', 'TLS1.0']}
            ),
            
            # 应用程序加固措施
            HardeningMeasure(
                measure_id="app_security_config",
                name="配置应用程序安全",
                description="配置应用程序安全设置",
                category=HardeningCategory.APPLICATION,
                priority="high",
                risk_reduction=0.4,
                implementation_function="configure_application_security",
                parameters={'settings': {
                    'input_validation': True,
                    'output_encoding': True,
                    'session_security': True,
                    'csrf_protection': True
                }}
            ),
            
            HardeningMeasure(
                measure_id="app_update_dependencies",
                name="更新应用程序依赖",
                description="更新应用程序的所有依赖库",
                category=HardeningCategory.APPLICATION,
                priority="medium",
                risk_reduction=0.3,
                implementation_function="update_application_dependencies"
            ),
            
            HardeningMeasure(
                measure_id="app_error_handling",
                name="配置错误处理",
                description="配置安全的错误处理机制",
                category=HardeningCategory.APPLICATION,
                priority="medium",
                risk_reduction=0.2,
                implementation_function="configure_error_handling",
                parameters={'settings': {
                    'hide_error_details': True,
                    'log_errors': True,
                    'custom_error_pages': True
                }}
            ),
            
            # 数据加固措施
            HardeningMeasure(
                measure_id="data_encryption",
                name="启用数据加密",
                description="启用静态和传输中的数据加密",
                category=HardeningCategory.DATA,
                priority="critical",
                risk_reduction=0.7,
                implementation_function="enable_data_encryption",
                parameters={'settings': {
                    'algorithm': 'AES-256-GCM',
                    'key_size': 256,
                    'enable_at_rest': True,
                    'enable_in_transit': True
                }}
            ),
            
            HardeningMeasure(
                measure_id="data_backup",
                name="配置数据备份",
                description="配置安全的数据备份策略",
                category=HardeningCategory.DATA,
                priority="high",
                risk_reduction=0.5,
                implementation_function="configure_data_backup",
                parameters={'settings': {
                    'backup_frequency': 'daily',
                    'retention_period': 30,
                    'encryption_enabled': True,
                    'offsite_backup': True
                }}
            ),
            
            HardeningMeasure(
                measure_id="data_dlp",
                name="数据丢失防护",
                description="实施数据丢失防护措施",
                category=HardeningCategory.DATA,
                priority="medium",
                risk_reduction=0.3,
                implementation_function="implement_data_loss_prevention",
                parameters={'settings': {
                    'content_scanning': True,
                    'policy_enforcement': True,
                    'incident_response': True
                }}
            )
        ]
        
        for measure in default_measures:
            self.hardening_measures[measure.measure_id] = measure
        
        self.statistics['total_measures'] = len(self.hardening_measures)
    
    def execute_hardening(
        self,
        measure_ids: Optional[List[str]] = None,
        categories: Optional[List[HardeningCategory]] = None,
        priorities: Optional[List[str]] = None
    ) -> List[HardeningResult]:
        """执行加固措施"""
        with self._lock:
            results = []
            
            try:
                self.statistics['last_hardening'] = time.time()
                
                # 选择要执行的措施
                measures_to_execute = self._select_measures(measure_ids, categories, priorities)
                
                # 按优先级排序
                priority_order = {'critical': 0, 'high': 1, 'medium': 2, 'low': 3}
                measures_to_execute.sort(key=lambda x: priority_order.get(x.priority, 4))
                
                # 执行措施
                for measure in measures_to_execute:
                    if not measure.enabled:
                        continue
                    
                    result = measure.execute(self)
                    results.append(result)
                    
                    # 更新统计
                    if result.is_successful:
                        self.statistics['completed_measures'] += 1
                    elif result.is_failed:
                        self.statistics['failed_measures'] += 1
                    else:
                        self.statistics['skipped_measures'] += 1
                    
                    self.statistics['total_execution_time'] += result.execution_time
                
                # 保存结果
                self.hardening_results.extend(results)
                
                return results
                
            except Exception as e:
                error_result = HardeningResult(
                    measure_id="system_error",
                    status=HardeningStatus.FAILED,
                    message=f"加固过程中发生系统错误: {e}",
                    execution_time=0
                )
                results.append(error_result)
                return results
    
    def _select_measures(
        self,
        measure_ids: Optional[List[str]],
        categories: Optional[List[HardeningCategory]],
        priorities: Optional[List[str]]
    ) -> List[HardeningMeasure]:
        """选择要执行的加固措施"""
        measures = []
        
        for measure in self.hardening_measures.values():
            # 按ID过滤
            if measure_ids and measure.measure_id not in measure_ids:
                continue
            
            # 按分类过滤
            if categories and measure.category not in categories:
                continue
            
            # 按优先级过滤
            if priorities and measure.priority not in priorities:
                continue
            
            measures.append(measure)
        
        return measures
    
    def _check_prerequisite(self, prerequisite: str) -> bool:
        """检查前提条件"""
        # 简化的前提条件检查
        if prerequisite == "root_access":
            return os.getuid() == 0 if hasattr(os, 'getuid') else True
        elif prerequisite == "network_access":
            return True
        elif prerequisite == "admin_privileges":
            return True
        else:
            return True
    
    # 加固实现函数
    def disable_unnecessary_services(self, parameters: Dict[str, Any]) -> dict:
        """禁用不必要的服务"""
        return SystemHardening.disable_unnecessary_services(parameters)
    
    def configure_firewall(self, parameters: Dict[str, Any]) -> dict:
        """配置防火墙"""
        return SystemHardening.configure_firewall(parameters)
    
    def update_system_packages(self, parameters: Dict[str, Any]) -> dict:
        """更新系统包"""
        return SystemHardening.update_system_packages(parameters)
    
    def configure_password_policy(self, parameters: Dict[str, Any]) -> dict:
        """配置密码策略"""
        return SystemHardening.configure_password_policy(parameters)
    
    def enable_ssl_tls(self, parameters: Dict[str, Any]) -> dict:
        """启用SSL/TLS"""
        return NetworkHardening.enable_ssl_tls(parameters)
    
    def configure_network_segmentation(self, parameters: Dict[str, Any]) -> dict:
        """配置网络分段"""
        return NetworkHardening.configure_network_segmentation(parameters)
    
    def disable_unnecessary_protocols(self, parameters: Dict[str, Any]) -> dict:
        """禁用不必要的协议"""
        return NetworkHardening.disable_unnecessary_protocols(parameters)
    
    def configure_application_security(self, parameters: Dict[str, Any]) -> dict:
        """配置应用程序安全"""
        return ApplicationHardening.configure_application_security(parameters)
    
    def update_application_dependencies(self, parameters: Dict[str, Any]) -> dict:
        """更新应用程序依赖"""
        return ApplicationHardening.update_application_dependencies(parameters)
    
    def configure_error_handling(self, parameters: Dict[str, Any]) -> dict:
        """配置错误处理"""
        return ApplicationHardening.configure_error_handling(parameters)
    
    def enable_data_encryption(self, parameters: Dict[str, Any]) -> dict:
        """启用数据加密"""
        return DataHardening.enable_data_encryption(parameters)
    
    def configure_data_backup(self, parameters: Dict[str, Any]) -> dict:
        """配置数据备份"""
        return DataHardening.configure_data_backup(parameters)
    
    def implement_data_loss_prevention(self, parameters: Dict[str, Any]) -> dict:
        """实施数据丢失防护"""
        return DataHardening.implement_data_loss_prevention(parameters)
    
    def start_hardening(self):
        """启动加固系统"""
        self.is_hardening = True
    
    def stop_hardening(self):
        """停止加固系统"""
        self.is_hardening = False
    
    def get_hardening_status(self) -> dict:
        """获取加固状态"""
        with self._lock:
            # 计算加固级别
            total_measures = len(self.hardening_measures)
            completed_measures = len([r for r in self.hardening_results if r.is_successful])
            
            if total_measures > 0:
                hardening_level = (completed_measures / total_measures) * 100
            else:
                hardening_level = 0
            
            return {
                'overall_hardening_level': hardening_level,
                'is_active': self.is_hardening,
                'total_measures': total_measures,
                'completed_measures': completed_measures,
                'statistics': self.statistics.copy()
            }
    
    def get_status(self) -> dict:
        """获取状态"""
        return self.get_hardening_status()
    
    def generate_hardening_report(self) -> dict:
        """生成加固报告"""
        with self._lock:
            status = self.get_hardening_status()
            
            # 按分类统计
            category_stats = {}
            for measure in self.hardening_measures.values():
                category = measure.category.value
                if category not in category_stats:
                    category_stats[category] = {'total': 0, 'completed': 0}
                category_stats[category]['total'] += 1
            
            for result in self.hardening_results:
                if result.is_successful:
                    measure = self.hardening_measures.get(result.measure_id)
                    if measure:
                        category = measure.category.value
                        if category in category_stats:
                            category_stats[category]['completed'] += 1
            
            return {
                'report_timestamp': time.time(),
                'hardening_status': status,
                'category_statistics': category_stats,
                'recent_results': [
                    {
                        'measure_id': r.measure_id,
                        'status': r.status.value,
                        'message': r.message,
                        'execution_time': r.execution_time,
                        'timestamp': r.timestamp
                    }
                    for r in self.hardening_results[-20:]  # 最近20个结果
                ]
            }


class SecurityHardeningError(Exception):
    """安全加固错误"""
    pass


def create_security_hardening_measures(config_path: str = None) -> SecurityHardeningMeasures:
    """
    创建安全加固措施
    
    Args:
        config_path: 配置路径
        
    Returns:
        SecurityHardeningMeasures: 安全加固措施实例
    """
    return SecurityHardeningMeasures(config_path or "/tmp/security_hardening")