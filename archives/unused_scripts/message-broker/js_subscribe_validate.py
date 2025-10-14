#!/usr/bin/env python3
import asyncio
import json
import os
import re
import signal
import sys
from typing import List

import nats
from nats.js.api import ConsumerConfig

DEFAULT_SUBJECTS = [
    'orderbook.>',
    'trade.>',
    'funding_rate.>',
    'open_interest.>',
    'liquidation.>',
    'volatility_index.>',
    'lsr_top_position.>',
    'lsr_all_account.>',
]

help_text = """
通用 JetStream 订阅验证脚本

用法:
  python services/message-broker/scripts/js_subscribe_validate.py \
      --nats-url nats://127.0.0.1:4222 \
      --stream MARKET_DATA \
      --subjects trade.> open-interest.>

若不指定 subjects，默认订阅全量标准前缀。
按 Ctrl+C 退出。
"""


def parse_args(argv: List[str]):
    import argparse
    p = argparse.ArgumentParser(description='JetStream 订阅验证', epilog=help_text)
    p.add_argument('--nats-url', default=os.getenv('NATS_URL', 'nats://127.0.0.1:4222'))
    p.add_argument('--stream', default=os.getenv('NATS_STREAM', 'MARKET_DATA'))
    p.add_argument('--subjects', nargs='*', default=None)
    p.add_argument('--durable-prefix', default='js-validate-')
    p.add_argument('--json', action='store_true', help='以json原样打印消息体')
    return p.parse_args(argv)


async def run(args):
    nc = await nats.connect(args.nats_url)
    js = nc.jetstream()

    subjects = args.subjects or DEFAULT_SUBJECTS
    counts = {s: 0 for s in subjects}

    async def make_cb(name):
        async def cb(msg):
            counts[name] += 1
            body = msg.data
            out = None
            if args.json:
                try:
                    out = json.dumps(json.loads(body.decode('utf-8')), ensure_ascii=False)
                except Exception:
                    out = body.decode('utf-8', errors='ignore')
            else:
                out = f"{msg.subject} | {len(body)} bytes"
            print(out)
            await msg.ack()
        return cb

    subs = []
    # 将 subject 转换为合法 durable：只能包含 A-Z a-z 0-9 _ -
    def to_durable(s: str) -> str:
        s = re.sub(r"[^A-Za-z0-9_-]", "-", s)
        return (args.durable_prefix + s)[:50]

    for pat in subjects:
        durable = to_durable(pat)
        # 使用 ConsumerConfig 指定 filter_subject，并明确指定流名称
        config = ConsumerConfig(filter_subject=pat, durable_name=durable)
        subs.append(await js.subscribe(pat, stream=args.stream, cb=await make_cb(pat), config=config))

    print('订阅中:')
    for s in subjects:
        print(' -', s)

    stop = asyncio.Event()

    def _handle(*_):
        stop.set()

    loop = asyncio.get_event_loop()
    for sig in (signal.SIGINT, signal.SIGTERM):
        loop.add_signal_handler(sig, _handle)

    await stop.wait()

    await nc.close()
    print('已退出，消息计数:', counts)


def main():
    args = parse_args(sys.argv[1:])
    asyncio.run(run(args))


if __name__ == '__main__':
    main()

