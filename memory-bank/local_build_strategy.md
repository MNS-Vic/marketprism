# MarketPrism 本地构建策略规范

## 📋 文档概述

本文档详细定义了MarketPrism项目的**本地构建优先开发策略**，包括构建层级、实施规范、性能要求和最佳实践。

## 🎯 核心理念

**本地构建优先，网络依赖最小化**
- 确保开发环境的稳定性和高效性
- 减少对外部网络的依赖
- 提供一致的跨平台开发体验
- 最大化开发效率和构建速度

## 📦 构建策略层级

### 🥇 **优先级1：完全离线构建**

#### Go服务本地构建
```bash
# 使用本地构建脚本
./scripts/local_build.sh go-collector
./scripts/local_build.sh data-normalizer
```

**特点**：
- ✅ 无网络依赖
- ✅ 构建时间：10-30秒
- ✅ 稳定性：极高
- ✅ 编译产物：保存到 `bin/` 目录

**环境要求**：
```bash
export GOPROXY=direct     # 离线模式
export GOSUMDB=off        # 禁用校验
export GO111MODULE=on     # 启用模块
export CGO_ENABLED=0      # 静态编译
```

#### Docker离线构建
```bash
# 使用离线Dockerfile
docker build -f Dockerfile.offline -t marketprism:local .
```

**特点**：
- ✅ 基于最小基础镜像
- ✅ 构建时间：<30秒
- ✅ 镜像大小：<50MB
- ✅ 适用于测试和演示

### 🥈 **优先级2：本地缓存构建**

#### 依赖预构建
```bash
# 一次性预构建（联网环境）
./scripts/prebuild_images.sh
```

**流程**：
1. 首次联网下载所有依赖
2. 构建基础镜像缓存
3. 后续使用缓存快速构建

#### 缓存复用构建
```bash
# 使用缓存快速构建
docker build --cache-from marketprism:deps -t marketprism:app .
```

**特点**：
- 🟡 首次需要网络连接
- ✅ 后续完全离线
- ✅ 构建时间：30秒-2分钟
- ✅ 稳定性：高

### 🥉 **优先级3：开发环境（零构建）**

#### 代码挂载模式
```bash
# 启动开发环境
docker-compose -f docker-compose.dev.yml up -d
```

**特点**：
- ✅ 启动时间：<10秒
- ✅ 代码热重载
- ✅ 无需重建
- ✅ 最佳开发体验

**配置要求**：
```yaml
# docker-compose.dev.yml
volumes:
  - ./services:/app/services    # 直接挂载源码
  - ./config:/app/config        # 挂载配置
```

### ⚠️ **备选方案：网络优化构建**

```bash
# 仅在网络环境良好时使用
./scripts/build_with_optimal_config.sh
```

**使用场景**：
- 首次环境设置
- 依赖版本更新
- 网络环境良好且稳定

## 🚨 防止虚假GitHub导入陷阱

**⚠️ 重要警告**：项目中发现大量虚假GitHub导入路径，如：
- `github.com/marketprism/services/go-collector/internal/nats`
- `github.com/marketprism/go-collector/internal/models`

这些路径会导致Go尝试从网络下载不存在的依赖，严重违背本地构建策略！

### 识别和修复虚假路径

```bash
# 🔍 检测虚假路径
grep -r "github.com/marketprism/services" --include="*.go" services/

# 🔧 自动修复（推荐）
./scripts/fix_github_imports.sh

# ✅ 验证修复结果
./scripts/local_build.sh go-collector
```

**详细规范**：参见 [虚假GitHub导入陷阱防护规范](./github_import_trap_prevention.md)

### 📚 重要技术教训

在实施本地构建策略过程中，我们获得了重要的技术教训。**强烈建议所有开发者阅读**：

- **[核心技术教训文档](./core_lessons_learned.md)** - 🔥 包含5个关键技术认知
- **[go-collector修复报告](./go_collector_fix_report.md)** - 实际修复案例和详细过程

**核心要点预览**：
1. 本地构建 = 完整模块路径 + replace指令 ≠ 相对路径导入
2. Go模块系统不支持 `"./internal/package"` 这样的相对路径
3. 虚假GitHub路径（如 `github.com/marketprism/services/*`）是最大陷阱

## 🛠️ 实施规范

### 开发流程规范

#### 1. 新项目初始化
```bash
# 克隆项目
git clone <repository-url>
cd marketprism

# 设置Go环境（本地构建）
export GOPROXY=direct
export GOSUMDB=off
export GO111MODULE=on

# 移除网络依赖配置
mv ~/.docker/daemon.json ~/.docker/daemon.json.bak
```

#### 2. 日常开发流程
```bash
# 选择构建方式（按优先级）

# 方式1：本地编译（推荐）
./scripts/local_build.sh go-collector

# 方式2：开发环境（推荐）
docker-compose -f docker-compose.dev.yml up -d

# 方式3：离线容器构建
docker build -f Dockerfile.offline -t marketprism:local .
```

#### 3. 测试验证流程
```bash
# 本地离线测试（推荐）
./scripts/run_local_tests.sh

# 离线数据流测试
python tests/test_data_flow_offline.py

# 传统测试
pytest tests/unit/
```

### 文件结构规范

```
marketprism/
├── services/
│   ├── go-collector/
│   │   ├── bin/           # 本地构建产物（重要）
│   │   ├── vendor/        # Go依赖缓存
│   │   └── cmd/           # Go源码
│   └── data-normalizer/
│       ├── bin/           # 构建产物
│       └── cmd/           # 源码
├── scripts/
│   ├── local_build.sh     # 本地构建脚本（核心）
│   ├── prebuild_images.sh # 依赖预构建
│   └── run_local_tests.sh # 本地测试
├── Dockerfile.offline     # 离线构建文件（核心）
├── docker-compose.dev.yml # 开发环境配置（核心）
└── memory-bank/
    └── local_build_strategy.md # 本规范文档
```

## 📊 性能要求与基准

### 构建性能要求

| 构建方式 | 首次构建 | 增量构建 | 网络依赖 | 稳定性要求 |
|----------|----------|----------|----------|------------|
| **本地离线** | ≤30秒 | ≤10秒 | 无 | 极高 |
| **开发挂载** | ≤10秒 | 0秒 | 无 | 极高 |
| **缓存构建** | ≤2分钟 | ≤30秒 | 首次 | 高 |
| **网络构建** | ≤5分钟 | ≤2分钟 | 依赖 | 中等 |

### 实际性能基准

基于实际测试结果：
- **本地离线构建**：Go编译 10-15秒，Docker构建 <30秒
- **开发环境启动**：容器启动 <10秒，代码修改 0秒延迟
- **构建稳定性**：本地构建 100% 成功率，网络构建 <70% 成功率

## ✅ 质量保证

### 构建验证检查清单

#### Go本地构建验证
- [ ] 编译无错误
- [ ] 二进制文件生成到 `bin/` 目录
- [ ] 可执行权限正确
- [ ] 版本信息显示正确

#### Docker构建验证
- [ ] 镜像构建成功
- [ ] 容器启动正常
- [ ] 健康检查通过
- [ ] 基础功能测试通过

#### 开发环境验证
- [ ] 容器启动时间 <10秒
- [ ] 代码挂载正常
- [ ] 配置文件加载正确
- [ ] 依赖服务连接正常

### 错误处理规范

#### 常见错误及解决方案

1. **Go模块依赖错误**
```bash
# 解决方案：使用本地构建
./scripts/local_build.sh go-collector
```

2. **Docker网络超时**
```bash
# 解决方案：使用离线构建
docker build -f Dockerfile.offline -t marketprism:local .
```

3. **缓存失效问题**
```bash
# 解决方案：清理后重建
docker system prune -f
./scripts/local_build.sh go-collector
```

## 🔄 持续改进

### 性能优化目标

#### 短期目标（1个月）
- 本地构建时间优化至 <15秒
- 开发环境启动优化至 <5秒
- 构建脚本错误处理完善

#### 中期目标（3个月）
- CI/CD流水线集成本地构建策略
- 跨平台兼容性验证和优化
- 构建性能监控体系建立

#### 长期目标（6个月）
- 构建缓存策略进一步优化
- 多架构支持（ARM64、AMD64）
- 社区最佳实践推广

### 监控和度量

#### 关键指标
- **构建成功率**：目标 >99%
- **构建时间**：目标本地构建 <15秒
- **开发启动时间**：目标 <5秒
- **资源使用**：目标内存 <2GB，磁盘 <5GB

#### 监控方法
- 构建时间自动记录
- 成功率统计分析
- 资源使用监控
- 开发者反馈收集

## 🎓 团队培训和推广

### 培训计划

#### 新成员入职培训
1. **本地构建策略概述**：理解设计理念
2. **实践操作**：掌握常用构建命令
3. **故障排除**：学会解决常见问题
4. **最佳实践**：了解开发流程规范

#### 持续培训
- 定期分享构建优化技巧
- 新工具和脚本使用培训
- 性能优化案例分享

### 推广策略

#### 内部推广
- 技术分享会演示
- 文档和教程完善
- 工具易用性优化

#### 外部推广
- 开源社区分享
- 技术博客文章
- 会议演讲展示

---

## 📚 相关文档

- [README.md](../README.md) - 项目整体说明
- [techContext.md](./techContext.md) - 技术上下文
- [activeContext.md](./activeContext.md) - 当前活动上下文
- [DOCKER_OPTIMIZATION_GUIDE.md](../DOCKER_OPTIMIZATION_GUIDE.md) - Docker优化指南

---

**规范版本**：v1.0  
**最后更新**：2025-05-24  
**负责人**：开发团队  
**审批状态**：已生效 