#!/usr/bin/env python3
"""
MarketPrism Data Collector - 统一入口

说明：
- 本文件是 data-collector 服务的唯一入口（main.py）
- 实际实现位于 unified_collector_main.py（作为模块保留，不再作为入口）
- 保持行为不变：透传原有常用参数
"""
import asyncio
import argparse
import os
from pathlib import Path

# 直接复用已有实现
try:
    from .unified_collector_main import UnifiedDataCollector  # package context
except ImportError:
    from unified_collector_main import UnifiedDataCollector  # script context


def parse_args():
    parser = argparse.ArgumentParser(description="MarketPrism Unified Data Collector")
    parser.add_argument("--mode", "-m", choices=["collector", "service", "test"], default="collector",
                        help="运行模式：collector（默认）/ service / test")
    parser.add_argument("--config", "-c", type=str, default=str(Path(__file__).resolve().parent / "config" / "collector" / "unified_data_collection.yaml"),
                        help="配置文件路径 (YAML)")
    parser.add_argument("--exchange", "-e", type=str, default=None,
                        help="仅运行指定交易所（例如：binance_spot / binance_derivatives / okx_spot / okx_derivatives / deribit_derivatives）")
    parser.add_argument("--log-level", "-l", choices=["DEBUG", "INFO", "WARNING", "ERROR"], default=os.getenv("LOG_LEVEL", "INFO"))
    return parser.parse_args()


async def _run(args):
    # 统一环境变量，可被实现读取
    os.environ.setdefault("LOG_LEVEL", args.log_level)
    collector = UnifiedDataCollector(config_path=args.config, mode=args.mode, target_exchange=args.exchange)
    ok = await collector.start()
    if not ok:
        raise SystemExit(1)


def main():
    args = parse_args()
    try:
        asyncio.run(_run(args))
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()

