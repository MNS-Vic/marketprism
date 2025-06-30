# MarketPrism 专业监控可视化仪表板

## 概述

MarketPrism 监控仪表板是一个现代化的Web界面，为MarketPrism量化交易系统提供全面的监控和可视化功能。该仪表板采用企业级设计，支持实时数据更新、交互式图表和专业的监控界面。

## 功能特性

### 🎯 核心功能
- **实时监控仪表板** - 系统概览和关键指标
- **系统性能监控** - CPU、内存、磁盘使用率监控
- **服务健康监控** - 微服务状态和性能跟踪
- **交易数据监控** - 实时交易数据和市场信息
- **告警管理系统** - 智能告警和通知管理

### 🎨 界面特性
- **现代化设计** - 基于Bootstrap 5的响应式界面
- **实时数据更新** - WebSocket实时数据推送
- **交互式图表** - 基于ECharts和Chart.js的专业图表
- **多主题支持** - 支持明暗主题切换
- **移动端适配** - 完全响应式设计

### 📊 监控页面

#### 1. 总览仪表板 (`/dashboard`)
- 系统资源使用率概览
- 服务健康状态汇总
- 实时性能趋势图表
- 交易数据概览
- 最新告警信息

#### 2. 系统监控 (`/system`)
- CPU使用率仪表盘
- 内存使用监控
- 磁盘空间监控
- 系统性能历史趋势
- 进程监控列表
- 网络流量统计
- 系统温度监控

#### 3. 服务监控 (`/services`)
- 微服务状态概览
- 服务响应时间趋势
- 服务依赖关系图
- 实时日志查看
- 服务性能指标
- 服务操作管理

#### 4. 交易监控 (`/trading`)
- 实时价格K线图
- 订单簿数据显示
- 交易所连接状态
- WebSocket连接监控
- 数据流量统计
- 最新交易记录

#### 5. 告警管理 (`/alerts`)
- 活跃告警列表
- 告警趋势分析
- 告警规则管理
- 通知设置配置
- 告警历史记录

## 技术架构

### 后端技术栈
- **Python 3.8+** - 主要开发语言
- **aiohttp** - 异步Web框架
- **aiohttp-jinja2** - 模板引擎
- **WebSocket** - 实时数据通信
- **structlog** - 结构化日志
- **PyYAML** - 配置文件解析

### 前端技术栈
- **Bootstrap 5** - UI框架
- **ECharts** - 专业图表库
- **Chart.js** - 轻量级图表
- **Font Awesome** - 图标库
- **WebSocket API** - 实时数据接收

### 架构特点
- **微服务集成** - 与MarketPrism微服务生态无缝集成
- **实时数据流** - WebSocket实现毫秒级数据更新
- **模块化设计** - 页面和功能模块化开发
- **可扩展架构** - 支持自定义监控指标和页面

## 安装部署

### 快速启动

1. **使用启动脚本（推荐）**
```bash
# 在项目根目录执行
./start-monitoring-dashboard.sh
```

2. **手动启动**
```bash
# 激活虚拟环境
source venv/bin/activate

# 安装依赖
pip install aiohttp aiohttp-jinja2 jinja2 pyyaml structlog

# 启动服务
cd services/monitoring-dashboard
python main.py
```

### 配置文件

在 `config/services.yaml` 中配置监控仪表板：

```yaml
monitoring-dashboard:
  port: 8086
  monitoring_service_url: "http://localhost:8083"
  data_collector_url: "http://localhost:8081"
```

### 访问地址

启动成功后，可通过以下地址访问：

- **主仪表板**: http://localhost:8086/dashboard
- **系统监控**: http://localhost:8086/system
- **服务监控**: http://localhost:8086/services
- **交易监控**: http://localhost:8086/trading
- **告警管理**: http://localhost:8086/alerts

## API接口

### REST API

- `GET /api/system-overview` - 获取系统概览数据
- `GET /api/services-status` - 获取服务状态数据
- `GET /api/alerts` - 获取告警信息
- `GET /api/metrics-history` - 获取指标历史数据
- `GET /api/trading-data` - 获取交易数据

### WebSocket API

- `ws://localhost:8086/ws` - 实时数据推送

WebSocket消息格式：
```json
{
  "type": "data_update",
  "timestamp": "2024-01-31T10:30:00Z",
  "data": {
    "system_overview": {...},
    "services_status": {...},
    "alerts": [...],
    "trading_data": {...}
  }
}
```

## 开发指南

### 项目结构

```
services/monitoring-dashboard/
├── main.py                 # 主服务文件
├── templates/              # Jinja2模板
│   ├── base.html          # 基础模板
│   ├── dashboard.html     # 主仪表板
│   ├── system.html        # 系统监控
│   ├── services.html      # 服务监控
│   ├── trading.html       # 交易监控
│   └── alerts.html        # 告警管理
├── static/                # 静态资源
│   └── css/
│       └── dashboard.css  # 自定义样式
└── README.md              # 文档
```

### 自定义开发

#### 添加新的监控页面

1. 在 `templates/` 目录创建新的HTML模板
2. 在 `main.py` 中添加路由处理器
3. 在 `base.html` 中添加导航链接

#### 添加新的数据源

1. 在 `MonitoringDashboard` 类中添加数据更新方法
2. 在 `_data_update_loop` 中调用新的更新方法
3. 在前端JavaScript中处理新的数据类型

#### 自定义图表

使用ECharts或Chart.js添加新的图表类型：

```javascript
// ECharts示例
const chart = echarts.init(document.getElementById('chart-container'));
chart.setOption({
    // 图表配置
});

// Chart.js示例
const ctx = document.getElementById('chart-canvas').getContext('2d');
const chart = new Chart(ctx, {
    // 图表配置
});
```

## 性能优化

### 数据缓存
- 监控数据在内存中缓存，减少API调用
- 历史数据限制在合理范围内（通常100个数据点）
- WebSocket连接复用，避免频繁建立连接

### 前端优化
- 图表数据增量更新，避免重绘整个图表
- 使用CSS3动画和过渡效果
- 响应式图片和资源懒加载

### 后端优化
- 异步I/O处理，提高并发性能
- 数据更新频率可配置（默认5秒）
- 自动清理断开的WebSocket连接

## 故障排除

### 常见问题

1. **端口被占用**
   ```bash
   # 查找占用进程
   lsof -i :8086
   # 终止进程
   kill -9 <PID>
   ```

2. **依赖安装失败**
   ```bash
   # 升级pip
   pip install --upgrade pip
   # 清理缓存
   pip cache purge
   ```

3. **WebSocket连接失败**
   - 检查防火墙设置
   - 确认监控服务正常运行
   - 查看浏览器控制台错误信息

4. **数据不更新**
   - 检查监控服务API是否可访问
   - 确认配置文件中的URL正确
   - 查看服务日志获取详细错误信息

### 日志查看

服务运行时会输出详细的日志信息，包括：
- WebSocket连接状态
- 数据更新状态
- API调用结果
- 错误和异常信息

## 扩展功能

### 计划中的功能
- [ ] 用户认证和权限管理
- [ ] 自定义仪表板配置
- [ ] 数据导出功能
- [ ] 移动端App
- [ ] 多语言支持
- [ ] 主题自定义

### 集成建议
- 与Grafana集成进行高级分析
- 与Prometheus集成进行指标收集
- 与ELK Stack集成进行日志分析
- 与钉钉/企业微信集成进行告警通知

## 贡献指南

欢迎提交Issue和Pull Request来改进监控仪表板。

### 开发环境设置
1. Fork项目仓库
2. 创建功能分支
3. 进行开发和测试
4. 提交Pull Request

### 代码规范
- 遵循PEP 8 Python代码规范
- 使用有意义的变量和函数名
- 添加适当的注释和文档
- 编写单元测试

## 许可证

本项目采用MIT许可证，详见LICENSE文件。

## 联系方式

如有问题或建议，请通过以下方式联系：
- 项目Issue: GitHub Issues
- 邮箱: admin@marketprism.com

---

**MarketPrism 监控仪表板** - 专业的量化交易系统监控解决方案