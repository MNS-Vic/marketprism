#!/usr/bin/env python3
# Phase 2 migration verification helper
# - Publishes sample messages to JetStream
# - Samples consumer metrics
# - Queries ClickHouse sample counts
# - Writes a report to logs/phase2_validation_report.txt

import os
import sys
import json
import time
from datetime import datetime
from urllib.request import urlopen, Request
from urllib.error import URLError, HTTPError

REPORT_PATH = os.path.join('logs', 'phase2_validation_report.txt')
NATS_URL = os.getenv('MARKETPRISM_NATS_URL', 'nats://localhost:4222')
CLICKHOUSE_HTTP = os.getenv('CLICKHOUSE_HTTP', 'http://localhost:8123')
STREAM = 'MARKET_DATA'
DURABLES = [
    'simple_hot_storage_realtime_orderbook',
    'simple_hot_storage_realtime_trade',
    'simple_hot_storage_realtime_liquidation',
]


def write_line(f, line):
    sys.stdout.write(line + "\n")
    f.write(line + "\n")


def ch_query(sql: str) -> str:
    try:
        data = sql.encode('utf-8')
        req = Request(CLICKHOUSE_HTTP, data=data)
        with urlopen(req, timeout=3) as resp:
            body = resp.read().decode('utf-8', errors='ignore')
            return body.strip()
    except (URLError, HTTPError) as e:
        return f"ERROR: {e}"
    except Exception as e:
        return f"ERROR: {e}"


def main():
    os.makedirs('logs', exist_ok=True)
    with open(REPORT_PATH, 'w', encoding='utf-8') as f:
        write_line(f, f"=== Phase 2 验证报告 @ {datetime.utcnow().isoformat()}Z ===")
        write_line(f, f"NATS_URL={NATS_URL}")
        write_line(f, f"CLICKHOUSE_HTTP={CLICKHOUSE_HTTP}")

        # 1) Connect NATS and publish test messages
        try:
            import asyncio
            import nats
        except Exception as e:
            write_line(f, f"✗ Python依赖缺失: {e}")
            return 0

        async def nats_work():
            try:
                nc = await nats.connect(NATS_URL)
            except Exception as e:
                write_line(f, f"✗ 无法连接NATS: {e}")
                return False
            js = nc.jetstream()
            # publish 5 test trades
            subject = 'trade.binance.spot.BTCUSDT'
            ok = 0
            for i in range(5):
                msg = {
                    'exchange': 'binance', 'market_type': 'spot', 'symbol': 'BTCUSDT',
                    'price': 27000 + i, 'size': 0.001, 'ts': int(time.time()*1000)
                }
                try:
                    ack = await js.publish(subject, json.dumps(msg).encode('utf-8'))
                    ok += 1
                except Exception as e:
                    write_line(f, f"发布失败: {e}")
            write_line(f, f"✓ 已发布测试消息 {ok}/5 到 {subject}")

            # sample consumer infos
            write_line(f, "\n--- JetStream消费者指标采样 ---")
            for d in DURABLES:
                try:
                    info = await js.consumer_info(STREAM, d)
                    write_line(f, json.dumps({
                        'durable': d,
                        'num_pending': getattr(info, 'num_pending', None),
                        'num_waiting': getattr(info, 'num_waiting', None),
                    }, ensure_ascii=False))
                except Exception as e:
                    write_line(f, json.dumps({'durable': d, 'error': str(e)}, ensure_ascii=False))
            await nc.close()
            return True

        try:
            asyncio.run(nats_work())
        except Exception as e:
            write_line(f, f"✗ 运行NATS任务失败: {e}")

        # 2) ClickHouse sample counts
        write_line(f, "\n--- ClickHouse 样本计数 ---")
        for tbl in ['trades', 'orderbooks', 'liquidations']:
            res = ch_query(f'SELECT count() FROM marketprism_hot.{tbl}')
            write_line(f, f"{tbl}: {res}")

        write_line(f, "\n=== 结束 ===")
    print(f"报告已生成: {REPORT_PATH}")
    return 0


if __name__ == '__main__':
    sys.exit(main())

