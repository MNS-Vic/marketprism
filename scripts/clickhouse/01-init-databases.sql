-- MarketPrism ClickHouse 数据库初始化脚本
-- 创建数据库和基础配置

-- 创建主数据库
CREATE DATABASE IF NOT EXISTS marketprism;

-- 创建冷存储数据库
CREATE DATABASE IF NOT EXISTS marketprism_cold;

-- 使用主数据库
USE marketprism;

-- 显示创建的数据库
SHOW DATABASES;
