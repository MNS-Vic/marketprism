"""
IPC 协议单元测试
"""

import pytest
import time
from core.ipc_protocol import (
    IPCMessage, MessageType, IPCProtocol,
    MetricsMessage, HealthMessage, HeartbeatMessage, ControlMessage,
    validate_message, serialize_message, deserialize_message
)


class TestIPCMessage:
    """测试 IPCMessage 基类"""
    
    def test_create_message(self):
        """测试创建消息"""
        msg = IPCMessage(
            msg_type=MessageType.HEARTBEAT.value,
            exchange="okx_spot",
            timestamp=time.time(),
            data={}
        )
        
        assert msg.msg_type == MessageType.HEARTBEAT.value
        assert msg.exchange == "okx_spot"
        assert msg.timestamp > 0
        assert msg.data == {}
    
    def test_to_dict(self):
        """测试转换为字典"""
        msg = IPCMessage(
            msg_type=MessageType.METRICS.value,
            exchange="binance_spot",
            timestamp=123456.789,
            data={"cpu": 50.0}
        )
        
        d = msg.to_dict()
        assert d["msg_type"] == MessageType.METRICS.value
        assert d["exchange"] == "binance_spot"
        assert d["timestamp"] == 123456.789
        assert d["data"] == {"cpu": 50.0}
    
    def test_from_dict(self):
        """测试从字典创建"""
        data = {
            "msg_type": MessageType.HEALTH.value,
            "exchange": "okx_derivatives",
            "timestamp": 123456.789,
            "data": {"status": "healthy"},
            "seq": 1
        }
        
        msg = IPCMessage.from_dict(data)
        assert msg.msg_type == MessageType.HEALTH.value
        assert msg.exchange == "okx_derivatives"
        assert msg.timestamp == 123456.789
        assert msg.data == {"status": "healthy"}
        assert msg.seq == 1


class TestMetricsMessage:
    """测试 MetricsMessage"""
    
    def test_create_metrics_message(self):
        """测试创建指标消息"""
        metrics = {
            "cpu_percent": 45.5,
            "memory_mb": 120.3
        }
        
        msg = MetricsMessage(
            exchange="okx_spot",
            metrics=metrics
        )
        
        assert msg.exchange == "okx_spot"
        assert msg.metrics == metrics
        assert msg.timestamp > 0
    
    def test_to_ipc_message(self):
        """测试转换为 IPC 消息"""
        metrics = {"cpu_percent": 45.5}
        msg = MetricsMessage(exchange="okx_spot", metrics=metrics)
        
        ipc_msg = msg.to_ipc_message()
        assert ipc_msg.msg_type == MessageType.METRICS.value
        assert ipc_msg.exchange == "okx_spot"
        assert ipc_msg.data["metrics"] == metrics


class TestHealthMessage:
    """测试 HealthMessage"""
    
    def test_create_health_message(self):
        """测试创建健康状态消息"""
        msg = HealthMessage(
            exchange="binance_spot",
            status="healthy",
            cpu_percent=30.0,
            memory_mb=100.0,
            uptime_seconds=3600.0,
            services={"nats": {"status": "healthy"}}
        )
        
        assert msg.exchange == "binance_spot"
        assert msg.status == "healthy"
        assert msg.cpu_percent == 30.0
        assert msg.memory_mb == 100.0
        assert msg.uptime_seconds == 3600.0
        assert msg.services == {"nats": {"status": "healthy"}}
    
    def test_to_ipc_message(self):
        """测试转换为 IPC 消息"""
        msg = HealthMessage(
            exchange="binance_spot",
            status="healthy",
            cpu_percent=30.0,
            memory_mb=100.0,
            uptime_seconds=3600.0,
            services={}
        )
        
        ipc_msg = msg.to_ipc_message()
        assert ipc_msg.msg_type == MessageType.HEALTH.value
        assert ipc_msg.data["status"] == "healthy"
        assert ipc_msg.data["cpu_percent"] == 30.0


class TestHeartbeatMessage:
    """测试 HeartbeatMessage"""
    
    def test_create_heartbeat_message(self):
        """测试创建心跳消息"""
        msg = HeartbeatMessage(exchange="okx_derivatives")
        
        assert msg.exchange == "okx_derivatives"
        assert msg.timestamp > 0
    
    def test_to_ipc_message(self):
        """测试转换为 IPC 消息"""
        msg = HeartbeatMessage(exchange="okx_derivatives")
        ipc_msg = msg.to_ipc_message()
        
        assert ipc_msg.msg_type == MessageType.HEARTBEAT.value
        assert ipc_msg.exchange == "okx_derivatives"
        assert ipc_msg.data == {}


class TestControlMessage:
    """测试 ControlMessage"""
    
    def test_create_control_message(self):
        """测试创建控制命令消息"""
        msg = ControlMessage(
            exchange="*",
            command=MessageType.CONTROL_STOP.value,
            params={"timeout": 10}
        )
        
        assert msg.exchange == "*"
        assert msg.command == MessageType.CONTROL_STOP.value
        assert msg.params == {"timeout": 10}
    
    def test_to_ipc_message(self):
        """测试转换为 IPC 消息"""
        msg = ControlMessage(
            exchange="okx_spot",
            command=MessageType.CONTROL_RESTART.value,
            params={}
        )
        
        ipc_msg = msg.to_ipc_message()
        assert ipc_msg.msg_type == MessageType.CONTROL_RESTART.value
        assert ipc_msg.exchange == "okx_spot"


class TestIPCProtocol:
    """测试 IPCProtocol"""
    
    def test_encode_decode_message(self):
        """测试消息编码和解码"""
        original_msg = IPCMessage(
            msg_type=MessageType.METRICS.value,
            exchange="okx_spot",
            timestamp=123456.789,
            data={"cpu": 50.0}
        )
        
        # 编码
        encoded = IPCProtocol.encode_message(original_msg)
        assert isinstance(encoded, dict)
        
        # 解码
        decoded_msg = IPCProtocol.decode_message(encoded)
        assert decoded_msg.msg_type == original_msg.msg_type
        assert decoded_msg.exchange == original_msg.exchange
        assert decoded_msg.timestamp == original_msg.timestamp
        assert decoded_msg.data == original_msg.data
    
    def test_create_metrics_message(self):
        """测试创建指标消息"""
        metrics = {"cpu_percent": 45.5, "memory_mb": 120.0}
        msg = IPCProtocol.create_metrics_message("okx_spot", metrics)
        
        assert msg.msg_type == MessageType.METRICS.value
        assert msg.exchange == "okx_spot"
        assert msg.data["metrics"] == metrics
    
    def test_create_health_message(self):
        """测试创建健康状态消息"""
        msg = IPCProtocol.create_health_message(
            exchange="binance_spot",
            status="healthy",
            cpu_percent=30.0,
            memory_mb=100.0,
            uptime_seconds=3600.0,
            services={}
        )
        
        assert msg.msg_type == MessageType.HEALTH.value
        assert msg.data["status"] == "healthy"
    
    def test_create_heartbeat_message(self):
        """测试创建心跳消息"""
        msg = IPCProtocol.create_heartbeat_message("okx_derivatives")
        
        assert msg.msg_type == MessageType.HEARTBEAT.value
        assert msg.exchange == "okx_derivatives"
    
    def test_create_control_message(self):
        """测试创建控制命令消息"""
        msg = IPCProtocol.create_control_message(
            exchange="*",
            command=MessageType.CONTROL_STOP.value,
            params={"timeout": 10}
        )
        
        assert msg.msg_type == MessageType.CONTROL_STOP.value
        assert msg.data["params"]["timeout"] == 10
    
    def test_create_ack_message(self):
        """测试创建确认消息"""
        original_msg = IPCMessage(
            msg_type=MessageType.METRICS.value,
            exchange="okx_spot",
            timestamp=123456.789,
            data={},
            seq=42
        )
        
        ack_msg = IPCProtocol.create_ack_message("okx_spot", original_msg)
        
        assert ack_msg.msg_type == MessageType.ACK.value
        assert ack_msg.data["ack_for"] == MessageType.METRICS.value
        assert ack_msg.data["ack_seq"] == 42


class TestMessageValidation:
    """测试消息验证"""
    
    def test_validate_valid_message(self):
        """测试验证有效消息"""
        msg = IPCMessage(
            msg_type=MessageType.HEARTBEAT.value,
            exchange="okx_spot",
            timestamp=time.time(),
            data={}
        )
        
        assert validate_message(msg) is True
    
    def test_validate_invalid_message_no_type(self):
        """测试验证无效消息（缺少类型）"""
        msg = IPCMessage(
            msg_type="",
            exchange="okx_spot",
            timestamp=time.time(),
            data={}
        )
        
        assert validate_message(msg) is False
    
    def test_validate_invalid_message_no_exchange(self):
        """测试验证无效消息（缺少交易所）"""
        msg = IPCMessage(
            msg_type=MessageType.HEARTBEAT.value,
            exchange="",
            timestamp=time.time(),
            data={}
        )
        
        assert validate_message(msg) is False


class TestSerialization:
    """测试序列化和反序列化"""
    
    def test_serialize_deserialize(self):
        """测试序列化和反序列化"""
        original_msg = IPCMessage(
            msg_type=MessageType.METRICS.value,
            exchange="okx_spot",
            timestamp=123456.789,
            data={"cpu": 50.0, "memory": 100.0}
        )
        
        # 序列化
        serialized = serialize_message(original_msg)
        assert isinstance(serialized, dict)
        
        # 反序列化
        deserialized_msg = deserialize_message(serialized)
        assert deserialized_msg is not None
        assert deserialized_msg.msg_type == original_msg.msg_type
        assert deserialized_msg.exchange == original_msg.exchange
        assert deserialized_msg.data == original_msg.data
    
    def test_deserialize_invalid_data(self):
        """测试反序列化无效数据"""
        invalid_data = {"invalid": "data"}
        
        result = deserialize_message(invalid_data)
        assert result is None


if __name__ == "__main__":
    pytest.main([__file__, "-v"])

