#!/usr/bin/env python3
"""
NATS Core vs JetStream 端到端延迟对比小工具（A/B）
- 订阅 Core NATS: <core_prefix>.<subject>
- 订阅 JetStream: <subject>
- 从消息 JSON 中读取 timestamp/trade_time，计算 now - ts 的延迟（毫秒）
- 每分钟输出一次分位数统计，结束时输出总览

用法示例：
  source .venv/bin/activate && \
  python scripts/ab_latency_compare.py \
    --nats nats://localhost:4222 \
    --subject trade.binance_spot.spot.BTCUSDT \
    --core-prefix core \
    --duration-min 10
"""
import asyncio
import json
import argparse
import statistics
from datetime import datetime, timezone

try:
    import nats
except Exception as e:
    raise SystemExit(f"nats 包未安装: {e}")


def parse_iso_or_ms(v):
    if v is None:
        return None
    if isinstance(v, (int, float)):
        # 认为是毫秒时间戳
        try:
            return datetime.fromtimestamp(float(v) / 1000.0, tz=timezone.utc)
        except Exception:
            return None
    if isinstance(v, str):
        t = v.replace('Z', '').replace('T', ' ')
        if '+' in t:
            t = t.split('+')[0]
        # 填充毫秒
        if '.' in t:
            head, frac = t.split('.', 1)
            frac = ''.join(ch for ch in frac if ch.isdigit())
            frac = (frac + '000')[:3]
            t = f"{head}.{frac}"
        else:
            t = f"{t}.000"
        try:
            return datetime.strptime(t, '%Y-%m-%d %H:%M:%S.%f').replace(tzinfo=timezone.utc)
        except Exception:
            return None
    return None


class WindowStats:
    def __init__(self):
        self.core_lat = []
        self.js_lat = []

    def add_core(self, ms):
        self.core_lat.append(ms)

    def add_js(self, ms):
        self.js_lat.append(ms)

    @staticmethod
    def _quantiles(vals):
        if not vals:
            return None
        vals = sorted(vals)
        def q(p):
            k = max(0, min(len(vals)-1, int(round(p*(len(vals)-1)))))
            return vals[k]
        return {
            'p50': q(0.5),
            'p90': q(0.9),
            'p95': q(0.95),
            'p99': q(0.99),
            'count': len(vals)
        }

    def snapshot(self):
        return {
            'core': self._quantiles(self.core_lat) or {'count': 0},
            'jetstream': self._quantiles(self.js_lat) or {'count': 0},
        }


async def run(nats_url, subject, core_prefix, duration_min, window_sec, jsonl_path=None, warmup_sec=0):
    nc = await nats.connect(servers=[nats_url])
    js = nc.jetstream()

    core_subject = f"{core_prefix}.{subject}" if core_prefix else subject

    win = WindowStats()
    total = WindowStats()
    stop = asyncio.Event()
    f_jsonl = open(jsonl_path, 'a') if jsonl_path else None

    def extract_ts_ms(payload):
        ts = payload.get('trade_time') or payload.get('timestamp')
        dt = parse_iso_or_ms(ts)
        if not dt:
            return None
        now = datetime.now(timezone.utc)
        ms = (now - dt).total_seconds() * 1000.0
        return ms

    async def handle_core(msg):
        try:
            payload = json.loads(msg.data.decode('utf-8'))
        except Exception:
            return
        ms = extract_ts_ms(payload)
        if ms is not None:
            win.add_core(ms)
            total.add_core(ms)

    async def handle_js(msg):
        try:
            payload = json.loads(msg.data.decode('utf-8'))
        except Exception:
            await msg.ack()
            return
        ms = extract_ts_ms(payload)
        if ms is not None:
            win.add_js(ms)
            total.add_js(ms)
        await msg.ack()

    # 订阅 Core（推送）
    await nc.subscribe(core_subject, cb=handle_core)

    # 订阅 JetStream（推送 + ack，优化：deliver_policy=last避免历史积压）
    from nats.js.api import ConsumerConfig
    consumer_config = ConsumerConfig(deliver_policy="last")
    sub = await js.subscribe(subject, durable=f"abtest_{int(datetime.now().timestamp())}", manual_ack=True, config=consumer_config)
    asyncio.create_task(_drain_js(sub, handle_js))

    # 预热期（如果设置）
    if warmup_sec > 0:
        print(f"🔥 预热 {warmup_sec} 秒，预热期不记录统计...")
        await asyncio.sleep(warmup_sec)
        win = WindowStats()  # 清空预热期数据
        print("✅ 预热完成，开始正式统计")

    # 定时窗口输出
    async def ticker():
        nonlocal win
        total_sec = int(duration_min * 60)
        windows = max(1, int(total_sec // int(window_sec)))
        for _ in range(windows):
            await asyncio.sleep(int(window_sec))
            snap = win.snapshot()
            now_iso = datetime.now(timezone.utc).isoformat()
            print(f"[{int(window_sec)}s] core={snap['core']} js={snap['jetstream']}")
            if f_jsonl:
                import json as _json
                f_jsonl.write(_json.dumps({
                    'ts': now_iso,
                    'subject': subject,
                    'window_sec': int(window_sec),
                    'core': snap['core'],
                    'jetstream': snap['jetstream']
                }, ensure_ascii=False) + "\n")
                f_jsonl.flush()
            win = WindowStats()
        stop.set()

    await ticker()
    await stop.wait()

    # 总览
    print("=== FINAL ===")
    print(total.snapshot())

    await nc.drain()


async def _drain_js(sub, cb):
    async for msg in sub.messages:
        await cb(msg)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--nats', dest='nats_url', default='nats://localhost:4222')
    ap.add_argument('--subject', required=True, help='如 trade.binance_spot.spot.BTCUSDT')
    ap.add_argument('--core-prefix', default='core')
    ap.add_argument('--duration-min', type=int, default=10)
    ap.add_argument('--window-sec', type=int, default=60)
    ap.add_argument('--jsonl', dest='jsonl_path', default=None)
    ap.add_argument('--warmup-sec', type=int, default=0, help='预热秒数，预热期不记录统计（默认0）')
    args = ap.parse_args()
    asyncio.run(run(args.nats_url, args.subject, args.core_prefix, args.duration_min, args.window_sec, args.jsonl_path, args.warmup_sec))


if __name__ == '__main__':
    main()

