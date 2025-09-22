# Data Collector配置迁移执行计划

## 🎯 迁移目标
将配置文件从全局配置目录 `config/collector/` 迁移到服务本地目录 `services/data-collector/config/`

## 📋 迁移文件清单

### 需要迁移的文件：
1. `config/collector/unified_data_collection.yaml` → `services/data-collector/config/collector/unified_data_collection.yaml`
2. `config/collector/README.md` → `services/data-collector/config/collector/README.md`
3. `config/collector/nats-server.conf` → `services/data-collector/config/nats/nats-server.conf`
4. `config/collector/nats-server-docker.conf` → `services/data-collector/config/nats/nats-server-docker.conf`
5. `config/collector/docker-compose.nats.yml` → `services/data-collector/config/nats/docker-compose.nats.yml`

## 🔧 需要修改的代码文件

### 主要文件：
1. `services/data-collector/unified_collector_main.py`
   - ConfigResolver.get_config_path() 方法
   - 路径：`project_root / "config" / "collector"` → `Path(__file__).parent / "config" / "collector"`

2. `services/data-collector/collector/config.py`
   - ConfigPathManager.__init__() 方法
   - 路径解析逻辑更新

3. `services/data-collector/collector/data_collection_config_manager.py`
   - 配置文件路径更新

4. `services/data-collector/collector/exchange_config_loader.py`
   - 配置文件路径更新

5. `services/data-collector/collector/strategy_config_manager.py`
   - 配置文件路径更新

6. `services/data-collector/collector/websocket_config_loader.py`
   - 配置文件路径更新

## ⚠️ 风险评估

### 高风险项：
- 路径引用错误可能导致配置加载失败
- 相对路径计算错误可能影响所有管理器启动

### 中风险项：
- 日志文件路径可能需要调整
- Docker配置路径可能需要更新

### 低风险项：
- 配置文件内容保持不变
- 功能逻辑不受影响

## 🔄 回滚方案

### 快速回滚：
1. 保留原配置文件备份
2. 恢复原始代码文件
3. 重启服务验证

### 备份策略：
- 创建 `config/collector.backup/` 目录保存原文件
- 创建 `services/data-collector/code.backup/` 保存原代码
- 记录所有修改的文件列表

## 📊 验证测试方案

### 基础验证：
1. 配置文件加载测试
2. 路径解析测试
3. 服务启动测试

### 功能验证：
1. 8种数据类型管理器启动
2. 5个交易所连接测试
3. NATS连接和数据发布测试

### 性能验证：
1. 启动时间对比
2. 内存使用对比
3. 数据吞吐量对比
