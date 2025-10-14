#!/usr/bin/env python3
import argparse
import time
import json
import urllib.request
import urllib.parse
import traceback
import os

JSZ_URL = 'http://localhost:8222/jsz?consumers=true&streams=true'
CH_URL  = 'http://localhost:8123/?query='

def fetch_json(url):
    try:
        with urllib.request.urlopen(url, timeout=5) as r:
            return json.loads(r.read().decode('utf-8', errors='ignore'))
    except Exception:
        return {"error": traceback.format_exc()}

def ch_query(sql):
    try:
        url = CH_URL + urllib.parse.quote(sql)
        with urllib.request.urlopen(url, timeout=8) as r:
            return r.read().decode('utf-8', errors='ignore').strip()
    except Exception:
        return 'ERR:' + traceback.format_exc()


def extract_metrics(js):
    m = {
        'market_data': {'consumers': None, 'trade_pending': None},
        'orderbook_snap': {'consumers': None, 'pending': None, 'ack_pending': None, 'redelivered': None}
    }
    try:
        sd = js['account_details'][0]['stream_detail']
        by_name = {x['name']: x for x in sd}
        md = by_name.get('MARKET_DATA')
        ob = by_name.get('ORDERBOOK_SNAP')
        if md:
            m['market_data']['consumers'] = md['state'].get('consumer_count')
            tp = None
            for c in md.get('consumer_detail', []):
                if c.get('name') == 'simple_hot_storage_realtime_trade':
                    tp = c.get('num_pending')
                    break
            m['market_data']['trade_pending'] = tp
        if ob:
            m['orderbook_snap']['consumers'] = ob['state'].get('consumer_count')
            cd = ob.get('consumer_detail', [])
            if cd:
                c = cd[0]
                m['orderbook_snap']['pending'] = c.get('num_pending')
                m['orderbook_snap']['ack_pending'] = c.get('num_ack_pending')
                m['orderbook_snap']['redelivered'] = c.get('num_redelivered')
    except Exception:
        m['error'] = traceback.format_exc()
    return m


def log_line(path, s):
    with open(path, 'a') as f:
        f.write(s + "\n")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--samples', type=int, default=3)
    ap.add_argument('--interval', type=int, default=420, help='seconds between samples')
    ap.add_argument('--log', default=f"/tmp/marketprism_obs_{int(time.time())}.log")
    args = ap.parse_args()

    log_path = args.log
    os.makedirs(os.path.dirname(log_path), exist_ok=True)

    log_line(log_path, f"OBS_START {time.strftime('%Y-%m-%dT%H:%M:%S%z')}")
    for i in range(args.samples):
        log_line(log_path, f"===== SAMPLE {i+1} @ {time.strftime('%Y-%m-%dT%H:%M:%S%z')} =====")
        js = fetch_json(JSZ_URL)
        m = extract_metrics(js)
        log_line(log_path, "JS_METRICS: " + json.dumps(m, ensure_ascii=False))
        latest = ch_query("SELECT toString(max(timestamp)) as latest_ts, count() FROM marketprism_hot.orderbooks WHERE timestamp > now() - INTERVAL 5 MINUTE")
        log_line(log_path, "CH_ORDERBOOKS_5M: " + latest)
        q = ch_query("SELECT quantilesExact(0.5,0.9,0.95,0.99)(toUInt32(dateDiff('second', timestamp, created_at))) FROM marketprism_hot.orderbooks WHERE timestamp > now() - INTERVAL 5 MINUTE")
        log_line(log_path, "CH_LATENCY_Q: " + q)
        if i < args.samples - 1:
            log_line(log_path, f"SLEEP {args.interval}s...")
            time.sleep(args.interval)
    log_line(log_path, f"OBS_END {time.strftime('%Y-%m-%dT%H:%M:%S%z')}")
    print(log_path)

if __name__ == '__main__':
    main()

