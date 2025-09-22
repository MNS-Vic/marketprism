#!/usr/bin/env python3
"""
JetStream Durable Consumer 版本的波动率指数监控器
- 使用 JetStream Pull/Push Durable Consumer 持久消费 volatility-index.* 主题
- 输出每秒统计、各交易所计数等
用法：
  source ../../venv/bin/activate && python services/data-collector/vol_index_monitor_js.py
"""
import asyncio
import json
import os
from collections import defaultdict
from datetime import datetime

import nats
import yaml
from aiohttp import web
from prometheus_client import Counter, Gauge, CONTENT_TYPE_LATEST, generate_latest

STREAM = "MARKET_DATA"
SUBJECT = "volatility_index.>"
DURABLE = "vi_durable_monitor"
CONSUMER_NAME = DURABLE

# Prometheus 指标
VI_MSG_TOTAL = Counter("vi_messages_total", "VI 消息总数", ["exchange"])
VI_LAST_TS = Gauge("vi_last_message_timestamp", "最近一条VI消息的epoch秒")
VI_RATE = Gauge("vi_messages_rate_per_sec", "平均消息速率（按进程运行期累计）")


def _load_metrics_config():
    default_port = 9095
    default_path = "/metrics"
    try:
        cfg_path = os.path.abspath(os.path.join(os.path.dirname(__file__), "config", "collector", "unified_data_collection.yaml"))
        with open(cfg_path, "r", encoding="utf-8") as f:
            cfg = yaml.safe_load(f) or {}
        mon = (cfg.get("monitoring") or {}).get("metrics") or {}
        sysobs = (cfg.get("system") or {}).get("observability") or {}
        enabled = mon.get("enabled", True)
        port = int(mon.get("port", sysobs.get("metrics_port", default_port)))
        path = str(mon.get("path", sysobs.get("metrics_path", default_path)))
        return enabled, port, path
    except Exception:
        return True, default_port, default_path


async def _start_metrics_server(port: int, path: str):
    async def handle_metrics(request):
        data = generate_latest()
        return web.Response(body=data, headers={"Content-Type": CONTENT_TYPE_LATEST})

    app = web.Application()
    app.router.add_get(path, handle_metrics)
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, host="0.0.0.0", port=port)
    await site.start()
    print(f"📈 Prometheus 指标已在 http://localhost:{port}{path} 暴露")


async def main():
    nc = await nats.connect("nats://localhost:4222")
    js = nc.jetstream()

    # 启动 Prometheus 指标 HTTP 服务（从配置读取）
    try:
        enabled, port, path = _load_metrics_config()
        if enabled:
            await _start_metrics_server(port, path)
        else:
            print("ℹ️ 已禁用 Prometheus 指标服务（配置）")
    except Exception as e:
        print(f"⚠️ Prometheus 指标服务启动失败: {e}")

    # 确保流存在（若不存在直接报错以提示先启动broker）
    try:
        await js.stream_info(STREAM)
    except Exception as e:
        print(f"❌ 获取流失败: {e}，请先启动统一NATS并确保包含 {SUBJECT}")
        await nc.close()
        return

    # 创建或获取 durable consumer（基于 subject 过滤）
    # nats-py 将在 subscribe 时自动创建基于 durable 的 consumer（如果不存在）
    sub = await js.subscribe(
        SUBJECT,
        durable=DURABLE,
        stream=STREAM,
        manual_ack=True,
        idle_heartbeat=5_000_000_000,  # 5s
    )

    print("📡 开始JetStream耐久消费: ", SUBJECT)
    print("💡 Ctrl+C 结束\n")

    counts = 0
    per_exchange = defaultdict(int)
    started = datetime.now()

    try:
        while True:
            try:
                msg = await sub.next_msg(timeout=5)
            except Exception:
                # 超时，输出心跳
                print("⏳ 等待中...")
                continue

            data = json.loads(msg.data.decode())
            counts += 1
            # 主题格式: volatility-index.{exchange}.{market_type}.{symbol}
            parts = msg.subject.split('.')
            exchange = parts[1] if len(parts) >= 4 else "unknown"
            per_exchange[exchange] += 1

            # 简要打印每条
            key = data.get('key') or data.get('vol_index') or data.get('data', {}).get('vol_index')
            print(f"[{counts}] {msg.subject} key={key}")

            # Prometheus 指标更新
            VI_MSG_TOTAL.labels(exchange=exchange).inc()
            VI_LAST_TS.set(datetime.now().timestamp())
            elapsed = (datetime.now() - started).total_seconds()
            if elapsed > 0:
                VI_RATE.set(counts / elapsed)

            # 手动确认
            await msg.ack()

            # 每10条输出一次统计
            if counts % 10 == 0:
                elapsed = (datetime.now() - started).total_seconds()
                print("-" * 50)
                print(f"总消息: {counts}, 平均 {counts/elapsed:.2f} msg/s")
                print(f"按交易所: {dict(per_exchange)}")
                print("-" * 50)
    except KeyboardInterrupt:
        print("\n👋 结束消费...")
    finally:
        await nc.close()
        print("🔌 NATS连接已关闭")


if __name__ == "__main__":
    asyncio.run(main())

