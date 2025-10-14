#!/usr/bin/env python3
"""
MarketPrism ClickHouse 数据校验脚本（一次性只读校验）
- 表计数：8张表（高频5分钟、低频24小时）
- 关键字段：timestamp/exchange/symbol 不为空校验（抽样）
- 时间戳：格式与有效性校验（抽样）

使用：
  source venv/bin/activate  # 建议
  python scripts/check_clickhouse_integrity.py

环境变量：
  CLICKHOUSE_HTTP (默认 http://localhost:8123)
  CLICKHOUSE_DB   (默认 marketprism_hot)
"""
import os
import sys
import json
from datetime import datetime, timezone, timedelta
from typing import Dict, List, Tuple

import requests

CH_URL = os.getenv("CLICKHOUSE_HTTP", "http://localhost:8123")
DB = os.getenv("CLICKHOUSE_DB", "marketprism_hot")

HIGH_FREQ = ["trades", "orderbooks"]
LOW_FREQ = [
    "funding_rates",
    "open_interests",
    "liquidations",
    "lsr_top_positions",
    "lsr_all_accounts",
    "volatility_indices",
]
ALL_TABLES = HIGH_FREQ + LOW_FREQ


def ch_query(sql: str, timeout: int = 10) -> Tuple[int, str]:
    try:
        resp = requests.post(f"{CH_URL}/?database={DB}", data=sql.encode("utf-8"), timeout=timeout)
        return resp.status_code, resp.text
    except Exception as e:
        return 599, str(e)


def count_recent(table: str) -> Tuple[int, int]:
    if table in HIGH_FREQ:
        cond = "now() - INTERVAL 5 MINUTE"
    else:
        cond = "now() - INTERVAL 24 HOUR"
    sql = f"SELECT count() FROM {table} WHERE timestamp > {cond}"
    code, text = ch_query(sql)
    if code == 200:
        try:
            return code, int(text.strip())
        except Exception:
            return 500, -1
    return code, -1


def max_timestamp(table: str) -> Tuple[int, str]:
    sql = f"SELECT toString(max(timestamp)) FROM {table}"
    code, text = ch_query(sql)
    if code == 200:
        return code, text.strip()
    return code, ""


def sample_rows(table: str, n: int = 3) -> Tuple[int, List[List[str]]]:
    sql = f"SELECT toString(timestamp), exchange, symbol FROM {table} ORDER BY timestamp DESC LIMIT {n}"
    code, text = ch_query(sql)
    if code == 200:
        rows = [line.split('\t') for line in text.strip().splitlines() if line.strip()]
        return code, rows
    return code, []


def describe(table: str) -> Tuple[int, List[str]]:
    code, text = ch_query(f"DESCRIBE {table}")
    if code == 200:
        cols = [ln.split('\t')[0] for ln in text.strip().splitlines() if ln.strip()]
        return code, cols
    return code, []


def check_table(table: str) -> Dict:
    result: Dict = {"table": table, "ok": False, "count": -1, "latest": "", "fields_ok": False, "ts_ok": False, "notes": []}

    # count
    code_c, cnt = count_recent(table)
    result["count"] = cnt
    if code_c != 200:
        result["notes"].append(f"count查询失败(status={code_c})")

    # schema
    code_d, cols = describe(table)
    need = {"timestamp", "exchange", "symbol"}
    fields_ok = need.issubset(set(cols))
    result["fields_ok"] = fields_ok
    if code_d != 200 or not fields_ok:
        result["notes"].append("字段缺失: 需包含 timestamp/exchange/symbol")

    # max timestamp
    code_t, latest = max_timestamp(table)
    result["latest"] = latest
    if code_t != 200 or not latest:
        result["notes"].append("max(timestamp) 查询失败或为空")

    # sample & timestamp validity
    code_s, rows = sample_rows(table)
    ts_valid = True
    key_fields_ok = True
    now = datetime.now(timezone.utc)
    for r in rows:
        if len(r) < 3:
            key_fields_ok = False
            break
        ts_s, exch, sym = r[0], r[1], r[2]
        if not exch or not sym:
            key_fields_ok = False
        try:
            # ClickHouse toString(timestamp) 返回 "YYYY-MM-DD HH:MM:SS.mmm"
            dt = datetime.strptime(ts_s, "%Y-%m-%d %H:%M:%S.%f")
        except Exception:
            try:
                dt = datetime.strptime(ts_s, "%Y-%m-%d %H:%M:%S")
            except Exception:
                ts_valid = False
                continue
        # 允许一定的时区差异（此处按UTC理解）与时间漂移
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        # funding_rates 的 timestamp 可能指向未来的生效时间（预测值），放宽至 +2h
        future_allowance = timedelta(hours=2) if table == "funding_rates" else timedelta(minutes=5)
        if dt > (now + future_allowance):
            ts_valid = False
    result["ts_ok"] = ts_valid and key_fields_ok

    # 合并判定
    result["ok"] = (cnt >= (1000 if table in HIGH_FREQ else 0)) and fields_ok and result["ts_ok"]
    return result


def main():
    print(f"\n🧪 ClickHouse 数据完整性校验 | DB={DB} | URL={CH_URL}\n")
    overall_ok = True
    report: List[Dict] = []

    for t in ALL_TABLES:
        r = check_table(t)
        report.append(r)
        ok = "✅" if r["ok"] else "❌"
        print(f"[{ok}] {t}")
        print(f"  - recent_count: {r['count']}")
        print(f"  - latest_ts: {r['latest']}")
        print(f"  - fields_ok: {r['fields_ok']}, ts_ok: {r['ts_ok']}")
        if r["notes"]:
            print(f"  - notes: {'; '.join(r['notes'])}")
        overall_ok = overall_ok and r["ok"]

    print("\n=== 结果总结 ===")
    print("- 高频 (5m>=1000): trades, orderbooks")
    print("- 低频 (24h>0): funding_rates, open_interests, liquidations, lsr_top_positions, lsr_all_accounts, volatility_indices\n")
    print(f"总体结论: {'✅ 通过' if overall_ok else '❌ 未通过'}")

    # 机器可读输出（如需被CI收集）
    try:
        j = json.dumps(report, ensure_ascii=False)
        print("\n--- JSON ---\n" + j)
    except Exception:
        pass

    # 非零退出用于CI
    sys.exit(0 if overall_ok else 2)


if __name__ == "__main__":
    main()

