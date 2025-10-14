import argparse
import subprocess
import shlex
import sys
from datetime import datetime


def run(cmd: str) -> str:
    """Run a shell command and return stdout as text. Raise on non-zero exit."""
    p = subprocess.run(cmd, shell=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    if p.returncode != 0:
        raise RuntimeError(f"Command failed ({p.returncode}): {cmd}\nSTDERR:\n{p.stderr}")
    return p.stdout.strip()


def clickhouse_query(container: str, sql: str, fmt: str = "PrettyCompactMonoBlock") -> str:
    quoted = sql.replace("\n", " ")
    cmd = f"docker exec {shlex.quote(container)} clickhouse-client --query=\"{quoted}\" --format={fmt}"
    return run(cmd)


def main():
    parser = argparse.ArgumentParser(description="Orderbook latency report from ClickHouse (last N minutes)")
    parser.add_argument("--container", default="marketprism-clickhouse-hot", help="ClickHouse docker container name")
    parser.add_argument("--db", default="marketprism_hot", help="Database name")
    parser.add_argument("--table", default="orderbooks", help="Table name inside the db")
    parser.add_argument("--window-minutes", type=int, default=10, help="Time window in minutes")
    parser.add_argument("--limit", type=int, default=12, help="Rows to show in per-symbol ranking")
    args = parser.parse_args()

    fqtn = f"{args.db}.{args.table}"
    m = int(args.window_minutes)

    print(f"\n=== Orderbook latency report (window={m}m) @ {datetime.utcnow().isoformat()}Z ===\n")

    # Overall summary
    overall_sql = f"""
        SELECT
            count() AS rows,
            round(avg(dateDiff('second', timestamp, now())), 3) AS event_avg_s,
            quantile(0.50)(dateDiff('second', timestamp, now())) AS event_p50_s,
            quantile(0.95)(dateDiff('second', timestamp, now())) AS event_p95_s,
            quantile(0.99)(dateDiff('second', timestamp, now())) AS event_p99_s,
            round(avg(dateDiff('second', created_at, now())), 3) AS ingest_avg_s,
            quantile(0.50)(dateDiff('second', created_at, now())) AS ingest_p50_s,
            quantile(0.95)(dateDiff('second', created_at, now())) AS ingest_p95_s,
            quantile(0.99)(dateDiff('second', created_at, now())) AS ingest_p99_s
        FROM {fqtn}
        WHERE created_at > now() - INTERVAL {m} MINUTE
    """
    try:
        print("-- Overall Summary --")
        print(clickhouse_query(args.container, overall_sql))
    except Exception as e:
        print(f"[ERROR] overall query failed: {e}", file=sys.stderr)

    # Top symbols by event_p95
    top_sql = f"""
        SELECT
            exchange,
            symbol,
            count() AS cnt,
            quantile(0.50)(dateDiff('second', timestamp, now())) AS event_p50_s,
            quantile(0.95)(dateDiff('second', timestamp, now())) AS event_p95_s,
            quantile(0.99)(dateDiff('second', timestamp, now())) AS event_p99_s,
            quantile(0.50)(dateDiff('second', created_at, now())) AS ingest_p50_s,
            quantile(0.95)(dateDiff('second', created_at, now())) AS ingest_p95_s
        FROM {fqtn}
        WHERE created_at > now() - INTERVAL {m} MINUTE
        GROUP BY exchange, symbol
        ORDER BY event_p95_s DESC
        LIMIT {args.limit}
    """
    try:
        print("\n-- Worst Symbols by Event Lag (p95) --")
        print(clickhouse_query(args.container, top_sql))
    except Exception as e:
        print(f"[ERROR] top symbols query failed: {e}", file=sys.stderr)

    # Per-exchange summary
    ex_sql = f"""
        SELECT
            exchange,
            count() AS cnt,
            quantile(0.50)(dateDiff('second', timestamp, now())) AS event_p50_s,
            quantile(0.95)(dateDiff('second', timestamp, now())) AS event_p95_s,
            quantile(0.50)(dateDiff('second', created_at, now())) AS ingest_p50_s,
            quantile(0.95)(dateDiff('second', created_at, now())) AS ingest_p95_s
        FROM {fqtn}
        WHERE created_at > now() - INTERVAL {m} MINUTE
        GROUP BY exchange
        ORDER BY exchange ASC
    """
    try:
        print("\n-- Per-Exchange Summary --")
        print(clickhouse_query(args.container, ex_sql))
    except Exception as e:
        print(f"[ERROR] per-exchange query failed: {e}", file=sys.stderr)


if __name__ == "__main__":
    main()

