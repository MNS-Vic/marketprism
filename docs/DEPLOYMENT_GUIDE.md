# MarketPrism 部署指南

## 🚨 重要使用提醒

### **常见错误及解决方案**

#### **1. 配置文件错误**
```yaml
# ❌ 错误配置
data_types: ["trades", "funding_rate"]  # "trades"是错误的

# ✅ 正确配置  
data_types: ["trade", "funding_rate"]   # "trade"是正确的枚举值
```

**常见数据类型名称错误**：
- ❌ `"trades"` → ✅ `"trade"`
- ❌ `"positions"` → ✅ `"lsr_top_position"`
- ❌ `"accounts"` → ✅ `"lsr_all_account"`

#### **2. 系统启动问题**
- **现象**: 启动后无输出或卡死
- **原因**: 配置文件中数据类型名称错误
- **解决**: 检查配置文件中所有data_types字段

#### **3. NATS连接问题**
- **现象**: 启动失败，提示NATS连接错误
- **解决**: 确保NATS服务器运行在端口4222

## 📋 启动前检查清单

### **必要条件**
- [ ] NATS服务器正在运行 (`systemctl status nats-server`)
- [ ] Python虚拟环境已激活
- [ ] 配置文件语法正确
- [ ] 数据类型名称匹配系统枚举
- [ ] 网络连接正常

### **系统资源**
- [ ] 内存 > 2GB (推荐4GB+)
- [ ] CPU > 2核心 (推荐4核心+)
- [ ] 磁盘空间 > 10GB
- [ ] 网络带宽稳定

## 🚀 渐进式部署策略

### **阶段1: 基础验证**
```yaml
data_types: ["volatility_index"]  # 仅Deribit波动率指数
```
- 验证系统基础功能
- 确认配置文件正确性
- 检查NATS连接

### **阶段2: 核心数据**
```yaml
data_types: ["trade", "funding_rate"]
```
- 添加实时交易数据
- 添加8小时资金费率数据
- 验证多manager协调

### **阶段3: 中频数据**
```yaml
data_types: ["trade", "funding_rate", "open_interest", "liquidation"]
```
- 添加5分钟未平仓量数据
- 添加实时强平数据
- 监控系统资源使用

### **阶段4: 高频数据**
```yaml
data_types: ["trade", "funding_rate", "open_interest", "liquidation", "lsr_top_position"]
```
- 添加10秒多空持仓比例数据
- 注意API速率限制
- 监控网络请求频率

### **阶段5: 完整配置**
```yaml
data_types: ["trade", "funding_rate", "open_interest", "liquidation", "lsr_top_position", "lsr_all_account"]
```
- 所有数据类型启用
- 全面监控系统性能
- 准备生产环境部署

## 🔧 启动命令

### **开发环境**
```bash
cd services/data-collector
source ../../venv/bin/activate
python main.py
```

### **生产环境**
```bash
cd services/data-collector
../../venv/bin/python main.py
```

## 📊 监控指标

### **系统资源监控**
- 内存使用率 < 80%
- CPU使用率 < 70%
- 网络延迟 < 100ms
- 错误率 < 1%

### **数据质量监控**
- WebSocket连接稳定性
- API请求成功率
- 数据收集完整性
- NATS消息发布成功率

## 🆘 故障排除

### **启动失败**
1. 检查配置文件语法
2. 验证数据类型名称
3. 确认NATS服务器状态
4. 检查虚拟环境激活

### **数据收集异常**
1. 检查网络连接
2. 验证交易所API访问
3. 监控API速率限制
4. 检查系统资源使用

### **性能问题**
1. 减少启用的数据类型
2. 增加系统资源配置
3. 优化网络连接
4. 调整收集频率

## 📞 技术支持

如遇到问题，请提供：
1. 完整的错误日志
2. 系统配置信息
3. 资源使用情况
4. 网络连接状态

---
**MarketPrism Team**  
最后更新: 2025-07-30
