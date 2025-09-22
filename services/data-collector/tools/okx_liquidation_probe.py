#!/usr/bin/env python3
# -*- coding: utf-8 -*-
import asyncio
import json
import os
import signal
import sys
import time
from typing import List

import websockets

WS_URL = os.getenv('OKX_WS_URL', 'wss://ws.okx.com:8443/ws/v5/public')
TARGETS: List[str] = os.getenv('OKX_LIQ_TARGETS', 'BTC-USDT-SWAP,ETH-USDT-SWAP').split(',')
RUN_SECONDS = int(os.getenv('RUN_SECONDS', '90'))
SUB_MODE = os.getenv('SUB_MODE', 'instId')  # 'instId' or 'uly'

async def probe():
    print(f"Connecting to {WS_URL} for liquidation-orders ... mode={SUB_MODE} targets={TARGETS}")
    async with websockets.connect(WS_URL, ping_interval=None, ping_timeout=None, close_timeout=10) as ws:
        # subscribe
        if SUB_MODE == 'uly':
            # accept BTC-USDT, ETH-USDT as underlying
            sub_args = [{"channel": "liquidation-orders", "instType": "SWAP", "uly": inst.strip()} for inst in TARGETS if inst.strip()]
        else:
            # default: instId precise
            sub_args = [{"channel": "liquidation-orders", "instType": "SWAP", "instId": inst.strip()} for inst in TARGETS if inst.strip()]
        sub_msg = {"op": "subscribe", "args": sub_args}
        await ws.send(json.dumps(sub_msg))
        print("-> sent subscribe:", sub_msg)

        start = time.time()
        last_ping = start
        recv_count = 0
        sample = None
        while True:
            # send ping every 20s to satisfy OKX 30s write requirement
            now = time.time()
            if now - last_ping >= 20:
                await ws.send('ping')
                last_ping = now
            # non-blocking read with timeout
            try:
                msg = await asyncio.wait_for(ws.recv(), timeout=2.0)
            except asyncio.TimeoutError:
                if now - start > RUN_SECONDS:
                    break
                continue

            try:
                data = json.loads(msg) if isinstance(msg, str) else msg
            except Exception:
                print("<-- non-JSON message:", repr(msg))
                continue

            # ignore subscribe/pong events
            if isinstance(data, dict) and data.get('event') in ('subscribe', 'pong'):
                print("<-- event:", data)
                continue

            # liquidation data shape: { arg: {...}, data: [ {...} ] }
            if isinstance(data, dict) and 'data' in data:
                rows = data.get('data') or []
                recv_count += len(rows)
                if sample is None and rows:
                    sample = rows[0]
                # concise print
                if rows:
                    first = rows[0]
                    print(f"<-- data: instId={first.get('instId')} side={first.get('side')} sz={first.get('sz')} bkPx={first.get('bkPx')} cTime={first.get('cTime')}")
            if time.time() - start > RUN_SECONDS:
                break

        print(f"Summary: received {recv_count} liquidation rows in {RUN_SECONDS}s")
        if sample:
            print("Sample row:", json.dumps(sample, ensure_ascii=False))

if __name__ == '__main__':
    try:
        asyncio.run(probe())
    except KeyboardInterrupt:
        pass

