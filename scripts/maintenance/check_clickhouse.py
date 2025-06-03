#!/usr/bin/env python3
import clickhouse_driver

def main():
    client = clickhouse_driver.Client(host='localhost', port=9000)
    print('ClickHouse表结构：')
    
    tables = client.execute('SHOW TABLES FROM marketprism')
    
    for table in tables:
        table_name = table[0]
        print(f"\n表名: {table_name}")
        
        # 获取表结构
        columns = client.execute(f'DESC marketprism.{table_name}')
        print("列结构:")
        for col in columns[:5]:  # 只展示前5列
            print(f"  {col[0]} ({col[1]})")
        
        if len(columns) > 5:
            print(f"  ... 及其他 {len(columns) - 5} 列")
        
        # 获取数据量
        count = client.execute(f'SELECT count() FROM marketprism.{table_name}')[0][0]
        print(f"数据量: {count} 行")

if __name__ == "__main__":
    main()