#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
MarketPrism 端到端（Collector -> NATS JetStream -> Storage -> ClickHouse）只读验证脚本
- 使用虚拟环境运行：source .venv/bin/activate && python scripts/e2e_validate.py
- 不发布测试数据，不影响生产数据
- 生成详细报告：logs/e2e_report.txt
"""

import os
import sys
import json
import asyncio
from datetime import datetime, timezone, timedelta
from urllib.parse import quote

import aiohttp
import nats

REPO_ROOT = os.path.abspath(os.path.dirname(os.path.dirname(__file__)))
LOG_DIR = os.path.join(REPO_ROOT, 'logs')
REPORT = os.path.join(LOG_DIR, 'e2e_report.txt')

NATS_URL = os.getenv('MARKETPRISM_NATS_URL', 'nats://localhost:4222')
CLICKHOUSE_HTTP = os.getenv('CLICKHOUSE_HTTP', 'http://localhost:8123')

# 尝试多个 Collector 端口（不同版本存在差异）
COLLECTOR_HEALTH_PORTS = [8087, 8086, 8080]
COLLECTOR_METRICS_PORTS = [9093, 8081]

# Storage 指标端点（优先采用生产标准端口 8085，其次兼容历史/容器端口）
STORAGE_METRICS_CANDIDATES = [
    'http://localhost:8085/metrics',  # 生产标准（HOT_STORAGE_HTTP_PORT=8085）
    'http://localhost:18080/metrics', # Docker 映射端口（可选）
    'http://localhost:8081/metrics',  # 本地开发进程（历史）
    'http://localhost:8080/metrics',  # 容器内或旧本机调试
]

STREAM = 'MARKET_DATA'
DURABLES = [
    'simple_hot_storage_realtime_trade',
    'simple_hot_storage_realtime_orderbook',
    'simple_hot_storage_realtime_liquidation',
]

# ClickHouse 表与校验逻辑
TABLES = {
    'trades': {
        'dup_key': ('exchange','symbol','trade_id'),
        'time_col': 'timestamp',
        'extra_cols': ['trade_time','price','quantity','side','created_at'],
        'latency_col': 'created_at',
    },
    'orderbooks': {
        'dup_key': ('exchange','symbol','last_update_id','timestamp'),
        'time_col': 'timestamp',
        'extra_cols': ['bids','asks','bids_count','asks_count','best_bid_price','best_ask_price','created_at'],
        'latency_col': 'created_at',
    },
    'liquidations': {
        'dup_key': ('exchange','symbol','timestamp','price','quantity','side'),
        'time_col': 'timestamp',
        'extra_cols': ['created_at'],
        'latency_col': 'created_at',
    },
}

SYMBOL_SAMPLES = [
    ('binance','spot','BTCUSDT'),
    ('okx','futures','BTC-USDT-SWAP'),
    ('deribit','perp','BTC-PERPETUAL'),
]


def write_line(f, s: str):
    print(s)
    f.write(s + "\n")
    f.flush()


async def http_get_text(session: aiohttp.ClientSession, url: str, timeout: int = 8) -> str:
    try:
        async with session.get(url, timeout=timeout) as resp:
            return await resp.text()
    except Exception as e:
        return f"ERROR: {e}"


async def http_get_json(session: aiohttp.ClientSession, url: str, timeout: int = 8):
    try:
        async with session.get(url, timeout=timeout) as resp:
            return await resp.json(content_type=None)
    except Exception as e:
        return {"error": str(e)}


async def ch_query(session: aiohttp.ClientSession, sql: str) -> str:
    try:
        url = f"{CLICKHOUSE_HTTP}/?query={quote(sql)}"
        async with session.get(url, timeout=10) as resp:
            return (await resp.text()).strip()
    except Exception as e:
        return f"ERROR: {e}"


async def check_collector(f):
    write_line(f, "\n=== 1) Collector 健康/指标 ===")
    async with aiohttp.ClientSession() as session:
        health = None
        for p in COLLECTOR_HEALTH_PORTS:
            data = await http_get_json(session, f"http://localhost:{p}/health")
            if data and isinstance(data, dict) and 'status' in data:
                health = (p, data)
                break
        if health:
            write_line(f, f"健康检查端口: {health[0]} status={health[1].get('status')}")
        else:
            write_line(f, "✗ Collector 健康端点不可用(8086/8080)")

        metrics_found = False
        for p in COLLECTOR_METRICS_PORTS:
            txt = await http_get_text(session, f"http://localhost:{p}/metrics")
            if txt and 'process_cpu_seconds_total' in txt:
                write_line(f, f"Metrics 端口: {p} (Prometheus 格式)")
                # 粗略抽样关键指标
                for key in [
                    'collector_nats_publish_total',
                    'collector_ws_messages_received_total',
                    'collector_errors_total']:
                    for line in txt.splitlines():
                        if line.startswith(key):
                            write_line(f, f"  {line}")
                metrics_found = True
                break
        if not metrics_found:
            write_line(f, "⚠️ Collector 指标端点不可用(9093/8081) 或未暴露关键指标")


async def check_nats_and_consumers(f):
    write_line(f, "\n=== 2) NATS JetStream 流/消费者 ===")
    nc = await nats.connect(NATS_URL)
    jsm = nc.jsm()
    js = nc.jetstream()

    try:
        sinfo = await jsm.stream_info(STREAM)
        state = getattr(sinfo, 'state', None)
        write_line(f, f"Stream={STREAM} 存在: ✅  messages={getattr(state,'messages', 'N/A')}\n  bytes={getattr(state,'bytes','N/A')} subjects=orderbook.>,trade.>,liquidation.>")
    except Exception as e:
        write_line(f, f"✗ 获取 Stream 失败: {e}")

    for d in DURABLES:
        try:
            info = await js.consumer_info(STREAM, d)
            cfg = info.config
            write_line(f, f"Consumer {d}: deliver_policy={cfg.deliver_policy}, ack_policy={cfg.ack_policy}, ack_wait={cfg.ack_wait}s, max_ack_pending={cfg.max_ack_pending}")
            write_line(f, f"  pending={info.num_pending}, ack_pending={info.num_ack_pending}, redelivered={info.num_redelivered}")
        except Exception as e:
            write_line(f, f"✗ Consumer {d} 不可用: {e}")

    await nc.close()


async def check_storage_metrics(f):
    write_line(f, "\n=== 3) Storage（simple_hot_storage）指标 ===")
    async with aiohttp.ClientSession() as session:
        txt = None
        used_url = None
        last_err = None
        for url in STORAGE_METRICS_CANDIDATES:
            t = await http_get_text(session, url)
            if t and not t.startswith('ERROR'):
                # 存储服务未必暴露 process_* 指标；允许 hot_storage_* 作为识别信号
                if ('hot_storage_messages_processed_total' in t) or ('process_cpu_seconds_total' in t):
                    txt = t
                    used_url = url
                    break
            last_err = t
        if not txt:
            write_line(f, f"✗ 无法获取 Storage 指标: {last_err}")
            return
        # 同时尝试读取健康状态
        health = await http_get_text(session, used_url.replace('/metrics', '/health'))
        write_line(f, f"Metrics URL: {used_url}")
        write_line(f, f"Health: {health}")
        # 抽取关键指标
        keys = [
            'hot_storage_messages_processed_total',
            'hot_storage_messages_failed_total',
            'hot_storage_batch_inserts_total',
            'hot_storage_batch_size_avg',
            'hot_storage_error_rate_percent'
        ]
        for k in keys:
            for line in txt.splitlines():
                if line.startswith(k):
                    write_line(f, f"  {line}")


async def check_clickhouse(f):
    write_line(f, "\n=== 4) ClickHouse 数据完整性/质量 ===")
    async with aiohttp.ClientSession() as session:
        # 4.1 表结构检查
        write_line(f, "-- 表结构检查 --")
        for tbl, meta in TABLES.items():
            cols = await ch_query(session, f"SELECT name,type FROM system.columns WHERE database='marketprism_hot' AND table='{tbl}' ORDER BY name")
            write_line(f, f"[{tbl}] 列:\n{cols}")

        # 4.2 数据量与最近写入
        write_line(f, "\n-- 数据量与最近写入 --")
        for tbl, meta in TABLES.items():
            total = await ch_query(session, f"SELECT count() FROM marketprism_hot.{tbl}")
            recent5m = await ch_query(session, f"SELECT count() FROM marketprism_hot.{tbl} WHERE {meta['time_col']} > now() - INTERVAL 5 MINUTE")
            max_ts = await ch_query(session, f"SELECT max({meta['time_col']}) FROM marketprism_hot.{tbl}")
            write_line(f, f"[{tbl}] total={total} recent_5m={recent5m} max_ts={max_ts}")

        # 4.3 重复数据检查（粗略）
        write_line(f, "\n-- 重复数据检查 --")
        for tbl, meta in TABLES.items():
            k = ','.join(meta['dup_key'])
            dup = await ch_query(session, f"SELECT count() - uniqExact({k}) FROM marketprism_hot.{tbl} WHERE {meta['time_col']} > now() - INTERVAL 1 DAY")
            write_line(f, f"[{tbl}] 最近1天重复条数≈ {dup}")

        # 4.4 关键字段校验（价格、数量为正等）
        write_line(f, "\n-- 关键字段校验 --")
        checks = {
            'trades': "SELECT sum(price<=0)+sum(quantity<=0) FROM marketprism_hot.trades WHERE timestamp > now()-INTERVAL 1 DAY",
            'orderbooks': "SELECT sum(best_bid_price<=0)+sum(best_ask_price<=0) FROM marketprism_hot.orderbooks WHERE timestamp > now()-INTERVAL 1 DAY",
            'liquidations': "SELECT sum(price<=0)+sum(quantity<=0) FROM marketprism_hot.liquidations WHERE timestamp > now()-INTERVAL 7 DAY",
        }
        for tbl, sql in checks.items():
            bad = await ch_query(session, sql)
            write_line(f, f"[{tbl}] 非法数值条数≈ {bad}")

        # 4.5 实时性（摄入延迟）：avg(created_at - event_ts)
        write_line(f, "\n-- 实时性（摄入延迟） --")
        for tbl, meta in TABLES.items():
            lat = await ch_query(session, (
                f"SELECT avg(toUnixTimestamp64Milli(toDateTime64({meta['latency_col']}, 3)) - "
                f"toUnixTimestamp64Milli(toDateTime64({meta['time_col']}, 3))) "
                f"FROM marketprism_hot.{tbl} "
                f"WHERE {meta['time_col']} > now() - INTERVAL 10 MINUTE"
            ))
            write_line(f, f"[{tbl}] 平均摄入延迟(ms)≈ {lat}")

        # 4.6 时间戳连续性（抽样符号）
        write_line(f, "\n-- 时间戳连续性（抽样） --")
        # 动态选择最近10分钟数据量Top3的 (exchange, symbol) 进行抽样
        for tbl, meta in TABLES.items():
            top_pairs = await ch_query(session, (
                f"SELECT exchange, symbol, count() AS c FROM marketprism_hot.{tbl} "
                f"WHERE {meta['time_col']} > now() - INTERVAL 10 MINUTE "
                f"GROUP BY exchange, symbol ORDER BY c DESC LIMIT 3"
            ))
            write_line(f, f"[{tbl}] 最近10m Top3 exchange/symbol: \n{top_pairs}")
            if top_pairs and not top_pairs.startswith('ERROR') and top_pairs.strip():
                for line in top_pairs.splitlines():
                    parts = line.split('\t')
                    if len(parts) >= 2:
                        exch, sym = parts[0], parts[1]
                        cnt = await ch_query(session, f"SELECT count() FROM marketprism_hot.{tbl} WHERE exchange='{exch}' AND symbol='{sym}' AND {meta['time_col']} > now() - INTERVAL 5 MINUTE")
                        write_line(f, f"  - {exch}/{sym} 最近5m 行数: {cnt}")


async def main():
    os.makedirs(LOG_DIR, exist_ok=True)
    with open(REPORT, 'w', encoding='utf-8') as f:
        write_line(f, f"=== E2E 数据流验证 @ {datetime.now(timezone.utc).isoformat()} ===")
        write_line(f, f"NATS_URL={NATS_URL}")
        write_line(f, f"CLICKHOUSE_HTTP={CLICKHOUSE_HTTP}")

        # 1) Collector 健康/指标
        await check_collector(f)

        # 2) NATS/Consumers
        await check_nats_and_consumers(f)

        # 3) Storage 指标
        await check_storage_metrics(f)

        # 4) ClickHouse 校验
        await check_clickhouse(f)

        write_line(f, "\n=== E2E 验证结束 ===")

if __name__ == '__main__':
    asyncio.run(main())

