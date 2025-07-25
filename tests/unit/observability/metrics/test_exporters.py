from datetime import datetime, timezone
import unittest
from unittest.mock import MagicMock, patch
import json
from core.observability.metrics.exporters import PrometheusExporter, JSONExporter
from core.observability.metrics.metric_registry import MetricInstance, MetricValue
from core.observability.metrics.metric_categories import MetricDefinition, MetricType, MetricCategory

class TestExporters(unittest.TestCase):

    def setUp(self):
        """Set up test fixtures."""
        # Create a mock metric definition
        self.definition = MetricDefinition(
            name="test_metric", 
            metric_type=MetricType.COUNTER,
            category=MetricCategory.BUSINESS,
            description="Test metric"
        )
        
        # Create a mock metric instance
        self.metric_instance = MagicMock(spec=MetricInstance)
        self.metric_instance.definition = self.definition
        self.metric_instance.created_at = 1640000000.0
        self.metric_instance.last_updated = 1640001000.0
        
        # Create mock metric values
        metric_value = MagicMock(spec=MetricValue)
        metric_value.value = 100
        metric_value.labels = {'type': 'test'}
        metric_value.timestamp = 1640000000.0
        metric_value.metadata = {}
        
        self.metric_instance.get_values.return_value = {'test': metric_value}
        
        # Metrics dictionary in the format expected by exporters
        self.metrics = {
            'test_metric': self.metric_instance
        }

    def test_json_exporter(self):
        """Test the JSONExporter correctly formats metrics."""
        exporter = JSONExporter()
        result = exporter.export_metrics(self.metrics)
        
        # Check that the output is a valid JSON string
        try:
            data = json.loads(result)
        except json.JSONDecodeError:
            self.fail("JSONExporter did not produce a valid JSON string.")

        # Verify the structure
        self.assertIn('metrics', data)
        self.assertIn('summary', data)
        self.assertIn('test_metric', data['metrics'])

    def test_prometheus_exporter(self):
        """Test the PrometheusExporter correctly formats metrics."""
        exporter = PrometheusExporter()
        result = exporter.export_metrics(self.metrics)
        
        # Check that the output contains Prometheus format elements
        self.assertIsInstance(result, str)
        self.assertIn('# TYPE', result)  # Should contain TYPE declaration
        self.assertIn('test_metric', result)  # Should contain metric name

    def test_prometheus_exporter_no_labels(self):
        """Test PrometheusExporter with metrics that have no labels."""
        # Create metric value without labels
        metric_value = MagicMock(spec=MetricValue)
        metric_value.value = 42
        metric_value.labels = {}
        metric_value.timestamp = 1640000000.0
        metric_value.metadata = {}
        
        # Update the existing metric instance
        self.metric_instance.get_values.return_value = {'no_labels': metric_value}
        
        metric_no_labels = {'test_metric_no_labels': self.metric_instance}
        
        exporter = PrometheusExporter()
        result = exporter.export_metrics(metric_no_labels)
        
        # Verify format
        self.assertIsInstance(result, str)
        self.assertIn('42', result)  # Should contain the value


if __name__ == '__main__':
    unittest.main() 