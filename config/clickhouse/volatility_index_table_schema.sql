-- MarketPrism 波动率指数表结构
-- 用于存储Deribit等交易所的波动率指数数据

-- 创建数据库（如果不存在）
CREATE DATABASE IF NOT EXISTS marketprism;

-- 创建波动率指数表
CREATE TABLE IF NOT EXISTS marketprism.volatility_index
(
    -- 基础标识字段
    exchange_name LowCardinality(String) COMMENT '交易所名称',
    currency LowCardinality(String) COMMENT '基础货币 (BTC, ETH)',
    index_name String COMMENT '指数名称 (如: BTCDVOL_USDC-DERIBIT-INDEX)',
    
    -- 核心数据字段
    volatility_value Decimal64(8) COMMENT '波动率指数值 (小数形式, 0.85 = 85%)',
    timestamp DateTime64(3, 'UTC') COMMENT '数据时间戳',
    
    -- 扩展信息字段
    resolution LowCardinality(String) COMMENT '数据分辨率 (1m, 5m, 1h, 1d)',
    market_session LowCardinality(String) COMMENT '市场时段',
    data_quality_score Decimal32(4) COMMENT '数据质量评分 (0-1)',
    
    -- 元数据字段
    source_timestamp DateTime64(3, 'UTC') COMMENT '原始数据时间戳',
    collected_at DateTime64(3, 'UTC') COMMENT '采集时间',
    raw_data String COMMENT '原始数据JSON',
    
    -- 分区和排序键
    date Date MATERIALIZED toDate(timestamp) COMMENT '日期分区字段'
)
ENGINE = MergeTree()
PARTITION BY (exchange_name, toYYYYMM(date))
ORDER BY (currency, timestamp, index_name)
PRIMARY KEY (currency, timestamp)
SETTINGS 
    index_granularity = 8192,
    ttl_only_drop_parts = 1;

-- 创建TTL策略：热数据保留30天，冷数据保留1年
ALTER TABLE marketprism.volatility_index 
MODIFY TTL 
    timestamp + INTERVAL 30 DAY TO DISK 'cold',
    timestamp + INTERVAL 365 DAY DELETE;

-- 创建索引优化查询性能
-- 1. 货币+时间范围查询索引
CREATE INDEX IF NOT EXISTS idx_currency_time 
ON marketprism.volatility_index (currency, timestamp) 
TYPE minmax GRANULARITY 1;

-- 2. 指数名称查询索引
CREATE INDEX IF NOT EXISTS idx_index_name 
ON marketprism.volatility_index (index_name) 
TYPE bloom_filter GRANULARITY 1;

-- 3. 数据质量评分索引
CREATE INDEX IF NOT EXISTS idx_quality_score 
ON marketprism.volatility_index (data_quality_score) 
TYPE minmax GRANULARITY 1;

-- 4. 波动率值范围索引
CREATE INDEX IF NOT EXISTS idx_volatility_value 
ON marketprism.volatility_index (volatility_value) 
TYPE minmax GRANULARITY 1;

-- 创建物化视图：每小时聚合数据
CREATE MATERIALIZED VIEW IF NOT EXISTS marketprism.volatility_index_hourly
ENGINE = SummingMergeTree()
PARTITION BY (exchange_name, toYYYYMM(hour))
ORDER BY (currency, hour, index_name)
AS SELECT
    exchange_name,
    currency,
    index_name,
    toStartOfHour(timestamp) as hour,
    avg(volatility_value) as avg_volatility,
    min(volatility_value) as min_volatility,
    max(volatility_value) as max_volatility,
    count() as data_points,
    avg(data_quality_score) as avg_quality_score
FROM marketprism.volatility_index
GROUP BY exchange_name, currency, index_name, hour;

-- 创建物化视图：每日聚合数据
CREATE MATERIALIZED VIEW IF NOT EXISTS marketprism.volatility_index_daily
ENGINE = SummingMergeTree()
PARTITION BY (exchange_name, toYYYYMM(day))
ORDER BY (currency, day, index_name)
AS SELECT
    exchange_name,
    currency,
    index_name,
    toDate(timestamp) as day,
    avg(volatility_value) as avg_volatility,
    min(volatility_value) as min_volatility,
    max(volatility_value) as max_volatility,
    count() as data_points,
    avg(data_quality_score) as avg_quality_score,
    stddevPop(volatility_value) as volatility_stddev
FROM marketprism.volatility_index
GROUP BY exchange_name, currency, index_name, day;

-- 创建查询优化的字典表（可选）
CREATE DICTIONARY IF NOT EXISTS marketprism.volatility_index_dict
(
    currency String,
    index_name String,
    latest_volatility Decimal64(8),
    latest_timestamp DateTime64(3, 'UTC')
)
PRIMARY KEY currency
SOURCE(CLICKHOUSE(
    HOST 'localhost'
    PORT 9000
    USER 'default'
    PASSWORD ''
    DB 'marketprism'
    TABLE 'volatility_index'
))
LAYOUT(HASHED())
LIFETIME(MIN 60 MAX 300);

-- 添加表注释
ALTER TABLE marketprism.volatility_index 
COMMENT '波动率指数数据表 - 存储Deribit等交易所的波动率指数数据，支持实时查询和历史分析';

-- 添加列注释（ClickHouse 21.8+）
ALTER TABLE marketprism.volatility_index 
COMMENT COLUMN exchange_name '交易所名称，如deribit',
COMMENT COLUMN currency '基础货币代码，如BTC、ETH',
COMMENT COLUMN index_name '完整的指数名称，如BTCDVOL_USDC-DERIBIT-INDEX',
COMMENT COLUMN volatility_value '波动率指数值，小数形式，0.85表示85%',
COMMENT COLUMN timestamp '数据的原始时间戳，UTC时区',
COMMENT COLUMN resolution '数据分辨率，如1m、5m、1h、1d',
COMMENT COLUMN market_session '市场时段标识',
COMMENT COLUMN data_quality_score '数据质量评分，0-1之间',
COMMENT COLUMN source_timestamp '数据源的原始时间戳',
COMMENT COLUMN collected_at '数据采集时间戳',
COMMENT COLUMN raw_data '原始JSON数据，用于调试和审计',
COMMENT COLUMN date '日期分区字段，自动从timestamp生成';

-- 创建示例查询视图
CREATE VIEW IF NOT EXISTS marketprism.v_latest_volatility_index AS
SELECT 
    exchange_name,
    currency,
    index_name,
    volatility_value,
    timestamp,
    data_quality_score
FROM marketprism.volatility_index
WHERE timestamp >= now() - INTERVAL 1 HOUR
ORDER BY currency, timestamp DESC;

-- 性能优化建议注释
/*
性能优化建议：

1. 分区策略：
   - 按exchange_name和月份分区，便于数据管理和查询优化
   - 避免过多小分区，保持分区大小在1-10GB之间

2. 排序键优化：
   - 主排序键：currency, timestamp - 支持按货币和时间范围查询
   - 二级排序键：index_name - 支持特定指数查询

3. 索引策略：
   - minmax索引：适用于数值范围查询
   - bloom_filter索引：适用于字符串精确匹配

4. TTL策略：
   - 热数据（30天）：存储在SSD，快速查询
   - 冷数据（1年）：存储在HDD，归档查询
   - 超过1年：自动删除，节省存储空间

5. 物化视图：
   - 小时级聚合：支持中期分析
   - 日级聚合：支持长期趋势分析
   - 自动维护，无需手动更新

6. 查询优化：
   - 使用PREWHERE进行早期过滤
   - 利用分区剪枝减少扫描数据量
   - 合理使用LIMIT和ORDER BY
*/
