from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict, List


def get_mock_rules() -> List[Dict[str, Any]]:
    now_str = datetime.now(timezone.utc).isoformat()
    return [
        {
            'id': 'rule-001',
            'name': 'CPU使用率过高',
            'description': 'CPU使用率超过阈值告警',
            'severity': 'high',
            'category': 'system',
            'enabled': True,
            'conditions': [
                {
                    'metric_name': 'cpu_usage_percent',
                    'operator': 'greater_than',
                    'threshold': 80.0,
                    'duration': 300
                }
            ],
            'created_at': now_str,
            'updated_at': now_str
        },
        {
            'id': 'rule-002',
            'name': '内存使用率过高',
            'description': '内存使用率超过阈值告警',
            'severity': 'medium',
            'category': 'system',
            'enabled': True,
            'conditions': [
                {
                    'metric_name': 'memory_usage_percent',
                    'operator': 'greater_than',
                    'threshold': 85.0,
                    'duration': 300
                }
            ],
            'created_at': now_str,
            'updated_at': now_str
        },
        {
            'id': 'rule-003',
            'name': 'API错误率过高',
            'description': 'API错误率超过5%',
            'severity': 'high',
            'category': 'business',
            'enabled': True,
            'conditions': [
                {
                    'metric_name': 'api_error_rate',
                    'operator': 'greater_than',
                    'threshold': 0.05,
                    'duration': 180
                }
            ],
            'created_at': now_str,
            'updated_at': now_str
        }
    ]


def get_mock_alerts() -> List[Dict[str, Any]]:
    now_str = datetime.now(timezone.utc).isoformat()
    return [
        {
            'id': 'alert-001',
            'rule_id': 'rule-001',
            'name': 'CPU使用率过高',
            'severity': 'high',
            'status': 'active',
            'category': 'system',
            'timestamp': now_str,
            'description': 'marketprism-node-01 CPU使用率达到85%',
            'source': 'marketprism-node-01',
            'labels': {
                'instance': 'marketprism-node-01',
                'service': 'data-collector'
            }
        },
        {
            'id': 'alert-002',
            'rule_id': 'rule-002',
            'name': '内存使用率过高',
            'severity': 'medium',
            'status': 'acknowledged',
            'category': 'system',
            'timestamp': now_str,
            'description': 'marketprism-node-02 内存使用率达到87%',
            'source': 'marketprism-node-02',
            'labels': {
                'instance': 'marketprism-node-02',
                'service': 'api-gateway'
            }
        }
    ]


def get_mock_metrics() -> Dict[str, Any]:
    now = datetime.now(timezone.utc).isoformat()
    return {
        'system_metrics': {
            'cpu_usage_percent': 45.2,
            'memory_usage_percent': 67.8,
            'disk_usage_percent': 34.1,
            'network_io_bytes': 1024000,
            'last_updated': now
        },
        'service_metrics': {
            'api_requests_total': 15420,
            'api_requests_per_second': 12.5,
            'api_error_rate': 0.02,
            'response_time_ms': 145.6,
            'last_updated': now
        },
        'business_metrics': {
            'active_connections': 234,
            'data_points_processed': 98765,
            'alerts_triggered_today': 8,
            'last_updated': now
        }
    }

