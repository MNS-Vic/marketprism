"""
配置安全加固系统模块

提供企业级配置安全加固功能，包括：
- 安全策略引擎
- 威胁检测和防护系统
- 安全配置验证
- 安全强化措施
- 实时安全监控和报告

Week 5 Day 6 实现 - 配置安全加固系统
"""

import time

from .security_policy_engine import (
    SecurityPolicyEngine,
    SecurityPolicy,
    PolicyRule,
    PolicyAction,
    PolicyCondition,
    PolicyType,
    PolicySeverity,
    PolicyStatus,
    PolicyViolation,
    PolicyEnforcementError,
    create_security_policy_engine
)

from .threat_detection_system import (
    ThreatDetectionSystem,
    ThreatType,
    ThreatIndicator,
    ThreatPattern,
    ThreatEvent,
    ThreatResponse,
    AttackVector,
    ThreatLevel,
    DetectionRule,
    ThreatIntelligence,
    ThreatDetectionError,
    create_threat_detection_system
)

from .security_validator import (
    SecurityValidator,
    ValidationRule,
    ValidationResult,
    ValidationLevel,
    SecurityStandard,
    ConfigSecurityCheck,
    SecurityRecommendation,
    SecurityValidationError,
    create_security_validator
)

from .security_hardening_measures import (
    SecurityHardeningMeasures,
    HardeningCategory,
    HardeningMeasure,
    HardeningResult,
    HardeningStatus,
    SystemHardening,
    NetworkHardening,
    ApplicationHardening,
    DataHardening,
    SecurityHardeningError,
    create_security_hardening_measures
)

from .security_monitoring import (
    SecurityMonitoring,
    SecurityEvent,
    SecurityEventType,
    SecurityMetric,
    SecurityAlert,
    SecurityDashboard,
    SecurityReport,
    MonitoringRule,
    RealTimeMonitor,
    AlertLevel,
    SecurityMonitoringError,
    create_security_monitoring
)

__all__ = [
    # 安全策略引擎
    'SecurityPolicyEngine',
    'SecurityPolicy',
    'PolicyRule',
    'PolicyAction',
    'PolicyCondition',
    'PolicyType',
    'PolicySeverity',
    'PolicyStatus',
    'PolicyViolation',
    'PolicyEnforcementError',
    'create_security_policy_engine',
    
    # 威胁检测系统
    'ThreatDetectionSystem',
    'ThreatType',
    'ThreatIndicator',
    'ThreatPattern',
    'ThreatEvent',
    'ThreatResponse',
    'AttackVector',
    'ThreatLevel',
    'DetectionRule',
    'ThreatIntelligence',
    'ThreatDetectionError',
    'create_threat_detection_system',
    
    # 安全验证器
    'SecurityValidator',
    'ValidationRule',
    'ValidationResult',
    'ValidationLevel',
    'SecurityStandard',
    'ConfigSecurityCheck',
    'SecurityRecommendation',
    'SecurityValidationError',
    'create_security_validator',
    
    # 安全加固措施
    'SecurityHardeningMeasures',
    'HardeningCategory',
    'HardeningMeasure',
    'HardeningResult',
    'HardeningStatus',
    'SystemHardening',
    'NetworkHardening',
    'ApplicationHardening',
    'DataHardening',
    'SecurityHardeningError',
    'create_security_hardening_measures',
    
    # 安全监控
    'SecurityMonitoring',
    'SecurityEvent',
    'SecurityEventType',
    'SecurityMetric',
    'SecurityAlert',
    'SecurityDashboard',
    'SecurityReport',
    'MonitoringRule',
    'RealTimeMonitor',
    'AlertLevel',
    'SecurityMonitoringError',
    'create_security_monitoring',
    
    # 集成系统
    'SecurityHardeningManager'
]


class SecurityHardeningManager:
    """
    安全加固管理器
    
    统一管理所有安全加固组件，提供企业级安全加固能力。
    """
    
    def __init__(
        self,
        enable_policy_engine: bool = True,
        enable_threat_detection: bool = True,
        enable_security_validation: bool = True,
        enable_hardening_measures: bool = True,
        enable_security_monitoring: bool = True,
        config_path: str = None
    ):
        """初始化安全加固管理器"""
        self.config_path = config_path or "/tmp/security_hardening"
        
        # 初始化核心组件
        self.policy_engine = None
        self.threat_detection = None
        self.security_validator = None
        self.hardening_measures = None
        self.security_monitoring = None
        
        if enable_policy_engine:
            self.policy_engine = create_security_policy_engine(
                config_path=f"{self.config_path}/policies"
            )
        
        if enable_threat_detection:
            self.threat_detection = create_threat_detection_system(
                config_path=f"{self.config_path}/threats"
            )
        
        if enable_security_validation:
            self.security_validator = create_security_validator(
                config_path=f"{self.config_path}/validation"
            )
        
        if enable_hardening_measures:
            self.hardening_measures = create_security_hardening_measures(
                config_path=f"{self.config_path}/hardening"
            )
        
        if enable_security_monitoring:
            self.security_monitoring = create_security_monitoring(
                config_path=f"{self.config_path}/monitoring"
            )
        
        # 系统状态
        self.is_active = False
        self.start_time = None
        
    def start_security_hardening(self) -> bool:
        """启动安全加固系统"""
        try:
            import time
            
            # 启动各个组件
            if self.policy_engine:
                self.policy_engine.start()
            
            if self.threat_detection:
                self.threat_detection.start_detection()
            
            if self.security_validator:
                self.security_validator.start_validation()
            
            if self.hardening_measures:
                self.hardening_measures.start_hardening()
            
            if self.security_monitoring:
                self.security_monitoring.start_monitoring()
            
            self.is_active = True
            self.start_time = time.time()
            
            return True
            
        except Exception as e:
            raise SecurityHardeningError(f"启动安全加固系统失败: {e}")
    
    def stop_security_hardening(self) -> bool:
        """停止安全加固系统"""
        try:
            # 停止各个组件
            if self.security_monitoring:
                self.security_monitoring.stop_monitoring()
            
            if self.hardening_measures:
                self.hardening_measures.stop_hardening()
            
            if self.security_validator:
                self.security_validator.stop_validation()
            
            if self.threat_detection:
                self.threat_detection.stop_detection()
            
            if self.policy_engine:
                self.policy_engine.stop()
            
            self.is_active = False
            
            return True
            
        except Exception as e:
            raise SecurityHardeningError(f"停止安全加固系统失败: {e}")
    
    def perform_security_assessment(self) -> dict:
        """执行完整的安全评估"""
        assessment_result = {
            'timestamp': time.time(),
            'overall_security_level': 'UNKNOWN',
            'policy_compliance': None,
            'threat_status': None,
            'validation_results': None,
            'hardening_status': None,
            'monitoring_health': None,
            'recommendations': []
        }
        
        try:
            # 策略合规检查
            if self.policy_engine:
                policy_result = self.policy_engine.evaluate_compliance()
                assessment_result['policy_compliance'] = policy_result
            
            # 威胁状态检查
            if self.threat_detection:
                threat_status = self.threat_detection.get_threat_status()
                assessment_result['threat_status'] = threat_status
            
            # 安全验证
            if self.security_validator:
                validation_results = self.security_validator.validate_system_security()
                assessment_result['validation_results'] = validation_results
            
            # 加固状态
            if self.hardening_measures:
                hardening_status = self.hardening_measures.get_hardening_status()
                assessment_result['hardening_status'] = hardening_status
            
            # 监控健康状态
            if self.security_monitoring:
                monitoring_health = self.security_monitoring.get_monitoring_health()
                assessment_result['monitoring_health'] = monitoring_health
            
            # 计算整体安全级别
            assessment_result['overall_security_level'] = self._calculate_security_level(assessment_result)
            
            # 生成安全建议
            assessment_result['recommendations'] = self._generate_security_recommendations(assessment_result)
            
            return assessment_result
            
        except Exception as e:
            assessment_result['error'] = str(e)
            return assessment_result
    
    def _calculate_security_level(self, assessment: dict) -> str:
        """计算整体安全级别"""
        scores = []
        
        # 策略合规评分
        if assessment.get('policy_compliance'):
            compliance_rate = assessment['policy_compliance'].get('compliance_rate', 0)
            scores.append(compliance_rate * 100)
        
        # 威胁状态评分
        if assessment.get('threat_status'):
            threat_level = assessment['threat_status'].get('current_threat_level', 'MEDIUM')
            threat_score = {'LOW': 90, 'MEDIUM': 70, 'HIGH': 40, 'CRITICAL': 10}.get(threat_level, 50)
            scores.append(threat_score)
        
        # 验证结果评分
        if assessment.get('validation_results'):
            validation_score = assessment['validation_results'].get('overall_score', 50)
            scores.append(validation_score)
        
        # 加固状态评分
        if assessment.get('hardening_status'):
            hardening_score = assessment['hardening_status'].get('overall_hardening_level', 50)
            scores.append(hardening_score)
        
        if not scores:
            return 'UNKNOWN'
        
        avg_score = sum(scores) / len(scores)
        
        if avg_score >= 90:
            return 'EXCELLENT'
        elif avg_score >= 80:
            return 'GOOD'
        elif avg_score >= 70:
            return 'MEDIUM'
        elif avg_score >= 60:
            return 'POOR'
        else:
            return 'CRITICAL'
    
    def _generate_security_recommendations(self, assessment: dict) -> list:
        """生成安全改进建议"""
        recommendations = []
        
        # 基于各个组件的状态生成建议
        if assessment.get('policy_compliance'):
            if assessment['policy_compliance'].get('compliance_rate', 1) < 0.9:
                recommendations.append({
                    'category': 'POLICY_COMPLIANCE',
                    'priority': 'HIGH',
                    'description': '策略合规率偏低，建议审查和更新安全策略',
                    'action': 'review_security_policies'
                })
        
        if assessment.get('threat_status'):
            threat_level = assessment['threat_status'].get('current_threat_level', 'MEDIUM')
            if threat_level in ['HIGH', 'CRITICAL']:
                recommendations.append({
                    'category': 'THREAT_RESPONSE',
                    'priority': 'CRITICAL',
                    'description': f'当前威胁级别为{threat_level}，需要立即响应',
                    'action': 'immediate_threat_response'
                })
        
        if assessment.get('validation_results'):
            if assessment['validation_results'].get('overall_score', 100) < 80:
                recommendations.append({
                    'category': 'SECURITY_VALIDATION',
                    'priority': 'MEDIUM',
                    'description': '安全验证评分偏低，建议加强安全配置',
                    'action': 'improve_security_configuration'
                })
        
        return recommendations
    
    def get_security_dashboard(self) -> dict:
        """获取安全仪表板数据"""
        dashboard = {
            'system_status': {
                'is_active': self.is_active,
                'start_time': self.start_time,
                'uptime': time.time() - self.start_time if self.start_time else 0
            },
            'components': {
                'policy_engine': self.policy_engine is not None,
                'threat_detection': self.threat_detection is not None,
                'security_validator': self.security_validator is not None,
                'hardening_measures': self.hardening_measures is not None,
                'security_monitoring': self.security_monitoring is not None
            }
        }
        
        # 获取各组件的状态信息
        if self.policy_engine:
            dashboard['policy_status'] = self.policy_engine.get_policy_status()
        
        if self.threat_detection:
            dashboard['threat_status'] = self.threat_detection.get_detection_status()
        
        if self.security_validator:
            dashboard['validation_status'] = self.security_validator.get_validation_status()
        
        if self.hardening_measures:
            dashboard['hardening_status'] = self.hardening_measures.get_status()
        
        if self.security_monitoring:
            dashboard['monitoring_status'] = self.security_monitoring.get_status()
        
        return dashboard
    
    def generate_security_report(self, report_type: str = 'comprehensive') -> dict:
        """生成安全报告"""
        if report_type == 'comprehensive':
            return {
                'assessment': self.perform_security_assessment(),
                'dashboard': self.get_security_dashboard(),
                'detailed_analysis': self._generate_detailed_analysis()
            }
        elif report_type == 'summary':
            return self.perform_security_assessment()
        elif report_type == 'dashboard':
            return self.get_security_dashboard()
        else:
            raise ValueError(f"不支持的报告类型: {report_type}")
    
    def _generate_detailed_analysis(self) -> dict:
        """生成详细分析报告"""
        analysis = {
            'policy_analysis': None,
            'threat_analysis': None,
            'validation_analysis': None,
            'hardening_analysis': None,
            'monitoring_analysis': None
        }
        
        try:
            if self.policy_engine:
                analysis['policy_analysis'] = self.policy_engine.generate_policy_report()
            
            if self.threat_detection:
                analysis['threat_analysis'] = self.threat_detection.generate_threat_report()
            
            if self.security_validator:
                analysis['validation_analysis'] = self.security_validator.generate_validation_report()
            
            if self.hardening_measures:
                analysis['hardening_analysis'] = self.hardening_measures.generate_hardening_report()
            
            if self.security_monitoring:
                analysis['monitoring_analysis'] = self.security_monitoring.generate_monitoring_report()
            
        except Exception as e:
            analysis['error'] = str(e)
        
        return analysis


# 全局异常类
class SecurityHardeningError(Exception):
    """安全加固系统错误"""
    pass


# 便利函数
def create_security_hardening_manager(
    enable_all: bool = True,
    config_path: str = None
) -> SecurityHardeningManager:
    """
    创建安全加固管理器
    
    Args:
        enable_all: 是否启用所有组件
        config_path: 配置文件路径
        
    Returns:
        SecurityHardeningManager: 安全加固管理器实例
    """
    return SecurityHardeningManager(
        enable_policy_engine=enable_all,
        enable_threat_detection=enable_all,
        enable_security_validation=enable_all,
        enable_hardening_measures=enable_all,
        enable_security_monitoring=enable_all,
        config_path=config_path
    )


# 版本信息
__version__ = "1.0.0"
__author__ = "MarketPrism Security Hardening Team"
__description__ = "Enterprise configuration security hardening system"