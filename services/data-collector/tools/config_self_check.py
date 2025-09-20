#!/usr/bin/env python3
"""
配置自检脚本：快速确认 data-collector 在当前环境下会使用的配置来源与关键变量。
可在容器或本地执行：
  python services/data-collector/tools/config_self_check.py
"""
import os
from pathlib import Path

PRIORITY = [
    ("CLI(ENTRYPOINT) -> COLLECTOR_CONFIG_PATH", os.getenv("COLLECTOR_CONFIG_PATH")),
    ("ENV -> MARKETPRISM_UNIFIED_DATA_COLLECTION_CONFIG", os.getenv("MARKETPRISM_UNIFIED_DATA_COLLECTION_CONFIG")),
    ("DEFAULT_LOCAL", str(Path(__file__).resolve().parents[1] / 'config' / 'collector' / 'unified_data_collection.yaml')),
    ("DEFAULT_GLOBAL", str(Path(__file__).resolve().parents[3] / 'config' / 'collector' / 'unified_data_collection.yaml')),
]

NATS = os.getenv("NATS_URL") or os.getenv("MARKETPRISM_NATS_SERVERS")

print("=== Config Resolution Self-Check ===")
for name, path in PRIORITY:
    exists = path and Path(path).exists()
    print(f"{name:48s} -> {path}  {'[OK]' if exists else '[MISSING]'}")

print(f"NATS_URL (or MARKETPRISM_NATS_SERVERS): {NATS}")
print("Tip: entrypoint.sh 会按上述优先级解析并传入 --config。主程序也会在启动日志打印选用的来源。")

