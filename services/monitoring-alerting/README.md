# MarketPrism 监控告警服务 - 重构版本
> 注意：本模块唯一入口为 main.py；main_before_security.py / main_old.py / main_secure*.py 皆为历史版本，已废弃，仅供参考，请勿直接使用。


> 历史入口文件已统一移动至 `services/monitoring-alerting/deprecated/` 目录，严禁直接运行，仅供参考。

## 📋 概述

MarketPrism监控告警服务的重构版本，专注于核心监控功能，为Grafana提供高性能的数据源支持。

### 🎯 设计目标

- **简化架构**: 移除复杂的未实现功能，专注于核心API
- **高性能**: 保持QPS > 2000，响应时间 < 5ms的优秀性能
- **Grafana集成**: 优化为Grafana提供数据源支持
- **轻量级**: 最小化依赖，减少资源消耗
- **稳定可靠**: 100%的服务可用性

## 🚀 核心功能

### ✅ 已实现功能

- **健康检查API** (`/health`)
- **告警管理API** (`/api/v1/alerts`)
- **告警规则API** (`/api/v1/alerts/rules`)
- **Prometheus指标** (`/metrics`)
- **服务状态API** (`/api/v1/status`, `/api/v1/version`)
- **CORS支持**
- **高性能异步处理**

### 🔄 与Grafana集成

本服务专门优化为Grafana的数据源，提供：

- 标准化的Prometheus指标格式
- RESTful API接口
- 实时数据更新
- 高并发支持

## 📊 API端点

| 端点 | 方法 | 描述 | 响应格式 |
|------|------|------|----------|
| `/` | GET | 服务信息 | JSON |
| `/health` | GET | 健康检查 | JSON |

| `/api/v1/alerts` | GET | 告警列表 | JSON |
| `/api/v1/alerts/rules` | GET | 告警规则 | JSON |
| `/api/v1/status` | GET | 服务状态 | JSON |
| `/api/v1/version` | GET | 版本信息 | JSON |
| `/metrics` | GET | Prometheus指标 | Text |

### 查询参数支持

**告警API** (`/api/v1/alerts`):
- `severity`: 按严重程度过滤 (critical, high, medium, low)
- `status`: 按状态过滤 (active, acknowledged, resolved)
- `category`: 按类别过滤 (system, business, network)

**规则API** (`/api/v1/alerts/rules`):
- `enabled`: 按启用状态过滤 (true, false)
- `category`: 按类别过滤 (system, business, network)

## 🛠️ 部署方式

### 方式1: 直接运行

```bash
source venv/bin/activate
# 安装依赖
pip install -r requirements.txt

# 启动服务（唯一入口）
python main.py
```

### 方式2: Docker部署

```bash
# 构建镜像
docker build -t marketprism-monitoring:2.0.0 .

# 运行容器
docker run -p 8082:8082 marketprism-monitoring:2.0.0
```

### 方式3: Grafana集成部署 (推荐)

基于Grafana和Prometheus官方文档的完整监控栈部署：

#### 3.1 启动监控告警服务
```bash
# 激活虚拟环境
source venv/bin/activate

# 启动服务
python services/monitoring-alerting/main.py
```

#### 3.2 部署Prometheus (基于官方配置)
```bash
# 创建Prometheus配置文件
cat > prometheus-marketprism.yml << EOF
global:
  scrape_interval: 15s
  evaluation_interval: 15s

scrape_configs:
  # Prometheus自身监控
  - job_name: 'prometheus'
    static_configs:
      - targets: ['localhost:9090']

  # MarketPrism监控告警服务
  - job_name: 'monitoring-alerting'
    static_configs:
      - targets: ['host.docker.internal:8082']
    metrics_path: /metrics
    scrape_interval: 10s
EOF

# 启动Prometheus容器
docker run -d --name prometheus-marketprism \
  --add-host=host.docker.internal:host-gateway \
  -p 9090:9090 \
  -v $(pwd)/prometheus-marketprism.yml:/etc/prometheus/prometheus.yml:ro \
  prom/prometheus:latest \
  --config.file=/etc/prometheus/prometheus.yml \
  --storage.tsdb.path=/prometheus \
  --web.console.libraries=/etc/prometheus/console_libraries \
  --web.console.templates=/etc/prometheus/consoles \
  --storage.tsdb.retention.time=200h \
  --web.enable-lifecycle
```

#### 3.3 部署Grafana (基于官方配置)
```bash
# 启动Grafana容器
docker run -d --name grafana-marketprism \
  --add-host=host.docker.internal:host-gateway \
  -p 3000:3000 \
  -e GF_SECURITY_ADMIN_PASSWORD=admin123 \
  -e GF_INSTALL_PLUGINS=grafana-clock-panel,grafana-simple-json-datasource \
  grafana/grafana:latest

# 等待Grafana启动
sleep 10

# 配置Prometheus数据源
python setup_grafana_datasource.py
```

#### 3.4 验证部署
```bash
# 运行完整集成测试
python comprehensive_api_test.py

# 运行Grafana集成测试
python grafana_integration_test.py
```

### 方式3: 一键启动监控栈（Prometheus + Alertmanager + Grafana）

```bash
cd services/monitoring-alerting

# 准备环境变量（可选但推荐）
# 复制示例并填入生产值（至少设置 DingTalk 与 Grafana 管理员密码）
cp .env.example .env
# vi .env  # 编辑并保存

# 启动（后台）
docker compose up -d

# 访问
# Prometheus:     http://localhost:9090
# Alertmanager:   http://localhost:9093
# Grafana:        http://localhost:3000  (admin/admin)

# 停止并清理
docker compose down -v
```

#### 验证 Prometheus 抓取目标
确保以下独立指标端口已按规范暴露：Collector:9092 / Hot:9094 / Cold:9095 / Broker:9096。

```bash
# 查看 Prometheus targets 列表
curl -s http://localhost:9090/api/v1/targets | jq '.data.activeTargets[].labels.job'

# 样例查询：最近5分钟 ClickHouse 写入错误速率
curl -G http://localhost:9090/api/v1/query --data-urlencode \
  "query=rate(marketprism_storage_clickhouse_insert_errors_total[5m])"
```

## ⚙️ 配置

服务支持统一配置加载器（可选）。当前版本默认使用 main.py 内置配置；如需启用统一配置加载器，将在后续版本提供对应 YAML。

### 默认配置

```yaml
server:
  host: "0.0.0.0"
  port: 8082

logging:
  level: "INFO"

cors:
  enabled: true
```

## 🔐 可选中间件开关（默认关闭）

通过环境变量按需启用认证与输入验证中间件（不设置则保持简单运行）：

- MARKETPRISM_ENABLE_AUTH=false|true
- MARKETPRISM_ENABLE_VALIDATION=false|true

示例：

```bash
# 启动时开启认证与验证
export MARKETPRISM_ENABLE_AUTH=true
export MARKETPRISM_ENABLE_VALIDATION=true
python main.py

# 访问受保护接口（使用 API Key 放行）
curl -H "X-API-Key: mp-monitoring-key-2024" http://localhost:8082/api/v1/alerts
```

说明：
- 公开端点无需认证：/health、/（以及 /login）
- 若需要 Bearer Token，可先调用 /login 获取 token，再以 Authorization: Bearer <token> 访问
- 示例 API Key 默认为 mp-monitoring-key-2024，可通过环境变量 MONITORING_API_KEY 覆盖


## 📈 性能指标

基于完整测试的性能表现：

- **QPS**: 2,960 (平均)
- **响应时间**: 3.8ms (平均)
- **P95响应时间**: <10ms
- **P99响应时间**: <17ms
- **成功率**: 100%
- **CPU使用率**: 7.3% (平均)
- **内存使用率**: 30.6% (平均)
- **服务可用性**: 100%

## 🔧 开发

### 项目结构

```
services/monitoring-alerting/
├── main.py                 # 唯一入口
├── requirements.txt        # 依赖
├── Dockerfile              # 镜像
├── docker-compose.yml      # 监控栈编排（Prometheus/Alertmanager/Grafana/Blackbox/DingTalk）
├── README.md               # 文档
├── src/                    # 运行时 Python 模块
│   ├── auth.py
│   ├── validation.py
│   └── ssl_config.py
├── config/                 # 配置（子目录分类）
│   ├── prometheus/{prometheus.yml, alerts.yml}
│   ├── alertmanager/alertmanager.yml
│   ├── blackbox/blackbox.yml
│   └── grafana/
│       ├── provisioning/{dashboards, datasources}
│       └── dashboards/marketprism-core.json
├── tests/
│   └── integration/...
├── temp/                   # 临时脚本与临时测试
│   ├── health_check.py
│   ├── simple_test.py
│   └── test_basic_service.py
└── deprecated/             # 历史/弃用
    ├── main_before_security.py
    ├── main_old.py
    ├── main_secure.py
    ├── main_secure_v2.py
    └── start_service.py
```

### 依赖说明

重构后的服务使用最小化依赖：

- `aiohttp`: 高性能异步Web框架
- `aiohttp-cors`: CORS支持
- `structlog`: 结构化日志
- `PyYAML`: 配置文件解析
- `python-dateutil`: 时间处理


### Docker Compose 端到端验证（本地）

前置条件：
- 已安装 Docker Engine 与 Compose v2（建议 Docker ≥ 27，Compose ≥ 2.20）
- 端口未被占用：3000(Grafana) / 9090(Prometheus) / 9093(Alertmanager) / 9115(Blackbox)

快速检查：
```bash
docker --version
docker compose version
```

启动/验证/清理（建议在模块根目录执行）：
```bash
cd services/monitoring-alerting
# 启动监控栈
docker compose up -d
# 查看容器
docker compose ps
# 健康检查（各组件）
curl http://localhost:9090/-/healthy        # Prometheus: HEALTHY
curl http://localhost:9093/-/healthy        # Alertmanager: OK
curl http://localhost:9115/-/healthy        # Blackbox Exporter: OK
curl http://localhost:3000/api/health       # Grafana: {"database":"ok"}
# Prometheus 目标（截断展示）
curl 'http://localhost:9090/api/v1/targets?state=active' | jq '.data.activeTargets | length'
# Grafana 数据源 & 仪表盘（默认管理员账号：admin/admin）
curl -u admin:admin http://localhost:3000/api/datasources | jq '.[].name'
curl -u admin:admin 'http://localhost:3000/api/search?query=marketprism' | jq '.[].title'
# 采集关键日志
docker compose logs --tail=100 prometheus
docker compose logs --tail=100 grafana
# 验证完成后清理
docker compose down -v
```

常见问题（FAQ）：
- 端口冲突：按照约定应 kill 占用进程，不要改端口。
- Grafana 仪表盘未出现：首次启动可能需 10~20s 完成 provisioning；可查看 `grafana` 容器日志含有 `provisioned` 关键字。
- Linux 下 `host.docker.internal` 无法解析：可改为宿主机 IP，或在 Prometheus 配置中临时替换 targets；我们的配置默认使用 `host.docker.internal`。
- 无法访问 Docker：请确认当前用户在 `docker` 组或以具备权限的用户执行。
- 无法连通被监控服务：Prometheus/Blackbox 的 targets 指向宿主机服务端口，需确保相应服务已启动。

## 🧪 测试

### 健康检查

```bash
curl http://localhost:8082/health
```

### API测试

```bash
# 获取告警列表
curl http://localhost:8082/api/v1/alerts

# 获取告警规则
curl http://localhost:8082/api/v1/alerts/rules

# 获取Prometheus指标
curl http://localhost:8082/metrics
```

### 性能测试

使用提供的测试脚本：

```bash
python ../../test_api_endpoints.py
python ../../test_performance.py
```

## 🔄 版本历史

### v2.0.0 (2025-06-27) - 重构版本

- ✅ 简化服务架构，专注核心功能
- ✅ 移除未实现的异常检测和故障预测API
- ✅ 优化Grafana集成支持
- ✅ 最小化依赖，提升性能
- ✅ 完善API文档和测试覆盖

### v1.0.0 - 初始版本

- 包含完整功能规划但部分未实现
- 复杂的依赖结构
- 集成多个外部系统

## 🤝 贡献

1. Fork项目
2. 创建功能分支
3. 提交更改
4. 创建Pull Request

## 📄 许可证

MarketPrism项目许可证

---

**重构完成**: 2025-06-27
**版本**: 2.0.0
**状态**: 生产就绪
