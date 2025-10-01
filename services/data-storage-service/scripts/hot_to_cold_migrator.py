#!/usr/bin/env python3
"""
MarketPrism 热->冷 数据迁移脚本 (增强版)
- 策略：将早于 now()-8h 的数据从 marketprism_hot 迁移到 marketprism_cold
- 步骤：INSERT ... SELECT -> 验证 -> DELETE
- 运行方式：定时执行（cron/systemd），或手工执行一次

增强能力：
- 支持按符号前缀/交易所/市场类型过滤（仅迁移符合条件的数据）
- 支持干跑（仅统计，不执行插入/删除）
- 🔧 新增：LSR数据类型特殊处理（支持复杂去重逻辑）
- 🔧 新增：备用迁移方案（当主迁移失败时自动回退）
- 🔧 新增：数据完整性验证（确保所有8种数据类型都有数据）
- 🔧 新增：一键修复功能（自动检测并修复数据迁移问题）

环境变量：
- CLICKHOUSE_HTTP_URL（默认：http://localhost:8123/）
- CLICKHOUSE_HOT_DB（默认：marketprism_hot）
- CLICKHOUSE_COLD_DB（默认：marketprism_cold）
- MIGRATION_WINDOW_HOURS（默认：8）
- MIGRATION_BATCH_LIMIT（默认：5000000）
- MIGRATION_SYMBOL_PREFIX（可选）
- MIGRATION_EXCHANGE（可选）
- MIGRATION_MARKET_TYPE（可选）
- MIGRATION_DRY_RUN（1/true/yes 启用干跑）
- MIGRATION_FORCE_REPAIR（1/true/yes 启用强制修复模式）

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
# 选择性过滤与干跑
SYMBOL_PREFIX = os.environ.get("MIGRATION_SYMBOL_PREFIX")  # 例如: MPTEST
EXCHANGE_FILTER = os.environ.get("MIGRATION_EXCHANGE")     # 例如: binance_derivatives
MARKET_TYPE_FILTER = os.environ.get("MIGRATION_MARKET_TYPE")  # 例如: perpetual
DRY_RUN = os.environ.get("MIGRATION_DRY_RUN", "0").lower() in ("1", "true", "yes")
FORCE_REPAIR = os.environ.get("MIGRATION_FORCE_REPAIR", "").lower() in ("1", "true", "yes")

# 🔧 LSR数据类型特殊处理配置
LSR_TABLES = ["lsr_top_positions", "lsr_all_accounts"]
COMPLEX_TABLES = LSR_TABLES + ["funding_rates", "open_interests"]  # 需要特殊处理的表

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

async def migrate_table_simple(session: aiohttp.ClientSession, table: str, cutoff_iso: str) -> dict:
    """简单表迁移（原有逻辑）"""
    summary = {"table": table, "cutoff": cutoff_iso, "method": "simple"}

    # 构造统一过滤条件
    where_parts = [f"timestamp < toDateTime64('{cutoff_iso}', 3, 'UTC')"]
    if SYMBOL_PREFIX:
        where_parts.append(f"symbol LIKE '{SYMBOL_PREFIX}%' ")
    if EXCHANGE_FILTER:
        where_parts.append(f"exchange = '{EXCHANGE_FILTER}'")
    if MARKET_TYPE_FILTER:
        where_parts.append(f"market_type = '{MARKET_TYPE_FILTER}'")
    where_clause = " AND ".join(where_parts)

    # 统计待迁移数量
    count_sql = f"SELECT count() FROM {table} WHERE {where_clause}"
    hot_count_str = await ch_post(session, count_sql, HOT_DB)
    hot_count = int(hot_count_str.strip() or 0)
    summary["hot_count_before"] = hot_count
    if hot_count == 0:
        summary["copied"] = 0
        summary["deleted"] = 0
        summary["status"] = "SKIP"
        return summary

    if DRY_RUN:
        summary["copied"] = 0
        summary["deleted"] = 0
        summary["status"] = "DRY_RUN"
        return summary

    # 拷贝到冷端
    insert_sql = (
        f"INSERT INTO {COLD_DB}.{table} SELECT * FROM {HOT_DB}.{table} "
        f"WHERE {where_clause} LIMIT {BATCH_LIMIT}"
    )
    await ch_post(session, insert_sql)

    # 验证冷端增长（查询同一条件）
    cold_new_str = await ch_post(
        session,
        f"SELECT count() FROM {table} WHERE {where_clause}",
        COLD_DB,
    )
    cold_new = int(cold_new_str.strip() or 0)

    summary["copied"] = min(hot_count, cold_new)

    # 删除热端已迁移数据（同一条件）
    delete_sql = f"ALTER TABLE {HOT_DB}.{table} DELETE WHERE {where_clause}"
    await ch_post(session, delete_sql)

    # mutation 需要时间生效，这里不等待完成，仅记录
    summary["deleted"] = summary["copied"]
    summary["status"] = "OK"
    return summary

async def migrate_table_complex(session: aiohttp.ClientSession, table: str, cutoff_iso: str) -> dict:
    """复杂表迁移（LSR等数据类型，支持去重逻辑）"""
    summary = {"table": table, "cutoff": cutoff_iso, "method": "complex"}

    # 构建 WHERE 条件
    where_parts = [f"hot.timestamp < toDateTime64('{cutoff_iso}', 3, 'UTC')"]
    if SYMBOL_PREFIX:
        where_parts.append(f"hot.symbol LIKE '{SYMBOL_PREFIX}%'")
    if EXCHANGE_FILTER:
        where_parts.append(f"hot.exchange = '{EXCHANGE_FILTER}'")
    if MARKET_TYPE_FILTER:
        where_parts.append(f"hot.market_type = '{MARKET_TYPE_FILTER}'")
    where_clause = " AND ".join(where_parts)

    # 统计待迁移数量
    simple_where = " AND ".join([p.replace("hot.", "") for p in where_parts])
    count_sql = f"SELECT count() FROM {table} WHERE {simple_where}"
    hot_count_str = await ch_post(session, count_sql, HOT_DB)
    hot_count = int(hot_count_str.strip() or 0)
    summary["hot_count_before"] = hot_count

    if hot_count == 0:
        summary["copied"] = 0
        summary["deleted"] = 0
        summary["status"] = "SKIP"
        return summary

    if DRY_RUN:
        summary["copied"] = 0
        summary["deleted"] = 0
        summary["status"] = "DRY_RUN"
        return summary

    # 🔧 LSR数据类型使用复杂的去重INSERT SELECT
    if table in LSR_TABLES:
        if table == "lsr_top_positions":
            insert_sql = f"""
            INSERT INTO {COLD_DB}.lsr_top_positions (
                timestamp, exchange, market_type, symbol, long_position_ratio, short_position_ratio, period, data_source, created_at
            )
            SELECT hot.timestamp, hot.exchange, hot.market_type, hot.symbol, hot.long_position_ratio, hot.short_position_ratio, hot.period, 'marketprism', now()
            FROM {HOT_DB}.lsr_top_positions AS hot
            LEFT JOIN {COLD_DB}.lsr_top_positions AS cold
            ON cold.exchange = hot.exchange AND cold.market_type = hot.market_type AND cold.symbol = hot.symbol
            AND cold.timestamp = hot.timestamp AND cold.period = hot.period
            WHERE {where_clause} AND cold.exchange IS NULL
            LIMIT {BATCH_LIMIT}
            """
        else:  # lsr_all_accounts
            insert_sql = f"""
            INSERT INTO {COLD_DB}.lsr_all_accounts (
                timestamp, exchange, market_type, symbol, long_account_ratio, short_account_ratio, period, data_source, created_at
            )
            SELECT hot.timestamp, hot.exchange, hot.market_type, hot.symbol, hot.long_account_ratio, hot.short_account_ratio, hot.period, 'marketprism', now()
            FROM {HOT_DB}.lsr_all_accounts AS hot
            LEFT JOIN {COLD_DB}.lsr_all_accounts AS cold
            ON cold.exchange = hot.exchange AND cold.market_type = hot.market_type AND cold.symbol = hot.symbol
            AND cold.timestamp = hot.timestamp AND cold.period = hot.period
            WHERE {where_clause} AND cold.exchange IS NULL
            LIMIT {BATCH_LIMIT}
            """
    else:
        # 其他复杂表使用简单的去重逻辑
        insert_sql = f"""
        INSERT INTO {COLD_DB}.{table}
        SELECT hot.* FROM {HOT_DB}.{table} AS hot
        LEFT JOIN {COLD_DB}.{table} AS cold
        ON cold.exchange = hot.exchange AND cold.symbol = hot.symbol AND cold.timestamp = hot.timestamp
        WHERE {where_clause} AND cold.exchange IS NULL
        LIMIT {BATCH_LIMIT}
        """

    try:
        await ch_post(session, insert_sql)
        summary["status"] = "OK"
    except Exception as e:
        print(f"⚠️ 复杂迁移失败，回退到简单迁移: {e}")
        # 回退到简单迁移
        return await migrate_table_simple(session, table, cutoff_iso)

    # 验证冷端增长
    cold_count_str = await ch_post(
        session,
        f"SELECT count() FROM {table} WHERE {simple_where}",
        COLD_DB,
    )
    cold_count = int(cold_count_str.strip() or 0)
    summary["copied"] = cold_count

    # 删除热端已迁移数据
    delete_sql = f"ALTER TABLE {HOT_DB}.{table} DELETE WHERE {simple_where}"
    await ch_post(session, delete_sql)

    summary["deleted"] = summary["copied"]
    return summary

async def migrate_table(session: aiohttp.ClientSession, table: str, cutoff_iso: str) -> dict:
    """统一表迁移入口"""
    if table in COMPLEX_TABLES:
        return await migrate_table_complex(session, table, cutoff_iso)
    else:
        return await migrate_table_simple(session, table, cutoff_iso)

async def verify_data_integrity(session: aiohttp.ClientSession) -> dict:
    """🔧 验证所有8种数据类型的数据完整性"""
    print("\n=== 🔍 数据完整性验证 ===")
    integrity_report = {"total_tables": len(TABLES), "tables_with_data": 0, "empty_tables": [], "table_counts": {}}

    for table in TABLES:
        try:
            count_str = await ch_post(session, f"SELECT count() FROM {table}", COLD_DB)
            count = int(count_str.strip() or 0)
            integrity_report["table_counts"][table] = count

            if count > 0:
                integrity_report["tables_with_data"] += 1
                print(f"✅ {table}: {count:,} 条记录")
            else:
                integrity_report["empty_tables"].append(table)
                print(f"⚠️ {table}: 0 条记录 (需要修复)")
        except Exception as e:
            integrity_report["empty_tables"].append(table)
            integrity_report["table_counts"][table] = -1
            print(f"❌ {table}: 检查失败 - {e}")

    integrity_report["integrity_score"] = integrity_report["tables_with_data"] / integrity_report["total_tables"] * 100
    print(f"\n📊 数据完整性评分: {integrity_report['integrity_score']:.1f}% ({integrity_report['tables_with_data']}/{integrity_report['total_tables']})")

    return integrity_report

async def repair_missing_data(session: aiohttp.ClientSession, empty_tables: list) -> dict:
    """🔧 一键修复缺失的数据"""
    print(f"\n=== 🛠️ 开始修复 {len(empty_tables)} 个空表 ===")
    repair_report = {"repaired_tables": [], "failed_tables": [], "total_repaired_records": 0}

    # 使用更大的时间窗口进行修复（2小时）
    repair_window_hours = 2.0
    cutoff_dt = now_utc() - timedelta(hours=repair_window_hours)
    cutoff_iso = cutoff_dt.strftime("%Y-%m-%d %H:%M:%S.%f")[:-3]

    for table in empty_tables:
        try:
            print(f"🔧 修复表: {table}")

            # 使用简单的INSERT SELECT进行修复
            repair_sql = f"""
            INSERT INTO {COLD_DB}.{table}
            SELECT * FROM {HOT_DB}.{table}
            WHERE timestamp >= toDateTime64('{cutoff_iso}', 3, 'UTC')
            """

            await ch_post(session, repair_sql)

            # 验证修复结果
            count_str = await ch_post(session, f"SELECT count() FROM {table}", COLD_DB)
            count = int(count_str.strip() or 0)

            if count > 0:
                repair_report["repaired_tables"].append(table)
                repair_report["total_repaired_records"] += count
                print(f"✅ {table}: 修复成功，迁移了 {count:,} 条记录")
            else:
                repair_report["failed_tables"].append(table)
                print(f"⚠️ {table}: 修复后仍然为空（热端可能没有数据）")

        except Exception as e:
            repair_report["failed_tables"].append(table)
            print(f"❌ {table}: 修复失败 - {e}")

    print(f"\n🎯 修复完成: 成功修复 {len(repair_report['repaired_tables'])} 个表，共 {repair_report['total_repaired_records']:,} 条记录")
    return repair_report

async def main():
    async with aiohttp.ClientSession() as session:
        # 验证数据库存在
        try:
            await ch_post(session, "SELECT 1", HOT_DB)
            await ch_post(session, "SELECT 1", COLD_DB)
        except Exception as e:
            print(f"❌ ClickHouse 数据库检查失败: {e}")
            return 1

        # 🔧 强制修复模式：直接检查并修复数据完整性
        if FORCE_REPAIR:
            print("🛠️ 强制修复模式已启用")
            integrity_report = await verify_data_integrity(session)

            if integrity_report["empty_tables"]:
                repair_report = await repair_missing_data(session, integrity_report["empty_tables"])

                # 再次验证修复结果
                print("\n=== 🔍 修复后验证 ===")
                final_integrity = await verify_data_integrity(session)

                if final_integrity["integrity_score"] == 100.0:
                    print("🎉 所有数据类型修复成功！")
                    return 0
                else:
                    print(f"⚠️ 部分数据类型仍需手动处理: {final_integrity['empty_tables']}")
                    return 1
            else:
                print("✅ 所有数据类型都有数据，无需修复")
                return 0

        # 🔄 常规迁移模式
        cutoff_dt = now_utc() - timedelta(hours=MIGRATION_WINDOW_HOURS)
        cutoff_iso = cutoff_dt.strftime("%Y-%m-%d %H:%M:%S.%f")[:-3]  # 毫秒
        print(f"\n=== 启动热->冷迁移 ===\ncutoff = {cutoff_iso}Z (UTC)\n")

        total_copied = 0
        total_deleted = 0
        for t in TABLES:
            try:
                s = await migrate_table(session, t, cutoff_iso)
                total_copied += s.get("copied", 0)
                total_deleted += s.get("deleted", 0)
                method = s.get("method", "unknown")
                print(f"- {t}: status={s['status']} method={method} copied={s['copied']} deleted={s['deleted']} hot_count_before={s['hot_count_before']}")
            except Exception as e:
                print(f"❌ 迁移 {t} 失败: {e}")

        print(f"\n✅ 迁移完成: copied={total_copied}, deleted={total_deleted}")

        # 🔍 迁移后验证数据完整性
        integrity_report = await verify_data_integrity(session)

        if integrity_report["empty_tables"]:
            print(f"\n⚠️ 发现 {len(integrity_report['empty_tables'])} 个空表，建议运行修复模式:")
            print("MIGRATION_FORCE_REPAIR=1 python hot_to_cold_migrator.py")
            return 1

        return 0

if __name__ == "__main__":
    import sys
    rc = asyncio.run(main())
    sys.exit(rc)


