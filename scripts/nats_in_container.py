import asyncio, json, time
from nats.aio.client import Client as NATS

async def main():
    nc = NATS()
    await nc.connect(servers=["nats://localhost:4222"], name="in-container-subscriber")
    js = nc.jetstream()
    sub = await js.subscribe('trade.binance_spot.spot.*')
    start = time.time()
    received = 0
    try:
        while time.time() - start < 15:
            try:
                msg = await sub.next_msg(timeout=1)
            except Exception:
                continue
            received += 1
    finally:
        await sub.unsubscribe()
        await nc.drain()
    print(f"BINANCE_SPOT_TRADES_15S {received}")

if __name__ == '__main__':
    asyncio.run(main())

