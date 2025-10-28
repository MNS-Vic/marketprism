import os
import sys
from pathlib import Path
import unittest
import importlib.util

# 动态加载 services/monitoring-alerting/main.py 为模块，避免目录名含连字符导致的 import 问题
MAIN_PATH = Path(__file__).resolve().parents[2] / 'main.py'

spec = importlib.util.spec_from_file_location('monitoring_alerting_main', str(MAIN_PATH))
main_mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(main_mod)  # type: ignore

MonitoringAlertingService = main_mod.MonitoringAlertingService


class TestUtils(unittest.TestCase):
    def setUp(self):
        # 使用 mock 数据，避免外部依赖
        os.environ['USE_MOCK_DATA'] = 'true'
        self.svc = MonitoringAlertingService({"environment": "test"})

    def test_parse_limit(self):
        class DummyReq:
            def __init__(self, q):
                self.query = q
        # 正常
        self.assertEqual(self.svc._parse_limit(DummyReq({'limit': '10'})), 10)
        # 缺省
        self.assertEqual(self.svc._parse_limit(DummyReq({})), 100)
        # 越界
        self.assertEqual(self.svc._parse_limit(DummyReq({'limit': '0'})), 1)
        self.assertEqual(self.svc._parse_limit(DummyReq({'limit': '5000'})), 1000)
        # 非法
        self.assertEqual(self.svc._parse_limit(DummyReq({'limit': 'abc'})), 100)

    def test_apply_alert_filters(self):
        alerts = [
            {"status": "active", "severity": "critical", "category": "system"},
            {"status": "resolved", "severity": "warning", "category": "business"},
            {"status": "active", "severity": "warning", "category": "system"},
        ]
        r1 = self.svc._apply_alert_filters(alerts, status='active', severity=None, category=None)
        self.assertEqual(len(r1), 2)
        r2 = self.svc._apply_alert_filters(alerts, status='active', severity='warning', category=None)
        self.assertEqual(len(r2), 1)
        r3 = self.svc._apply_alert_filters(alerts, status=None, severity=None, category='system')
        self.assertEqual(len(r3), 2)

    def test_apply_rule_filters(self):
        rules = [
            {"enabled": True, "category": "system", "severity": "critical"},
            {"enabled": False, "category": "business", "severity": "warning"},
            {"enabled": True, "category": "business", "severity": "warning"},
        ]
        r1 = self.svc._apply_rule_filters(rules, enabled_str='true', category=None, severity=None)
        self.assertEqual(len(r1), 2)
        r2 = self.svc._apply_rule_filters(rules, enabled_str='false', category=None, severity=None)
        self.assertEqual(len(r2), 1)
        r3 = self.svc._apply_rule_filters(rules, enabled_str=None, category='business', severity='warning')
        self.assertEqual(len(r3), 2)


if __name__ == '__main__':
    unittest.main()

