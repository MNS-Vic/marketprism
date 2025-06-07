# MarketPrism 统一API代理架构设计

## 🏗️ 系统架构总览

### **核心设计理念**
- **统一收口**：所有交易所API请求经过统一代理
- **智能路由**：根据IP资源和限制智能选择最佳路径
- **弹性容错**：自动处理429/418错误和IP切换
- **零侵入**：现有代码无需修改即可享受保护

### **整体架构图**

```mermaid
graph TB
    subgraph "MarketPrism Services"
        A[Python Collector] --> M[API Proxy]
        B[Monitoring Service] --> M
        C[Trading Service] --> M
        D[Data Archiver] --> M
    end
    
    subgraph "API Proxy Core"
        M --> E[Request Router]
        E --> F[Weight Calculator]
        E --> G[IP Manager]
        E --> H[Rate Limiter]
        F --> I[Dynamic Weight Engine]
        G --> J[Health Monitor]
        H --> K[Error Handler]
    end
    
    subgraph "IP Resource Pool"
        G --> L[IP-1: 192.168.1.100]
        G --> N[IP-2: 192.168.1.101]
        G --> O[IP-3: 192.168.1.102]
    end
    
    subgraph "Exchange APIs"
        L --> P[Binance API]
        N --> Q[OKX API]
        O --> R[Deribit API]
    end
    
    subgraph "Monitoring & Analytics"
        K --> S[Request Statistics]
        J --> T[Health Reports]
        S --> U[Alert System]
        T --> U
    end
    
    style M fill:#e1f5fe
    style E fill:#f3e5f5
    style G fill:#e8f5e8
    style K fill:#fff3e0
```

## 📊 核心组件设计

### **1. API代理核心 (ExchangeAPIProxy)**

```python
class ExchangeAPIProxy:
    """统一API代理核心组件"""
    
    # 核心职责
    - 请求路由和分发
    - IP资源管理和选择
    - 权重计算和限制
    - 错误处理和恢复
    - 实时监控和统计
```

**组件关系图：**
```mermaid
classDiagram
    class ExchangeAPIProxy {
        +ProxyMode mode
        +Dict~str,IPResource~ ip_resources
        +DynamicWeightCalculator weight_calculator
        +UnifiedSessionManager session_manager
        +request(exchange, method, endpoint, params)
        +get_status()
        +get_health_report()
    }
    
    class IPResource {
        +str ip
        +int current_weight
        +int max_weight_per_minute
        +float health_score
        +datetime banned_until
        +consume_weight(weight)
        +handle_rate_limit_response(status, retry_after)
    }
    
    class DynamicWeightCalculator {
        +calculate_weight(exchange, endpoint, params)
        +get_optimization_suggestions()
    }
    
    class ProxyAdapter {
        +use_api_proxy(exchange)
        +get_proxy_session(exchange)
        +enable_global_proxy()
    }
    
    ExchangeAPIProxy --> IPResource
    ExchangeAPIProxy --> DynamicWeightCalculator
    ExchangeAPIProxy --> ProxyAdapter
```

### **2. 请求处理流程**

```mermaid
sequenceDiagram
    participant Client as 业务服务
    participant Proxy as API代理
    participant Weight as 权重计算器
    participant IPMgr as IP管理器
    participant Exchange as 交易所API
    
    Client->>Proxy: 发送API请求
    Proxy->>Weight: 计算请求权重
    Weight-->>Proxy: 返回权重值
    Proxy->>IPMgr: 选择最佳IP
    IPMgr-->>Proxy: 返回可用IP
    
    alt IP权重充足
        Proxy->>Exchange: 发送请求
        Exchange-->>Proxy: 返回成功响应
        Proxy-->>Client: 返回结果
    else IP权重不足
        Proxy->>IPMgr: 尝试其他IP
        IPMgr-->>Proxy: 返回备用IP
        Proxy->>Exchange: 重新发送
    else 收到429警告
        Exchange-->>Proxy: 429 Too Many Requests
        Proxy->>Proxy: 解析retry_after
        Proxy->>Proxy: 等待/切换IP
        Proxy->>Exchange: 重试请求
    else 收到418封禁
        Exchange-->>Proxy: 418 IP Banned
        Proxy->>IPMgr: 标记IP不可用
        Proxy->>IPMgr: 切换到其他IP
        Proxy->>Exchange: 使用新IP请求
    end
```

### **3. IP资源管理架构**

```mermaid
graph LR
    subgraph "IP资源池"
        A[IP-1] --> A1[权重: 1500/6000]
        A --> A2[健康分数: 0.95]
        A --> A3[状态: 可用]
        
        B[IP-2] --> B1[权重: 5800/6000]
        B --> B2[健康分数: 0.75]
        B --> B3[状态: 接近限制]
        
        C[IP-3] --> C1[权重: 0/6000]
        C --> C2[健康分数: 0.1]
        C --> C3[状态: 被封禁至14:30]
    end
    
    subgraph "选择策略"
        D[健康分数权重: 70%]
        E[权重使用率: 30%]
        F[可用性检查]
    end
    
    A --> G[最佳选择]
    D --> G
    E --> G
    F --> G
```

### **4. 权重计算引擎**

```mermaid
graph TD
    A[API请求] --> B{识别交易所}
    B -->|Binance| C[Binance权重规则]
    B -->|OKX| D[OKX权重规则]
    B -->|Deribit| E[Deribit权重规则]
    
    C --> F[端点基础权重]
    C --> G[参数依赖权重]
    C --> H[批量操作权重]
    
    F --> I[权重计算]
    G --> I
    H --> I
    
    I --> J[优化建议生成]
    I --> K[最终权重值]
    
    subgraph "权重规则示例"
        L[ping: 1]
        M[ticker/24hr: 1-40]
        N[depth: 1-50]
        O[订单操作: 1-10]
    end
```

## 🔄 运行模式设计

### **1. 自动模式 (AUTO)**
```mermaid
graph LR
    A[启动代理] --> B[检测IP环境]
    B --> C{IP数量判断}
    C -->|单IP| D[切换到统一模式]
    C -->|多IP| E[切换到分布式模式]
    D --> F[单点统一管理]
    E --> G[负载均衡管理]
```

### **2. 统一模式 (UNIFIED)**
```mermaid
graph TB
    A[所有服务请求] --> B[统一代理入口]
    B --> C[权重汇总计算]
    C --> D[单IP资源管理]
    D --> E[统一限制控制]
    E --> F[交易所API]
    
    style B fill:#e1f5fe
    style D fill:#e8f5e8
```

### **3. 分布式模式 (DISTRIBUTED)**
```mermaid
graph TB
    A[服务A请求] --> D[IP-1]
    B[服务B请求] --> E[IP-2]
    C[服务C请求] --> F[IP-3]
    
    G[负载均衡器] --> D
    G --> E
    G --> F
    
    D --> H[Binance API]
    E --> I[OKX API]
    F --> J[Deribit API]
    
    style G fill:#f3e5f5
```

## 🛡️ 错误处理架构

### **错误处理流程图**
```mermaid
flowchart TD
    A[API请求] --> B[发送到交易所]
    B --> C{响应状态}
    
    C -->|200 OK| D[记录成功统计]
    C -->|429 Too Many Requests| E[解析retry_after]
    C -->|418 IP Banned| F[解析封禁时间]
    C -->|其他错误| G[通用错误处理]
    
    E --> H{有其他可用IP?}
    H -->|是| I[切换到其他IP]
    H -->|否| J[等待retry_after]
    
    F --> K[标记IP不可用]
    K --> L[设置恢复时间]
    L --> M{有其他可用IP?}
    M -->|是| N[切换到备用IP]
    M -->|否| O[等待IP恢复]
    
    I --> P[重试请求]
    J --> P
    N --> P
    O --> P
    
    P --> A
    
    D --> Q[更新健康分数]
    G --> R[记录错误统计]
```

### **IP健康管理**
```mermaid
graph LR
    subgraph "健康分数计算"
        A[成功请求 +0.01]
        B[429警告 ×0.8]
        C[418封禁 =0.1]
        D[超时错误 ×0.9]
    end
    
    subgraph "状态判断"
        E[健康分数 > 0.8: 优秀]
        F[健康分数 > 0.5: 良好]
        G[健康分数 > 0.2: 一般]
        H[健康分数 ≤ 0.2: 差]
    end
    
    A --> I[更新分数]
    B --> I
    C --> I
    D --> I
    I --> E
    I --> F
    I --> G
    I --> H
```

## 📊 监控与观测架构

### **监控数据流**
```mermaid
graph TB
    subgraph "数据收集"
        A[请求记录] --> D[统计引擎]
        B[错误记录] --> D
        C[性能指标] --> D
    end
    
    subgraph "指标计算"
        D --> E[成功率计算]
        D --> F[响应时间分析]
        D --> G[错误分布统计]
        D --> H[权重使用分析]
    end
    
    subgraph "报告生成"
        E --> I[实时状态报告]
        F --> I
        G --> J[健康诊断报告]
        H --> J
    end
    
    subgraph "告警系统"
        I --> K[阈值检查]
        J --> K
        K --> L[告警通知]
    end
    
    style D fill:#e1f5fe
    style K fill:#fff3e0
```

### **关键指标设计**
```mermaid
mindmap
  root((监控指标))
    基础指标
      总请求数
      成功请求数
      失败请求数
      平均响应时间
    
    速率限制指标
      429警告次数
      418封禁次数
      权重使用率
      IP切换次数
    
    健康指标
      IP健康分数
      服务可用性
      错误率趋势
      性能趋势
    
    业务指标
      各交易所请求分布
      各服务请求分布
      权重消耗分布
      峰值负载处理
```

## 🔧 配置架构设计

### **配置层次结构**
```mermaid
graph TD
    A[全局配置] --> B[交易所配置]
    A --> C[IP资源配置]
    A --> D[监控配置]
    
    B --> E[Binance配置]
    B --> F[OKX配置]
    B --> G[Deribit配置]
    
    C --> H[单IP模式配置]
    C --> I[多IP模式配置]
    
    D --> J[告警阈值]
    D --> K[报告间隔]
    
    subgraph "配置文件"
        L[api_proxy_config.yaml]
        M[dynamic_weight_config.yaml]
        N[exchange_configs/]
    end
```

### **配置继承关系**
```yaml
# 配置优先级：运行时参数 > 环境变量 > 配置文件 > 默认值

默认配置:
  mode: "auto"
  max_weight_per_minute: 6000
  health_check_interval: 60

环境配置:
  PROXY_MODE: "distributed"  # 覆盖默认mode
  
运行时配置:
  proxy = ExchangeAPIProxy(mode=ProxyMode.UNIFIED)  # 最高优先级
```

## 🚀 扩展架构设计

### **插件化扩展点**
```mermaid
graph LR
    subgraph "核心代理"
        A[ExchangeAPIProxy]
    end
    
    subgraph "扩展插件"
        B[权重计算插件]
        C[IP选择策略插件]
        D[错误处理插件]
        E[监控报告插件]
    end
    
    A --> B
    A --> C
    A --> D
    A --> E
    
    subgraph "自定义实现"
        F[CustomWeightCalculator]
        G[CustomIPSelector]
        H[CustomErrorHandler]
        I[CustomMonitor]
    end
    
    B -.-> F
    C -.-> G
    D -.-> H
    E -.-> I
```

### **水平扩展架构**
```mermaid
graph TB
    subgraph "服务集群"
        A[API代理实例-1] --> D[Redis协调器]
        B[API代理实例-2] --> D
        C[API代理实例-3] --> D
    end
    
    subgraph "共享状态"
        D --> E[全局权重状态]
        D --> F[IP封禁状态]
        D --> G[配置同步]
    end
    
    subgraph "负载均衡"
        H[请求分发器] --> A
        H --> B
        H --> C
    end
    
    style D fill:#e1f5fe
    style H fill:#f3e5f5
```

## 💡 设计原则总结

### **核心设计原则**

1. **单一职责**：每个组件只负责一个明确的功能
2. **开放封闭**：对扩展开放，对修改封闭
3. **依赖倒置**：依赖抽象而不是具体实现
4. **最小惊讶**：API设计符合直觉和约定
5. **渐进增强**：从简单开始，逐步增加复杂性

### **架构优势**

✅ **高内聚低耦合**：组件职责清晰，依赖关系简单
✅ **可测试性**：每个组件都可以独立测试
✅ **可扩展性**：支持插件化和水平扩展
✅ **可观测性**：完整的监控和诊断能力
✅ **容错性**：多层次的错误处理和恢复机制

### **性能特征**

- **低延迟**：本地路由决策，无额外网络开销
- **高吞吐**：支持连接复用和并发请求
- **自适应**：根据实际负载动态调整策略
- **可预测**：明确的权重计算和限制机制

这个架构设计确保了MarketPrism统一API代理既**简单优雅**又**功能强大**，为分布式交易所API管理提供了完整的解决方案！