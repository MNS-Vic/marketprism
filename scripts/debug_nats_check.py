import asyncio, json, time
from nats.aio.client import Client as NATS

async def main():
    nc = NATS()
    await nc.connect(servers=["nats://localhost:4222"], name="debug-subscriber")
    js = nc.jetstream()
    msgs = []
    total_msgs = 0
    sub = await js.subscribe('trade.>')
    start = time.time()
    try:
        while time.time() - start < 20:
            try:
                msg = await sub.next_msg(timeout=1)
            except Exception:
                continue
            total_msgs += 1
            try:
                data = json.loads(msg.data.decode())
            except Exception:
                data = {}
            subj = msg.subject
            if subj.startswith('trade.binance_spot.'):
                msgs.append((subj, data.get('symbol'), data.get('trade_id')))
                if len(msgs) % 10 == 0:
                    print(f"[binance_spot trades] count={len(msgs)} last_subj={subj} last_symbol={data.get('symbol')}")
    finally:
        await sub.unsubscribe()
        await nc.drain()
    print(f"Total trade messages in 20s: {total_msgs}")
    print(f"Total binance_spot trades received in 20s: {len(msgs)}")

if __name__ == '__main__':
    asyncio.run(main())

