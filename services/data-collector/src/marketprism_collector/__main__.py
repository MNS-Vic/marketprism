"""
MarketPrism Python Collector 主程序入口

提供命令行接口来启动和管理数据收集器
"""

from datetime import datetime, timezone
import asyncio
import sys
import os
from pathlib import Path
import click
import structlog

from .config import Config, create_default_config
from .collector import MarketDataCollector


def setup_logging(log_level: str = "INFO", debug: bool = False):
    """设置日志记录"""
    
    # 配置structlog
    structlog.configure(
        processors=[
            structlog.stdlib.filter_by_level,
            structlog.stdlib.add_logger_name,
            structlog.stdlib.add_log_level,
            structlog.stdlib.PositionalArgumentsFormatter(),
            structlog.processors.TimeStamper(fmt="ISO"),
            structlog.processors.StackInfoRenderer(),
            structlog.processors.format_exc_info,
            structlog.processors.UnicodeDecoder(),
            structlog.processors.JSONRenderer() if not debug else structlog.dev.ConsoleRenderer(colors=True)
        ],
        context_class=dict,
        logger_factory=structlog.stdlib.LoggerFactory(),
        wrapper_class=structlog.stdlib.BoundLogger,
        cache_logger_on_first_use=True,
    )
    
    # 设置根日志级别
    import logging
    logging.basicConfig(
        format="%(message)s",
        stream=sys.stdout,
        level=getattr(logging, log_level.upper())
    )


@click.group()
@click.version_option(version="1.0.0")
def cli():
    """MarketPrism Python Collector - 高性能加密货币市场数据收集器"""
    pass


@cli.command()
@click.option(
    '--config', '-c',
    type=click.Path(exists=True, path_type=Path),
    help='配置文件路径'
)
@click.option(
    '--log-level', '-l',
    type=click.Choice(['DEBUG', 'INFO', 'WARNING', 'ERROR', 'CRITICAL']),
    default='INFO',
    help='日志级别'
)
@click.option(
    '--debug/--no-debug',
    default=False,
    help='调试模式'
)
def run(config: Path, log_level: str, debug: bool):
    """运行数据收集器"""
    
    # 设置日志
    setup_logging(log_level, debug)
    logger = structlog.get_logger(__name__)
    
    try:
        logger.info("启动MarketPrism Python Collector", version="1.0.0")
        
        # 加载配置
        if config:
            logger.info("从文件加载配置", config_path=str(config))
            app_config = Config.load_from_file(str(config))
        else:
            logger.info("使用默认配置")
            app_config = create_default_config()
        
        # 覆盖日志级别和调试设置
        app_config.collector.log_level = log_level
        app_config.debug = debug
        
        # 创建并运行收集器
        collector = MarketDataCollector(app_config)
        
        # 运行事件循环
        asyncio.run(collector.run())
        
    except KeyboardInterrupt:
        logger.info("收到中断信号，正在停止...")
    except Exception as e:
        logger.error("运行收集器失败", exc_info=True)
        sys.exit(1)


@cli.command()
@click.option(
    '--output', '-o',
    type=click.Path(path_type=Path),
    default=Path('config/services/data-collector/python-collector/collector.yaml'),
    help='配置文件输出路径'
)
def init(output: Path):
    """生成默认配置文件"""
    
    setup_logging()
    logger = structlog.get_logger(__name__)
    
    try:
        # 创建输出目录
        output.parent.mkdir(parents=True, exist_ok=True)
        
        # 生成默认配置
        config = create_default_config()
        
        # 生成YAML配置内容
        config_content = f"""# MarketPrism Python Collector 配置文件
# 生成时间: {datetime.now(timezone.utc).isoformat()}

# 收集器配置
collector:
  use_real_exchanges: false  # 是否使用真实交易所 (true: 真实, false: 模拟)
  log_level: "{config.collector.log_level}"
  http_port: {config.collector.http_port}
  metrics_port: {config.collector.metrics_port}
  max_reconnect_attempts: {config.collector.max_reconnect_attempts}
  reconnect_delay: {config.collector.reconnect_delay}
  max_concurrent_connections: {config.collector.max_concurrent_connections}
  message_buffer_size: {config.collector.message_buffer_size}

# NATS配置
nats:
  url: "{config.nats.url}"
  client_name: "{config.nats.client_name}"
  streams:
    MARKET_DATA:
      name: "MARKET_DATA"
      subjects: ["market.>"]
      retention: "limits"
      max_msgs: 1000000
      max_bytes: 1073741824  # 1GB
      max_age: 86400  # 24小时
      max_consumers: 10
      replicas: 1

# 代理配置
proxy:
  enabled: false
  http_proxy: ""
  https_proxy: ""
  no_proxy: ""

# 交易所配置文件列表
exchanges:
  configs:
    - "exchanges/binance_spot.yaml"

# 环境配置
environment: "development"
debug: false
"""
        
        # 写入配置文件
        with open(output, 'w', encoding='utf-8') as f:
            f.write(config_content)
        
        logger.info("默认配置文件已生成", output_path=str(output))
        
        # 生成示例交易所配置
        exchanges_dir = output.parent / 'exchanges'
        exchanges_dir.mkdir(exist_ok=True)
        
        # Binance现货配置示例
        binance_config = exchanges_dir / 'binance_spot.yaml'
        binance_content = f"""# Binance 现货交易所配置
# 生成时间: {datetime.now(timezone.utc).isoformat()}

exchange: "binance"
market_type: "spot"
enabled: true

# API配置
base_url: "https://api.binance.com"
ws_url: "wss://stream.binance.com:9443/ws"
api_key: ""  # 从环境变量 BINANCE_SPOT_API_KEY 读取
api_secret: ""  # 从环境变量 BINANCE_SPOT_API_SECRET 读取

# 数据类型
data_types:
  - "trade"
  - "orderbook"
  - "ticker"

# 监听的交易对
symbols:
  - "BTCUSDT"
  - "ETHUSDT"
  - "ADAUSDT"

# 速率限制
max_requests_per_minute: 1200

# WebSocket配置
ping_interval: 30
reconnect_attempts: 5
reconnect_delay: 5

# 订单簿配置
snapshot_interval: 10
depth_limit: 20
"""
        
        with open(binance_config, 'w', encoding='utf-8') as f:
            f.write(binance_content)
        
        logger.info("示例交易所配置已生成", exchange_config=str(binance_config))
        
        # 生成.env示例文件
        env_file = output.parent / '.env.example'
        env_content = f"""# MarketPrism Python Collector 环境变量配置
# 复制为 .env 文件并填入实际值

# 基础配置
ENVIRONMENT=development
DEBUG=false
LOG_LEVEL=INFO

# NATS配置
NATS_URL=nats://localhost:4222

# HTTP服务配置
HTTP_PORT=8080

# 代理配置 (可选)
# HTTP_PROXY=http://proxy.example.com:8080
# HTTPS_PROXY=https://proxy.example.com:8080
# NO_PROXY=localhost,127.0.0.1

# Binance API密钥 (可选，用于获取实时数据)
# BINANCE_SPOT_API_KEY=your_api_key_here
# BINANCE_SPOT_API_SECRET=your_api_secret_here

# OKX API密钥 (可选)
# OKX_SPOT_API_KEY=your_api_key_here
# OKX_SPOT_API_SECRET=your_api_secret_here
# OKX_SPOT_PASSPHRASE=your_passphrase_here

# Deribit API密钥 (可选)
# DERIBIT_FUTURES_API_KEY=your_api_key_here
# DERIBIT_FUTURES_API_SECRET=your_api_secret_here
"""
        
        with open(env_file, 'w', encoding='utf-8') as f:
            f.write(env_content)
        
        logger.info("环境变量示例文件已生成", env_file=str(env_file))
        
        click.echo(f"""
配置文件初始化完成！

生成的文件:
  主配置: {output}
  交易所配置: {binance_config}
  环境变量示例: {env_file}

下一步操作:
  1. 复制 {env_file} 为 .env 并填入API密钥
  2. 根据需要修改配置文件
  3. 运行: python -m marketprism_collector run -c {output}
""")
        
    except Exception as e:
        logger.error("生成配置文件失败", exc_info=True)
        sys.exit(1)


@cli.command()
@click.option(
    '--config', '-c',
    type=click.Path(exists=True, path_type=Path),
    help='配置文件路径'
)
def validate(config: Path):
    """验证配置文件"""
    
    setup_logging()
    logger = structlog.get_logger(__name__)
    
    try:
        if config:
            logger.info("验证配置文件", config_path=str(config))
            app_config = Config.load_from_file(str(config))
        else:
            logger.info("验证默认配置")
            app_config = create_default_config()
        
        # 验证配置
        logger.info("配置验证成功")
        
        click.echo("配置文件验证通过！")
        click.echo(f"启用的交易所数量: {len(app_config.get_enabled_exchanges())}")
        
        for exchange in app_config.get_enabled_exchanges():
            click.echo(f"  - {exchange.exchange.value} ({exchange.market_type.value})")
        
    except Exception as e:
        logger.error("配置验证失败", exc_info=True)
        click.echo(f"配置验证失败: {e}")
        sys.exit(1)


@cli.command()
def version():
    """显示版本信息"""
    click.echo(f"""MarketPrism Python Collector
版本: 1.0.0
Python: {sys.version}
平台: {sys.platform}
""")


if __name__ == '__main__':
    cli() 