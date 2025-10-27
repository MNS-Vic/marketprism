"""
IPC 协议定义 - 主进程与子进程之间的通信协议

支持的消息类型：
1. 指标数据（Metrics）
2. 健康状态（Health）
3. 控制命令（Control）
4. 日志消息（Log）
"""

from enum import Enum
from typing import Any, Dict, Optional
from dataclasses import dataclass, asdict
import time


class MessageType(Enum):
    """IPC 消息类型"""
    # 子进程 → 主进程
    METRICS = "metrics"           # 指标数据
    HEALTH = "health"             # 健康状态
    LOG = "log"                   # 日志消息
    HEARTBEAT = "heartbeat"       # 心跳
    
    # 主进程 → 子进程
    CONTROL_STOP = "control_stop"         # 停止命令
    CONTROL_RESTART = "control_restart"   # 重启命令
    CONTROL_RELOAD = "control_reload"     # 重载配置
    
    # 双向
    ACK = "ack"                   # 确认消息


@dataclass
class IPCMessage:
    """IPC 消息基类"""
    msg_type: str                 # 消息类型
    exchange: str                 # 交易所名称（进程标识）
    timestamp: float              # 时间戳
    data: Dict[str, Any]          # 消息数据
    seq: Optional[int] = None     # 序列号（可选）
    
    def to_dict(self) -> Dict[str, Any]:
        """转换为字典"""
        return asdict(self)
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'IPCMessage':
        """从字典创建消息"""
        return cls(**data)


@dataclass
class MetricsMessage:
    """指标消息"""
    exchange: str
    metrics: Dict[str, float]     # 指标名称 → 值
    timestamp: float = None
    
    def __post_init__(self):
        if self.timestamp is None:
            self.timestamp = time.time()
    
    def to_ipc_message(self) -> IPCMessage:
        """转换为 IPC 消息"""
        return IPCMessage(
            msg_type=MessageType.METRICS.value,
            exchange=self.exchange,
            timestamp=self.timestamp,
            data={"metrics": self.metrics}
        )


@dataclass
class HealthMessage:
    """健康状态消息"""
    exchange: str
    status: str                   # healthy, degraded, unhealthy
    cpu_percent: float            # CPU 使用率
    memory_mb: float              # 内存使用（MB）
    uptime_seconds: float         # 运行时间（秒）
    services: Dict[str, Any]      # 服务状态详情
    timestamp: float = None
    
    def __post_init__(self):
        if self.timestamp is None:
            self.timestamp = time.time()
    
    def to_ipc_message(self) -> IPCMessage:
        """转换为 IPC 消息"""
        return IPCMessage(
            msg_type=MessageType.HEALTH.value,
            exchange=self.exchange,
            timestamp=self.timestamp,
            data={
                "status": self.status,
                "cpu_percent": self.cpu_percent,
                "memory_mb": self.memory_mb,
                "uptime_seconds": self.uptime_seconds,
                "services": self.services
            }
        )


@dataclass
class HeartbeatMessage:
    """心跳消息"""
    exchange: str
    timestamp: float = None
    
    def __post_init__(self):
        if self.timestamp is None:
            self.timestamp = time.time()
    
    def to_ipc_message(self) -> IPCMessage:
        """转换为 IPC 消息"""
        return IPCMessage(
            msg_type=MessageType.HEARTBEAT.value,
            exchange=self.exchange,
            timestamp=self.timestamp,
            data={}
        )


@dataclass
class ControlMessage:
    """控制命令消息"""
    exchange: str                 # 目标交易所（"*" 表示所有）
    command: str                  # 命令类型
    params: Dict[str, Any]        # 命令参数
    timestamp: float = None
    
    def __post_init__(self):
        if self.timestamp is None:
            self.timestamp = time.time()
    
    def to_ipc_message(self) -> IPCMessage:
        """转换为 IPC 消息"""
        return IPCMessage(
            msg_type=self.command,
            exchange=self.exchange,
            timestamp=self.timestamp,
            data={"params": self.params}
        )


class IPCProtocol:
    """IPC 协议处理器"""
    
    @staticmethod
    def encode_message(msg: IPCMessage) -> Dict[str, Any]:
        """编码消息（准备发送）"""
        return msg.to_dict()
    
    @staticmethod
    def decode_message(data: Dict[str, Any]) -> IPCMessage:
        """解码消息（接收后）"""
        return IPCMessage.from_dict(data)
    
    @staticmethod
    def create_metrics_message(exchange: str, metrics: Dict[str, float]) -> IPCMessage:
        """创建指标消息"""
        return MetricsMessage(exchange=exchange, metrics=metrics).to_ipc_message()
    
    @staticmethod
    def create_health_message(
        exchange: str,
        status: str,
        cpu_percent: float,
        memory_mb: float,
        uptime_seconds: float,
        services: Dict[str, Any]
    ) -> IPCMessage:
        """创建健康状态消息"""
        return HealthMessage(
            exchange=exchange,
            status=status,
            cpu_percent=cpu_percent,
            memory_mb=memory_mb,
            uptime_seconds=uptime_seconds,
            services=services
        ).to_ipc_message()
    
    @staticmethod
    def create_heartbeat_message(exchange: str) -> IPCMessage:
        """创建心跳消息"""
        return HeartbeatMessage(exchange=exchange).to_ipc_message()
    
    @staticmethod
    def create_control_message(
        exchange: str,
        command: str,
        params: Optional[Dict[str, Any]] = None
    ) -> IPCMessage:
        """创建控制命令消息"""
        return ControlMessage(
            exchange=exchange,
            command=command,
            params=params or {}
        ).to_ipc_message()
    
    @staticmethod
    def create_ack_message(exchange: str, original_msg: IPCMessage) -> IPCMessage:
        """创建确认消息"""
        return IPCMessage(
            msg_type=MessageType.ACK.value,
            exchange=exchange,
            timestamp=time.time(),
            data={"ack_for": original_msg.msg_type, "ack_seq": original_msg.seq}
        )


# 消息验证
def validate_message(msg: IPCMessage) -> bool:
    """验证消息格式"""
    if not msg.msg_type:
        return False
    if not msg.exchange:
        return False
    if msg.timestamp is None or msg.timestamp <= 0:
        return False
    if msg.data is None:
        return False
    return True


# 消息序列化（用于 Pipe 传输）
def serialize_message(msg: IPCMessage) -> Dict[str, Any]:
    """序列化消息（准备通过 Pipe 发送）"""
    return IPCProtocol.encode_message(msg)


def deserialize_message(data: Dict[str, Any]) -> Optional[IPCMessage]:
    """反序列化消息（从 Pipe 接收后）"""
    try:
        msg = IPCProtocol.decode_message(data)
        if validate_message(msg):
            return msg
        return None
    except Exception:
        return None

