# MarketPrism Cold Storage Service（独立模块）

职责：从 ClickHouse Hot 批量复制到 ClickHouse Cold（按时间窗口），推进水位，可选清理。基于 `services/data-storage-service/replication.py`。

- 入口：`services/cold-storage-service/main.py`
- 配置：`services/cold-storage-service/config/cold_storage_config.yaml`
- 健康端口：8086（/health, /stats）
- 测试阶段可全部在本机部署，但逻辑上假设冷端在远端（NAS）。
- 跨实例复制：已内置基于 ClickHouse remote() 的热→冷跨实例复制逻辑；当 hot 与 cold 的主机/端口不同即自动启用。


## 本机“假远端”快速验证
1. 启动 ClickHouse Hot 与 ClickHouse Cold（示例端口：Hot=9000/8123，Cold=9001/8124）
2. 设置环境变量并启动冷端：
   ```bash
   export HOT_CH_HOST=clickhouse-hot HOT_CH_TCP_PORT=9000
   export COLD_CH_HOST=clickhouse-cold COLD_CH_TCP_PORT=9001
   python services/cold-storage-service/main.py
   ```
3. 观察日志与 /stats：确认各表复制计数增长，watermark 推进；`cleanup_enabled=false`（稳定后再开启）。

## 远端 NAS 部署要点
- 冷端代码与 ClickHouse 部署在 NAS 上；配置中 cold_storage.* 指向 NAS 本机；hot_storage.* 指向热端 ClickHouse 地址
- 开启清理前需观察 24–48 小时，确认复制稳定

## 使用 manage 脚本（推荐）
- 路径：`services/cold-storage-service/scripts/manage.sh`
- 赋予执行权限：`chmod +x services/cold-storage-service/scripts/manage.sh`
- 常用命令示例：
  - 安装依赖（venv）：`services/cold-storage-service/scripts/manage.sh install-deps`
  - 初始化冷端表结构：`services/cold-storage-service/scripts/manage.sh init-schema`
  - 启动服务：`services/cold-storage-service/scripts/manage.sh start`
  - 查看状态/健康：`services/cold-storage-service/scripts/manage.sh status | health`
  - 跟随日志：`services/cold-storage-service/scripts/manage.sh logs`
  - 快速校验计数：`services/cold-storage-service/scripts/manage.sh verify`

环境变量要点：
- `COLD_STORAGE_CONFIG` 指定配置文件，默认 `services/cold-storage-service/config/cold_storage_config.yaml`
- `MARKETPRISM_COLD_RUN_DIR` 指定运行状态目录，默认 `services/cold-storage-service/run`
## docker-compose 本机一键验证（可选）
- 文件：`services/cold-storage-service/docker-compose.cold-test.yml`
- 用法：
  ```bash
  cd services/cold-storage-service
  docker compose -f docker-compose.cold-test.yml up --build
  # 打开 http://localhost:8086/health 观察健康；/stats 观察复制指标
  ```

- `COLD_CH_HTTP_URL` 指定冷端 ClickHouse HTTP 地址（用于 init-schema/verify 回退），默认 `http://localhost:8123`


## 注意事项
- 避免与热端的内置复制同时运行：未设置 `ENABLE_INTERNAL_REPLICATION` 时，热端不会启用内置复制
- 状态文件路径可通过 `MARKETPRISM_COLD_RUN_DIR` 定制；默认在本模块 `run/`

