#!/usr/bin/env python3
"""
Synthetic publisher for A/B latency test using NATSPublisher with mirror_to_core=True.
- Publishes JSON messages to JetStream (primary) and mirrors to Core NATS (optional) via NATSPublisher
- Subject format: <data_type>.<exchange>.<market_type>.<symbol>

Example:
  source .venv/bin/activate && \
  python scripts/synthetic_core_mirror_publisher.py \
    --nats nats://localhost:4222 \
    --subject trade.binance_spot.spot.BTCUSDT \
    --rate-hz 10 --duration-min 10
"""
import asyncio
import argparse
import sys
import pathlib
from datetime import datetime, timezone

# Ensure collector package on path
ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'services' / 'data-collector'))
from collector.nats_publisher import NATSPublisher, NATSConfig


async def run(nats_url, subject, rate_hz, duration_min):
    cfg = NATSConfig(servers=[nats_url])
    cfg.mirror_to_core = True
    cfg.core_subject_prefix = 'core'
    pub = NATSPublisher(cfg)
    ok = await pub.connect()
    if not ok:
        raise SystemExit('NATS connect failed')

    parts = subject.split('.')
    if len(parts) < 4:
        raise SystemExit('subject should look like trade.binance_spot.spot.BTCUSDT')
    data_type, exchange, market_type, symbol = parts[0], parts[1], parts[2], parts[3]

    period = 1.0 / float(rate_hz)
    end = asyncio.get_event_loop().time() + duration_min * 60
    count = 0

    while asyncio.get_event_loop().time() < end:
        ts = datetime.now(timezone.utc).isoformat() + 'Z'
        msg = {
            'exchange': exchange,
            'market_type': market_type,
            'symbol': symbol,
            'data_type': data_type,
            'timestamp': ts,
            'publisher': 'synthetic-ab-test'
        }
        if data_type == 'trade':
            msg['trade_time'] = ts
            msg['price'] = 123.45
            msg['quantity'] = 0.01
            msg['side'] = 'buy'
        await pub.publish_data(data_type, exchange, market_type, symbol, msg)
        count += 1
        await asyncio.sleep(period)

    await pub.close()
    print(f'done, sent={count}')


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--nats', dest='nats_url', default='nats://localhost:4222')
    ap.add_argument('--subject', required=True)
    ap.add_argument('--rate-hz', type=float, default=10.0)
    ap.add_argument('--duration-min', type=int, default=10)
    args = ap.parse_args()
    asyncio.run(run(args.nats_url, args.subject, args.rate_hz, args.duration_min))


if __name__ == '__main__':
    main()

