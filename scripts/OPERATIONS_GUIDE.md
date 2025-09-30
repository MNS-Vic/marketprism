# MarketPrism 运维操作指南

## 🎯 快速参考

### 一键操作

```bash
# 首次部署
./scripts/manage_all.sh init && ./scripts/manage_all.sh start

# 日常重启
./scripts/manage_all.sh restart

# 健康检查
./scripts/manage_all.sh health

# 故障诊断
./scripts/manage_all.sh diagnose
```

## 📋 常用命令速查表

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

# 只启动热端存储
./manage.sh start hot

# 只停止冷端存储
./manage.sh stop cold

# 查看存储服务状态
./manage.sh status

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

## 🚨 故障处理流程

### 场景1：服务启动失败

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

### 场景2：端口被占用

```bash
# 步骤1：查看端口占用
ss -ltnp | grep -E ':(4222|8222|8123|8085|8086|8087)'

# 步骤2：停止所有服务
./scripts/manage_all.sh stop

# 步骤3：清理并重启
./scripts/manage_all.sh clean
./scripts/manage_all.sh start
```

### 场景3：僵尸锁文件

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

### 场景4：数据采集异常

```bash
# 步骤1：检查采集器状态
cd services/data-collector/scripts
./manage.sh status

# 步骤2：查看采集器日志
tail -f ../../logs/collector.log

# 步骤3：重启采集器
./manage.sh restart

# 步骤4：验证NATS连接
cd ../../message-broker/scripts
./manage.sh health
```

## 📊 监控和日志

### 查看日志

```bash
# 热端存储日志
tail -f logs/hot_storage.log

# 冷端存储日志
tail -f logs/cold_storage.log

# 数据采集器日志
tail -f logs/collector.log

# NATS日志
cd services/message-broker/scripts
./manage.sh logs -f
```

### 检查服务状态

```bash
# 查看所有服务状态
./scripts/manage_all.sh status

# 查看进程
ps aux | grep -E '(nats-server|main.py|unified_collector_main.py)' | grep -v grep

# 查看端口
ss -ltnp | grep -E ':(4222|8222|8123|8085|8086|8087)'

# 查看锁文件
ls -l /tmp/marketprism_*.lock
```

## 🔄 日常维护

### 每日检查

```bash
# 执行健康检查
./scripts/manage_all.sh health

# 查看服务状态
./scripts/manage_all.sh status
```

### 每周维护

```bash
# 清理临时文件
./scripts/manage_all.sh clean

# 重启服务
./scripts/manage_all.sh restart

# 验证健康状态
./scripts/manage_all.sh health
```

### 升级部署

```bash
# 1. 停止服务
./scripts/manage_all.sh stop

# 2. 备份数据（如需要）
# ...

# 3. 更新代码
git pull

# 4. 重新启动
./scripts/manage_all.sh start

# 5. 验证
./scripts/manage_all.sh health
./scripts/manage_all.sh status
```

## 🎯 服务启动顺序

脚本会自动按照以下顺序启动服务：

1. **NATS消息代理** (端口: 4222, 8222)
   - 提供消息队列服务
   - 所有服务的依赖基础

2. **热端存储服务** (端口: 8085)
   - 接收并存储实时数据
   - 依赖: NATS, ClickHouse

3. **数据采集器** (端口: 8087)
   - 采集市场数据并发送到NATS
   - 依赖: NATS

4. **冷端存储服务** (端口: 8086)
   - 归档热端数据到冷端存储
   - 依赖: ClickHouse, 热端存储

## 🔐 安全注意事项

1. **锁文件机制**：防止多实例运行，确保数据一致性
2. **优雅停止**：使用脚本停止服务，避免数据丢失
3. **日志审计**：定期检查日志文件，发现异常
4. **权限管理**：确保脚本有执行权限，但限制访问范围

## 📞 技术支持

遇到问题时的处理流程：

1. 运行 `./scripts/manage_all.sh diagnose` 进行快速诊断
2. 查看相关日志文件
3. 检查环境变量配置
4. 确认依赖服务（Docker、Python虚拟环境）正常
5. 参考本文档的故障处理流程

---

**最后更新**: 2025-09-29  
**版本**: 1.0.0
