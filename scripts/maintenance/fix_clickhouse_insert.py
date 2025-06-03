#!/usr/bin/env python
# coding: utf-8

import urllib.request
import urllib.parse
import json
import sys
import time
import datetime
import random
import subprocess

def run_command(command):
    """运行命令并返回结果"""
    try:
        result = subprocess.run(
            command,
            shell=True,
            check=True,
            capture_output=True,
            text=True
        )
        return result.stdout
    except subprocess.CalledProcessError as e:
        print(f"命令执行失败: {e}")
        print(f"错误输出: {e.stderr}")
        return None

def execute_query(query):
    """执行ClickHouse查询"""
    try:
        encoded_query = urllib.parse.quote(query)
        with urllib.request.urlopen(f"http://localhost:8123/?query={encoded_query}") as response:
            result = response.read().decode('utf-8')
            return result
    except Exception as e:
        print(f"查询执行失败: {str(e)}")
        return None

def test_insert():
    """测试向ClickHouse插入数据"""
    print("测试向ClickHouse插入数据...")
    
    # 生成测试数据
    now = datetime.datetime.now()
    id = random.randint(1000000, 9999999)
    exchange = "BINANCE"
    symbol = "BTCUSDT"
    trade_id = f"TEST{id}"
    price = 60000.0 + random.randint(-1000, 1000)
    quantity = round(random.uniform(0.01, 1.0), 4)
    side = "BUY" if random.random() > 0.5 else "SELL"
    trade_time = now.strftime("%Y-%m-%d %H:%M:%S")
    receive_time = now.strftime("%Y-%m-%d %H:%M:%S")
    
    # 构建插入SQL
    insert_sql = f"""
    INSERT INTO marketprism.trades 
        (id, exchange, symbol, trade_id, price, quantity, side, trade_time, receive_time, is_best_match)
    VALUES 
        ({id}, '{exchange}', '{symbol}', '{trade_id}', {price}, {quantity}, '{side}', '{trade_time}', '{receive_time}', true)
    """
    
    print(f"执行插入: {insert_sql}")
    result = execute_query(insert_sql)
    
    if result is not None:
        print("[OK] 数据插入成功")
        return True
    else:
        print("[ERROR] 数据插入失败")
        return False

def check_table_structure():
    """检查trades表结构"""
    print("\n检查trades表结构...")
    
    query = "DESCRIBE TABLE marketprism.trades FORMAT JSON"
    result = execute_query(query)
    
    if result:
        try:
            structure = json.loads(result)
            print("当前表结构:")
            
            if "data" in structure:
                for column in structure["data"]:
                    print(f"  - {column.get('name')}: {column.get('type')}")
                return structure["data"]
            else:
                print("[ERROR] 未找到表结构数据")
                return None
        except json.JSONDecodeError:
            print(f"[ERROR] 解析表结构失败: {result}")
            return None
    else:
        print("[ERROR] 无法获取表结构")
        return None

def fix_table_structure():
    """修复trades表结构"""
    print("\n尝试修复表结构...")
    
    # 备份现有表数据
    backup_query = """
    CREATE TABLE IF NOT EXISTS marketprism.trades_backup AS 
    SELECT * FROM marketprism.trades
    """
    
    print("备份现有数据...")
    backup_result = execute_query(backup_query)
    
    if backup_result is None:
        print("[WARN] 无法备份现有数据，但将继续尝试修复表")
    
    # 删除现有表
    drop_query = "DROP TABLE IF EXISTS marketprism.trades"
    
    print("删除现有表...")
    drop_result = execute_query(drop_query)
    
    if drop_result is None:
        print("[ERROR] 无法删除现有表，修复失败")
        return False
    
    # 创建正确的表结构
    create_query = """
    CREATE TABLE IF NOT EXISTS marketprism.trades (
        id UInt64,
        exchange LowCardinality(String),
        symbol LowCardinality(String),
        trade_id String,
        price Float64,
        quantity Float64,
        side LowCardinality(String),
        trade_time DateTime,
        receive_time DateTime,
        is_best_match Bool DEFAULT true
    ) ENGINE = MergeTree()
    ORDER BY (exchange, symbol, trade_time)
    """
    
    print("创建正确的表结构...")
    create_result = execute_query(create_query)
    
    if create_result is None:
        print("[ERROR] 无法创建新表，修复失败")
        return False
    
    # 恢复备份数据
    try:
        restore_query = """
        INSERT INTO marketprism.trades 
        SELECT * FROM marketprism.trades_backup
        """
        
        print("恢复备份数据...")
        restore_result = execute_query(restore_query)
        
        if restore_result is None:
            print("[WARN] 无法恢复备份数据，但表结构已修复")
    except Exception:
        print("[WARN] 跳过数据恢复，可能没有备份数据")
    
    print("[OK] 表结构修复完成")
    return True

def verify_permissions():
    """验证ClickHouse权限"""
    print("\n验证ClickHouse权限...")
    
    # 检查用户权限
    query = "SHOW GRANTS"
    result = execute_query(query)
    
    if result:
        print(f"当前用户权限: {result.strip()}")
    else:
        print("[WARN] 无法获取用户权限")
    
    # 验证读写权限
    print("\n验证读写权限...")
    
    # 尝试创建一个临时表
    temp_table_query = """
    CREATE TABLE IF NOT EXISTS marketprism.temp_test (
        id UInt64,
        value String
    ) ENGINE = MergeTree()
    ORDER BY id
    """
    
    temp_result = execute_query(temp_table_query)
    
    if temp_result is not None:
        print("[OK] 可以创建表，写入权限正常")
        
        # 尝试插入和查询数据
        insert_query = "INSERT INTO marketprism.temp_test VALUES (1, 'test')"
        insert_result = execute_query(insert_query)
        
        if insert_result is not None:
            print("[OK] 可以插入数据")
            
            # 查询数据
            select_query = "SELECT * FROM marketprism.temp_test FORMAT JSON"
            select_result = execute_query(select_query)
            
            if select_result:
                print("[OK] 可以查询数据，读取权限正常")
                
                # 清理临时表
                cleanup_query = "DROP TABLE marketprism.temp_test"
                execute_query(cleanup_query)
                
                return True
            else:
                print("[ERROR] 无法查询数据，读取权限可能有问题")
        else:
            print("[ERROR] 无法插入数据")
    else:
        print("[ERROR] 无法创建表，写入权限可能有问题")
    
    return False

def execute_all_repairs():
    """执行所有修复操作"""
    print("===== ClickHouse数据插入修复工具 =====")
    
    # 测试插入
    insert_success = test_insert()
    
    if insert_success:
        print("\n[OK] 数据插入正常，无需修复")
        return
    
    # 检查表结构
    check_table_structure()
    
    # 验证权限
    verify_permissions()
    
    # 修复表结构
    structure_fixed = fix_table_structure()
    
    if structure_fixed:
        # 再次测试插入
        insert_success = test_insert()
        
        if insert_success:
            print("\n[OK] 修复成功，数据现在可以正常插入")
        else:
            print("\n[ERROR] 结构修复后仍无法插入数据，可能存在其他问题")
    else:
        print("\n[ERROR] 无法修复表结构")
    
    print("\n===== 修复完成 =====")

if __name__ == "__main__":
    execute_all_repairs() 