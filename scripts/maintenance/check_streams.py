#!/usr/bin/env python3
import asyncio
import nats

async def check_streams():
    nc = await nats.connect('nats://localhost:4222')
    js = nc.jetstream()
    streams = await js.streams_info()
    print('现有流:')
    for stream in streams:
        print(f'  - {stream.config.name}: {stream.config.subjects}')
    await nc.close()

if __name__ == "__main__":
    asyncio.run(check_streams()) 