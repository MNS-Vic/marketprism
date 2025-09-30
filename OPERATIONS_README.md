# MarketPrism 运维脚本使用指南

## 🚀 快速开始

### 首次部署

```bash
# 一键初始化并启动整个系统
./scripts/manage_all.sh init
./scripts/manage_all.sh start

# 验证系统状态
./scripts/manage_all.sh health
```

### 日常运维

```bash
# 重启所有服务
./scripts/manage_all.sh restart

# 查看系统状态
./scripts/manage_all.sh status

# 执行健康检查
./scripts/manage_all.sh health
```

### 故障处理

```bash
# 快速诊断问题
./scripts/manage_all.sh diagnose

# 清理锁文件
./scripts/manage_all.sh clean

# 重新启动
./scripts/manage_all.sh restart
```

## 📋 命令速查表

| 操作 | 命令 | 说明 |
|------|------|------|
| 初始化系统 | `./scripts/manage_all.sh init` | 首次部署时使用 |
| 启动所有服务 | `./scripts/manage_all.sh start` | 按正确顺序启动 |
| 停止所有服务 | `./scripts/manage_all.sh stop` | 按正确顺序停止 |
| 重启所有服务 | `./scripts/manage_all.sh restart` | 先停止再启动 |
| 查看状态 | `./scripts/manage_all.sh status` | 显示所有服务状态 |
| 健康检查 | `./scripts/manage_all.sh health` | 执行完整健康检查 |
| 快速诊断 | `./scripts/manage_all.sh diagnose` | 诊断系统问题 |
| 清理锁文件 | `./scripts/manage_all.sh clean` | 清理临时数据 |

## 🔧 模块独立操作

### 数据存储服务

```bash
cd services/data-storage-service/scripts

# 启动热端存储
./manage.sh start hot

# 停止冷端存储
./manage.sh stop cold

# 重启所有存储服务
./manage.sh restart

# 强制清理锁文件
./manage.sh clean --force
```

### 数据采集器

```bash
cd services/data-collector/scripts

# 启动采集器
./manage.sh start

# 重启采集器
./manage.sh restart

# 查看采集器状态
./manage.sh status
```

### NATS消息代理

```bash
cd services/message-broker/scripts

# 启动NATS
./manage.sh start

# 查看NATS日志
./manage.sh logs -f

# 查看NATS状态
./manage.sh status
```

## 🚨 常见问题处理

### 问题1：服务启动失败

```bash
# 步骤1：诊断问题
./scripts/manage_all.sh diagnose

# 步骤2：清理锁文件
./scripts/manage_all.sh clean

# 步骤3：重新启动
./scripts/manage_all.sh restart

# 步骤4：验证
./scripts/manage_all.sh health
```

### 问题2：端口被占用

```bash
# 步骤1：查看端口占用
ss -ltnp | grep -E ':(4222|8222|8123|8085|8086|8087)'

# 步骤2：停止所有服务
./scripts/manage_all.sh stop

# 步骤3：清理并重启
./scripts/manage_all.sh clean
./scripts/manage_all.sh start
```

### 问题3：僵尸锁文件

```bash
# 步骤1：查看锁文件
ls -l /tmp/marketprism_*.lock

# 步骤2：强制清理
cd services/data-storage-service/scripts
./manage.sh clean --force

cd ../../data-collector/scripts
./manage.sh clean

# 步骤3：重新启动
cd ../../../
./scripts/manage_all.sh start
```

## 📊 服务架构

### 服务启动顺序

```
1. NATS消息代理 (端口: 4222, 8222)
   ↓
2. 热端存储服务 (端口: 8085)
   ↓
3. 数据采集器 (端口: 8087)
   ↓
4. 冷端存储服务 (端口: 8086)
```

### 服务依赖关系

- **热端存储服务**: 依赖 NATS + ClickHouse
- **数据采集器**: 依赖 NATS
- **冷端存储服务**: 依赖 ClickHouse + 热端存储

## 📝 日志文件

所有日志文件位于 `logs/` 目录：

```bash
# 查看热端存储日志
tail -f logs/hot_storage.log

# 查看冷端存储日志
tail -f logs/cold_storage.log

# 查看数据采集器日志
tail -f logs/collector.log

# 查看NATS日志
cd services/message-broker/scripts
./manage.sh logs -f
```

## 🔐 核心特性

### 1. 实例锁机制
- 防止多实例运行
- 自动清理僵尸锁
- 支持强制清理

### 2. 依赖自动管理
- 自动启动ClickHouse
- 自动启动NATS
- 按正确顺序启动服务

### 3. 幂等性保证
- 多次执行安全
- 自动跳过已完成步骤
- 提供清晰反馈

### 4. 完善的健康检查
- HTTP端点检查
- 进程状态检查
- 端口监听检查
- 锁文件状态检查

## 📚 详细文档

- **运维操作指南**: `scripts/OPERATIONS_GUIDE.md`
- **脚本实施报告**: `logs/SCRIPTS_IMPLEMENTATION_REPORT.md`
- **最终总结报告**: `logs/FINAL_SCRIPTS_SUMMARY.md`

## 🎯 最佳实践

### 每日检查

```bash
./scripts/manage_all.sh health
./scripts/manage_all.sh status
```

### 每周维护

```bash
./scripts/manage_all.sh clean
./scripts/manage_all.sh restart
./scripts/manage_all.sh health
```

### 升级部署

```bash
# 1. 停止服务
./scripts/manage_all.sh stop

# 2. 更新代码
git pull

# 3. 重新启动
./scripts/manage_all.sh start

# 4. 验证
./scripts/manage_all.sh health
```

---

**最后更新**: 2025-09-29  
**版本**: 1.0.0
