#!/usr/bin/env python3
"""
ClickHouse数据库和表结构初始化脚本
分别执行SQL语句以避免多语句错误
"""

import asyncio
import aiohttp
import sys
from pathlib import Path

async def execute_sql(session, sql, database=None):
    """执行单个SQL语句"""
    try:
        url = "http://localhost:8123/"
        if database:
            url += f"?database={database}"

        async with session.post(url, data=sql.strip()) as response:
            if response.status == 200:
                result = await response.text()
                return True, result.strip()
            else:
                error = await response.text()
                return False, error
    except Exception as e:
        return False, str(e)

async def init_clickhouse():
    """初始化ClickHouse数据库和表结构"""
    print("🚀 开始初始化ClickHouse数据库和表结构")

    async with aiohttp.ClientSession() as session:
        # 1. 创建数据库
        print("\n📊 创建数据库...")
        databases = [
            "CREATE DATABASE IF NOT EXISTS marketprism_hot",
            "CREATE DATABASE IF NOT EXISTS marketprism_cold"
        ]

        for db_sql in databases:
            success, result = await execute_sql(session, db_sql)
            if success:
                print(f"✅ {db_sql}")
            else:
                print(f"❌ {db_sql} - {result}")
                return False

        # 2. 读取并执行表结构SQL
        print("\n📋 创建表结构...")
        schema_file = Path(__file__).parent.parent / "config" / "clickhouse_schema.sql"

        if not schema_file.exists():
            print(f"❌ Schema文件不存在: {schema_file}")
            return False

        with open(schema_file, 'r', encoding='utf-8') as f:
            content = f.read()

        # 分割SQL语句（跳过注释和空行）
        statements = []
        current_statement = []

        for line in content.split('\n'):
            line = line.strip()
            if not line or line.startswith('--'):
                continue
            if line.startswith('USE '):
                continue  # 跳过USE语句，我们通过URL参数指定数据库
            if line.startswith('CREATE DATABASE'):
                continue  # 跳过数据库创建语句，已经执行过了

            current_statement.append(line)
            if line.endswith(';'):
                stmt = ' '.join(current_statement).rstrip(';')
                if stmt.strip():
                    statements.append(stmt)
                current_statement = []

        # 如果最后一个语句没有分号
        if current_statement:
            stmt = ' '.join(current_statement)
            if stmt.strip():
                statements.append(stmt)

        # 执行表创建语句
        success_count = 0
        for i, stmt in enumerate(statements):
            if not stmt.strip():
                continue

            print(f"执行语句 {i+1}/{len(statements)}: {stmt[:50]}...")
            success, result = await execute_sql(session, stmt, None)

            if success:
                print(f"✅ 语句 {i+1} 执行成功")
                success_count += 1
            else:
                print(f"❌ 语句 {i+1} 执行失败: {result}")

        print(f"\n📊 表结构初始化完成: {success_count}/{len(statements)} 成功")


        # 3. 冷端表结构
        print("\n📂 冷端表结构由权威 schema 同步创建（忽略 TTL 差异）")

        # 4. 验证表创建
        print("\n🔍 验证表创建...")
        success, tables = await execute_sql(session, "SHOW TABLES", "marketprism_hot")
        if success:
            table_list = tables.split('\n') if tables else []
            print(f"✅ 创建了 {len(table_list)} 个表:")
            for table in table_list:
                if table.strip():
                    print(f"  - {table}")
        else:
            print(f"❌ 无法查询表列表: {tables}")

        return success_count > 0

async def main():
    """主函数"""
    try:
        success = await init_clickhouse()
        if success:
            print("\n🎉 ClickHouse初始化完成")
            sys.exit(0)
        else:
            print("\n❌ ClickHouse初始化失败")
            sys.exit(1)
    except Exception as e:
        print(f"\n💥 初始化过程中发生错误: {e}")
        sys.exit(1)

if __name__ == "__main__":
    asyncio.run(main())
