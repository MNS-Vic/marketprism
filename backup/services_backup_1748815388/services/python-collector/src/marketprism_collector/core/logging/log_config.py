"""
日志配置模块

定义日志系统的配置选项和枚举。
"""

from enum import Enum
from typing import Dict, Any, List, Optional
from dataclasses import dataclass, field


class LogLevel(Enum):
    """日志级别枚举"""
    TRACE = "TRACE"
    DEBUG = "DEBUG"
    INFO = "INFO"
    WARNING = "WARNING"
    ERROR = "ERROR"
    CRITICAL = "CRITICAL"
    
    @property
    def numeric_level(self) -> int:
        """获取数值级别"""
        level_map = {
            LogLevel.TRACE: 5,
            LogLevel.DEBUG: 10,
            LogLevel.INFO: 20,
            LogLevel.WARNING: 30,
            LogLevel.ERROR: 40,
            LogLevel.CRITICAL: 50
        }
        return level_map[self]


class LogFormat(Enum):
    """日志格式枚举"""
    JSON = "json"
    STRUCTURED = "structured"
    COLORED = "colored"
    SIMPLE = "simple"


class LogOutput(Enum):
    """日志输出类型"""
    CONSOLE = "console"
    FILE = "file"
    SYSLOG = "syslog"
    ELASTICSEARCH = "elasticsearch"
    KAFKA = "kafka"


@dataclass
class LogRotationConfig:
    """日志轮转配置"""
    max_size: str = "100MB"  # 最大文件大小
    backup_count: int = 10   # 备份文件数量
    when: str = "midnight"   # 轮转时间（midnight, H, D, W0-W6）
    interval: int = 1        # 轮转间隔
    compress: bool = True    # 是否压缩旧文件


@dataclass
class LogOutputConfig:
    """日志输出配置"""
    output_type: LogOutput
    enabled: bool = True
    level: LogLevel = LogLevel.INFO
    format_type: LogFormat = LogFormat.STRUCTURED
    
    # 文件输出配置
    filename: Optional[str] = None
    rotation: Optional[LogRotationConfig] = None
    
    # 远程输出配置
    host: Optional[str] = None
    port: Optional[int] = None
    index: Optional[str] = None  # Elasticsearch索引
    topic: Optional[str] = None  # Kafka主题
    
    # 其他配置
    buffer_size: int = 1000
    flush_interval: float = 5.0
    extra_fields: Dict[str, Any] = field(default_factory=dict)


@dataclass
class LogConfig:
    """日志系统配置"""
    # 全局配置
    global_level: LogLevel = LogLevel.INFO
    default_format: LogFormat = LogFormat.STRUCTURED
    
    # 输出配置
    outputs: List[LogOutputConfig] = field(default_factory=list)
    
    # 结构化日志配置
    include_hostname: bool = True
    include_process_id: bool = True
    include_thread_id: bool = True
    include_caller_info: bool = True
    
    # 性能配置
    async_logging: bool = True
    queue_size: int = 10000
    
    # 过滤器配置
    filters: List[str] = field(default_factory=list)
    
    # 上下文配置
    correlation_id_header: str = "X-Correlation-ID"
    request_id_header: str = "X-Request-ID"
    
    @classmethod
    def default_console_config(cls) -> 'LogConfig':
        """创建默认控制台配置"""
        console_output = LogOutputConfig(
            output_type=LogOutput.CONSOLE,
            level=LogLevel.INFO,
            format_type=LogFormat.COLORED
        )
        
        return cls(
            global_level=LogLevel.INFO,
            outputs=[console_output]
        )
    
    @classmethod
    def default_file_config(cls, filename: str = "marketprism.log") -> 'LogConfig':
        """创建默认文件配置"""
        file_output = LogOutputConfig(
            output_type=LogOutput.FILE,
            level=LogLevel.DEBUG,
            format_type=LogFormat.JSON,
            filename=filename,
            rotation=LogRotationConfig()
        )
        
        console_output = LogOutputConfig(
            output_type=LogOutput.CONSOLE,
            level=LogLevel.INFO,
            format_type=LogFormat.COLORED
        )
        
        return cls(
            global_level=LogLevel.DEBUG,
            outputs=[console_output, file_output]
        )
    
    @classmethod
    def production_config(cls,
                         log_dir: str = "/var/log/marketprism",
                         elasticsearch_host: str = None) -> 'LogConfig':
        """创建生产环境配置"""
        outputs = []
        
        # 文件输出
        file_output = LogOutputConfig(
            output_type=LogOutput.FILE,
            level=LogLevel.INFO,
            format_type=LogFormat.JSON,
            filename=f"{log_dir}/marketprism.log",
            rotation=LogRotationConfig(
                max_size="500MB",
                backup_count=30,
                compress=True
            )
        )
        outputs.append(file_output)
        
        # 错误文件输出
        error_output = LogOutputConfig(
            output_type=LogOutput.FILE,
            level=LogLevel.ERROR,
            format_type=LogFormat.JSON,
            filename=f"{log_dir}/marketprism-error.log",
            rotation=LogRotationConfig(
                max_size="100MB",
                backup_count=10,
                compress=True
            )
        )
        outputs.append(error_output)
        
        # Elasticsearch输出（如果提供）
        if elasticsearch_host:
            es_output = LogOutputConfig(
                output_type=LogOutput.ELASTICSEARCH,
                level=LogLevel.WARNING,
                format_type=LogFormat.JSON,
                host=elasticsearch_host,
                port=9200,
                index="marketprism-logs"
            )
            outputs.append(es_output)
        
        return cls(
            global_level=LogLevel.INFO,
            outputs=outputs,
            async_logging=True,
            include_hostname=True,
            include_process_id=True
        )
    
    def to_dict(self) -> Dict[str, Any]:
        """转换为字典"""
        return {
            "global_level": self.global_level.value,
            "default_format": self.default_format.value,
            "outputs": [
                {
                    "output_type": output.output_type.value,
                    "enabled": output.enabled,
                    "level": output.level.value,
                    "format_type": output.format_type.value,
                    "filename": output.filename,
                    "rotation": output.rotation.__dict__ if output.rotation else None,
                    "host": output.host,
                    "port": output.port,
                    "index": output.index,
                    "topic": output.topic,
                    "buffer_size": output.buffer_size,
                    "flush_interval": output.flush_interval,
                    "extra_fields": output.extra_fields
                }
                for output in self.outputs
            ],
            "include_hostname": self.include_hostname,
            "include_process_id": self.include_process_id,
            "include_thread_id": self.include_thread_id,
            "include_caller_info": self.include_caller_info,
            "async_logging": self.async_logging,
            "queue_size": self.queue_size,
            "filters": self.filters,
            "correlation_id_header": self.correlation_id_header,
            "request_id_header": self.request_id_header
        }