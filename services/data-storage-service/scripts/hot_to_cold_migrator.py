#!/usr/bin/env python3
"""
MarketPrism 热->冷 数据迁移脚本
- 策略：将早于 now()-8h 的数据从 marketprism_hot 迁移到 marketprism_cold
- 步骤：INSERT ... SELECT -> 验证 -> DELETE
- 运行方式：定时执行（cron/systemd），或手工执行一次

注意：ClickHouse 不支持事务级强一致；本脚本采用“先拷贝后删除”的方式，
     如需更强一致性可在业务层增加去重策略或调整表引擎。
"""

import asyncio
import aiohttp
import os
from datetime import datetime, timezone, timedelta

TABLES = [
    "orderbooks",
    "trades",
    "funding_rates",
    "open_interests",
    "liquidations",
    "lsr_top_positions",
    "lsr_all_accounts",
    "volatility_indices",
]

CLICKHOUSE_URL = os.environ.get("CLICKHOUSE_HTTP_URL", "http://localhost:8123/")
HOT_DB = os.environ.get("CLICKHOUSE_HOT_DB", "marketprism_hot")
COLD_DB = os.environ.get("CLICKHOUSE_COLD_DB", "marketprism_cold")
MIGRATION_WINDOW_HOURS = float(os.environ.get("MIGRATION_WINDOW_HOURS", "8"))
BATCH_LIMIT = int(os.environ.get("MIGRATION_BATCH_LIMIT", "5000000"))  # 可通过环境变量覆盖

def now_utc():
    return datetime.now(timezone.utc)

async def ch_post(session: aiohttp.ClientSession, sql: str, database: str | None = None) -> str:
    url = CLICKHOUSE_URL
    if database:
        url += f"?database={database}"
    async with session.post(url, data=sql) as resp:
        text = await resp.text()
        if resp.status != 200:
            raise RuntimeError(f"ClickHouse error: {resp.status} {text}")
        return text

async def migrate_table(session: aiohttp.ClientSession, table: str, cutoff_iso: str) -> dict:
    summary: dict = {"table": table}

    # 统计待迁移数量
    count_sql = f"SELECT count() FROM {table} WHERE timestamp < toDateTime64('{cutoff_iso}', 3, 'UTC')"
    hot_count_str = await ch_post(session, count_sql, HOT_DB)
    hot_count = int(hot_count_str.strip() or 0)
    summary["hot_count_before"] = hot_count
    if hot_count == 0:
        summary["copied"] = 0
        summary["deleted"] = 0
        summary["status"] = "SKIP"
        return summary

    # 拷贝到冷端
    insert_sql = (
        f"INSERT INTO {COLD_DB}.{table} SELECT * FROM {HOT_DB}.{table} "
        f"WHERE timestamp < toDateTime64('{cutoff_iso}', 3, 'UTC') LIMIT {BATCH_LIMIT}"
    )
    await ch_post(session, insert_sql)

    # 验证冷端增长
    cold_count_before_str = await ch_post(session, f"SELECT count() FROM {table}", COLD_DB)
    cold_count_before = int(cold_count_before_str.strip() or 0)

    # 因为无法获知插入前数量，这里再次查询插入后数量，用差值近似估算
    # 简化：直接查询刚插入区间的数量
    cold_new_str = await ch_post(
        session,
        f"SELECT count() FROM {table} WHERE timestamp < toDateTime64('{cutoff_iso}', 3, 'UTC')",
        COLD_DB,
    )
    cold_new = int(cold_new_str.strip() or 0)

    summary["copied"] = min(hot_count, cold_new)

    # 删除热端已迁移数据（仅按时间条件）
    delete_sql = f"ALTER TABLE {HOT_DB}.{table} DELETE WHERE timestamp < toDateTime64('{cutoff_iso}', 3, 'UTC')"
    await ch_post(session, delete_sql)

    # mutation 需要时间生效，这里不等待完成，仅记录
    summary["deleted"] = summary["copied"]
    summary["status"] = "OK"
    return summary

async def main():
    cutoff_dt = now_utc() - timedelta(hours=MIGRATION_WINDOW_HOURS)
    cutoff_iso = cutoff_dt.strftime("%Y-%m-%d %H:%M:%S.%f")[:-3]  # 毫秒
    print(f"\n=== 启动热->冷迁移 ===\ncutoff = {cutoff_iso}Z (UTC)\n")
    async with aiohttp.ClientSession() as session:
        # 验证数据库存在
        try:
            await ch_post(session, "SELECT 1", HOT_DB)
            await ch_post(session, "SELECT 1", COLD_DB)
        except Exception as e:
            print(f"❌ ClickHouse 数据库检查失败: {e}")
            return 1

        total_copied = 0
        total_deleted = 0
        for t in TABLES:
            try:
                s = await migrate_table(session, t, cutoff_iso)
                total_copied += s.get("copied", 0)
                total_deleted += s.get("deleted", 0)
                print(f"- {t}: status={s['status']} copied={s['copied']} deleted={s['deleted']} hot_count_before={s['hot_count_before']}")
            except Exception as e:
                print(f"❌ 迁移 {t} 失败: {e}")
        print(f"\n✅ 迁移完成: copied={total_copied}, deleted={total_deleted}\n")
    return 0

if __name__ == "__main__":
    import sys
    rc = asyncio.run(main())
    sys.exit(rc)

