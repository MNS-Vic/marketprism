# data_archiver_service 职责混乱分析

## 当前职责（违背单一责任原则）

### 1. 数据存储职责
**文件**: `storage_manager.py` (978行)
- ClickHouse热/冷存储管理
- 数据查询路由
- 存储状态监控

### 2. 数据归档职责  
**文件**: `archiver.py` (918行)
- 热存储到冷存储的数据迁移
- 批量数据处理
- 归档验证和状态跟踪

### 3. 任务调度职责
**文件**: `service.py` (1031行)
```python
# Cron调度系统
self.archive_schedule = "0 2 * * *"  # 每天凌晨2点归档
self.cleanup_schedule = "0 3 * * *"  # 每天凌晨3点清理

# 调度循环
async def _run_service_loop_async(self):
    while self.running:
        # 检查是否需要执行归档任务
        # 检查是否需要执行清理任务
```

### 4. 消息处理职责
```python
# NATS消息队列处理
async def _handle_trade_message(self, msg):
async def _handle_depth_message(self, msg):
async def _handle_funding_message(self, msg):
```

### 5. 监控和运维职责
```python
def health_check(self) -> Dict[str, Any]:
    """健康检查"""
    
def get_metrics(self) -> Dict[str, Any]:
    """指标收集"""
    
async def _send_heartbeat(self):
    """心跳监控"""
```

## 为什么会出现这种设计？

### 1. 单体思维惯性
- 将相关功能放在一起，便于开发和调试
- 减少服务间通信的复杂性

### 2. 业务领域混淆
- 将"数据生命周期管理"当作一个整体业务域
- 没有区分存储、调度、监控的不同技术域

### 3. 早期快速开发
- 为了快速实现功能，将多个职责放在一个服务中
- 缺乏长期架构规划

## 正确的微服务划分

按照**单一责任原则**和**业务能力**划分：

### 方案1：细粒度拆分
```
├── storage-service/          # 纯数据存储服务
│   ├── hot_storage_manager   # 热存储管理
│   ├── cold_storage_manager  # 冷存储管理
│   └── query_router          # 查询路由
│
├── archiver-service/         # 纯数据归档服务
│   ├── data_migrator         # 数据迁移
│   ├── archive_validator     # 归档验证
│   └── archive_tracker       # 状态跟踪
│
├── scheduler-service/        # 通用调度服务
│   ├── cron_manager          # Cron任务管理
│   ├── task_executor         # 任务执行器
│   └── schedule_config       # 调度配置
│
└── monitoring-service/       # 通用监控服务
    ├── health_checker        # 健康检查
    ├── metrics_collector     # 指标收集
    └── alert_manager         # 告警管理
```

### 方案2：领域驱动拆分（推荐）
```
├── data-lifecycle-service/   # 数据生命周期管理
│   ├── archiver_core         # 归档核心逻辑
│   └── lifecycle_policy      # 生命周期策略
│
├── task-scheduler/           # 任务调度器
│   ├── job_scheduler         # 通用任务调度
│   └── cron_executor         # Cron执行器
│
├── storage-gateway/          # 存储网关
│   ├── unified_storage       # 统一存储接口
│   └── query_router          # 查询路由
│
└── observability-platform/  # 可观测性平台
    ├── monitoring            # 监控
    ├── logging               # 日志
    └── tracing               # 链路追踪
```

## 当前代码中的设计缺陷例证

### 服务启动时的职责混乱：
```python
# service.py - 一个类做太多事情
class DataArchiverService:
    def __init__(self):
        # 存储管理
        self.archiver = DataArchiver(config_path)
        self.storage_manager = StorageManager()
        
        # 调度管理
        self.archive_schedule = "0 2 * * *"
        self.cleanup_schedule = "0 3 * * *"
        
        # 消息处理
        self.nats_client = self._init_nats_client()
        self.message_handlers = {}
        
        # 监控管理
        self.heartbeat_interval = 60
```

### 违背开闭原则：
- 如果要修改调度策略，需要修改数据归档服务
- 如果要更换存储后端，影响调度和监控逻辑
- 如果要增加新的数据源，需要修改整个服务

## 改进建议

### 立即改进（最小侵入）：
将现有服务重构为更清晰的内部模块：
```python
class DataArchiverService:
    def __init__(self):
        # 职责分离
        self.storage_component = StorageComponent()
        self.scheduler_component = SchedulerComponent()
        self.monitoring_component = MonitoringComponent()
        self.messaging_component = MessagingComponent()
```

### 长期重构（微服务拆分）：
1. 提取调度功能到独立的`task-scheduler`服务
2. 提取监控功能到`observability-platform`
3. 将存储逻辑整合到统一存储管理器
4. 保留`data-archiver`作为纯归档业务逻辑

## 微服务设计原则回顾

### 单一责任原则
- 每个服务只负责一个业务能力
- 修改一个服务的理由只有一个

### 业务能力对齐
- 按业务能力而非技术层面划分
- 服务边界与业务边界一致

### 自治性
- 服务可以独立开发、部署、扩展
- 最小化服务间的耦合