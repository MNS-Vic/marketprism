# MarketPrism 快速开始

## 🚀 3分钟部署指南

### 前提条件
- Ubuntu/CentOS/macOS 系统
- 至少 4GB 内存
- sudo 权限

### 一键部署

```bash
# 1. 克隆项目
git clone https://github.com/MNS-Vic/marketprism.git
cd marketprism

# 2. 执行一键部署
./scripts/one_click_deploy.sh --fresh

# 3. 等待完成（约5-10分钟）
```

就这么简单！✨

---

## 📊 验证部署

```bash
# 查看服务状态
./scripts/manage_all.sh status

# 查看数据
clickhouse-client --query "SELECT count(*) FROM marketprism_hot.trades"
```

---

## 🎯 常用命令

| 操作 | 命令 |
|------|------|
| 启动服务 | `./scripts/manage_all.sh start` |
| 停止服务 | `./scripts/manage_all.sh stop` |
| 重启服务 | `./scripts/manage_all.sh restart` |
| 查看状态 | `./scripts/manage_all.sh status` |
| 健康检查 | `./scripts/manage_all.sh health` |
| 清理资源 | `./scripts/one_click_deploy.sh --clean` |

---

## 🌐 服务访问

- **NATS 监控**: http://localhost:8222
- **ClickHouse**: http://localhost:8123
- **存储服务**: http://localhost:8085/health

---

## 📝 查看日志

```bash
# NATS
tail -f /tmp/nats-server.log

# 存储服务
tail -f /tmp/storage-hot.log

# 数据采集器
tail -f /tmp/collector.log
```

---

## 🐛 遇到问题？

查看详细文档：[DEPLOYMENT.md](./DEPLOYMENT.md)

或查看故障排查：[TROUBLESHOOTING.md](./TROUBLESHOOTING.md)

---

## 🎉 部署成功！

现在你可以：
- ✅ 实时采集加密货币市场数据
- ✅ 查询和分析历史数据
- ✅ 开发自己的交易策略
- ✅ 构建数据可视化应用

祝你使用愉快！🚀

