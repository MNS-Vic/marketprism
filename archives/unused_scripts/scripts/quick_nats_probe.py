#!/usr/bin/env python3
import asyncio
import json
import signal
import sys
from collections import defaultdict
import nats

SUBJECTS = [
    'orderbook.>', 'trade.>', 'funding_rate.>', 'open_interest.>',
    'liquidation.>', 'volatility_index.>', 'lsr_top_position.>', 'lsr_all_account.>'
]

async def main(duration=15):
    nc = await nats.connect('nats://127.0.0.1:4222')
    counts = defaultdict(int)
    subs = []

    async def mk_cb(key):
        async def cb(msg):
            counts[key] += 1
        return cb

    # 使用核心 NATS 订阅（非 JetStream durable），快速验证是否有实时消息
    for s in SUBJECTS:
        subs.append(await nc.subscribe(s, cb=await mk_cb(s)))

    print(f"✅ quick_nats_probe 订阅已建立，采样 {duration}s ...", flush=True)
    await asyncio.sleep(duration)

    print("\n📊 采样计数：", flush=True)
    for s in SUBJECTS:
        print(f"  {s:22s} -> {counts[s]} 条", flush=True)

    for sub in subs:
        await sub.drain()
    await nc.close()

if __name__ == '__main__':
    dur = 15
    if len(sys.argv) > 1:
        try:
            dur = int(sys.argv[1])
        except Exception:
            pass
    asyncio.run(main(dur))

