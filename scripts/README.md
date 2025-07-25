# MarketPrism 脚本工具

本目录包含MarketPrism系统的各种脚本和工具。

## 📁 目录结构

### 🔧 工具脚本 (`tools/`)
- `verify_nats_setup.py` - NATS架构验证工具

### 🏠 开发脚本
- `run_local_services.py` - 本地开发环境服务启动脚本

### 📦 历史脚本 (`legacy/`)
- `run_services.py` - 已过时的服务启动脚本（已迁移到Docker Compose）

## 🎯 使用指南

### NATS架构验证
```bash
# 验证NATS配置是否正确
python scripts/tools/verify_nats_setup.py
```

### 本地开发环境
```bash
# 启动本地开发服务
python scripts/run_local_services.py
```

## 📚 相关文档

- [部署指南](../docs/deployment/)
- [开发指南](../docs/development/)
- [故障排除](../docs/operations/troubleshooting.md) 