# 🌐 OKX API代理配置操作手册

## 📋 概述

本手册详细说明如何配置代理以解决OKX API连接问题，确保MarketPrism能够稳定访问OKX交易所API。

## 🔍 问题诊断

### 常见OKX连接问题
1. **SSL连接错误**: `SSLEOFError: EOF occurred in violation of protocol`
2. **连接超时**: `ReadTimeoutError: Read timed out`
3. **地理位置限制**: 某些地区无法直接访问OKX API
4. **网络防火墙**: 企业网络可能阻止加密货币交易所访问

### 快速诊断命令
```bash
# 测试OKX API直连
curl -v https://www.okx.com/api/v5/public/time

# 运行OKX连接诊断
python scripts/okx_api_integration_optimizer.py

# 检查当前代理配置
cat config/proxy.yaml
```

## 🔧 代理配置方案

### 方案1: 本地代理服务器

#### 1.1 使用Clash代理
```bash
# 安装Clash (macOS)
brew install clash

# 配置Clash
mkdir -p ~/.config/clash
cat > ~/.config/clash/config.yaml << 'EOF'
port: 7890
socks-port: 7891
allow-lan: false
mode: Rule
log-level: info

proxies:
  - name: "your-proxy"
    type: http
    server: your-proxy-server.com
    port: 8080
    username: your-username  # 可选
    password: your-password  # 可选

proxy-groups:
  - name: "PROXY"
    type: select
    proxies:
      - your-proxy

rules:
  - DOMAIN-SUFFIX,okx.com,PROXY
  - DOMAIN-SUFFIX,okex.com,PROXY
  - MATCH,DIRECT
EOF

# 启动Clash
clash -d ~/.config/clash
```

#### 1.2 使用V2Ray代理
```bash
# 安装V2Ray (Linux)
bash <(curl -L https://raw.githubusercontent.com/v2fly/fhs-install-v2ray/master/install-release.sh)

# 配置V2Ray
sudo cat > /usr/local/etc/v2ray/config.json << 'EOF'
{
  "inbounds": [{
    "port": 1087,
    "protocol": "http",
    "settings": {}
  }],
  "outbounds": [{
    "protocol": "vmess",
    "settings": {
      "vnext": [{
        "address": "your-v2ray-server.com",
        "port": 443,
        "users": [{
          "id": "your-uuid",
          "security": "auto"
        }]
      }]
    }
  }]
}
EOF

# 启动V2Ray
sudo systemctl start v2ray
sudo systemctl enable v2ray
```

### 方案2: 云代理服务

#### 2.1 使用商业代理服务
```bash
# 示例配置（请替换为实际的代理信息）
export HTTP_PROXY=http://username:password@proxy.provider.com:8080
export HTTPS_PROXY=http://username:password@proxy.provider.com:8080

# 测试代理连接
curl --proxy $HTTP_PROXY https://www.okx.com/api/v5/public/time
```

#### 2.2 使用VPN服务
```bash
# 安装OpenVPN客户端
sudo apt install openvpn

# 连接VPN
sudo openvpn --config your-vpn-config.ovpn

# 验证IP地址变更
curl ipinfo.io
```

## ⚙️ MarketPrism代理配置

### 配置文件更新

#### 1. 更新proxy.yaml
```yaml
# config/proxy.yaml
environments:
  development:
    data-collector:
      enabled: true
      rest_api:
        http_proxy: "http://127.0.0.1:7890"
        https_proxy: "http://127.0.0.1:7890"
        timeout: 30
        verify_ssl: true
      websocket:
        socks_proxy: "socks5://127.0.0.1:7891"
        timeout: 30
      no_proxy: "localhost,127.0.0.1,*.local"
  
  production:
    data-collector:
      enabled: true
      rest_api:
        http_proxy: "http://your-proxy-server:port"
        https_proxy: "http://your-proxy-server:port"
        timeout: 30
        verify_ssl: true
      websocket:
        socks_proxy: "socks5://your-proxy-server:socks-port"
        timeout: 30
      no_proxy: "localhost,127.0.0.1,internal.domain.com"
  
  ci:
    data-collector:
      enabled: false  # CI环境通常不需要代理
```

#### 2. 环境变量配置
```bash
# .env文件
# 代理配置
PROXY_ENABLED=true
HTTP_PROXY=http://127.0.0.1:7890
HTTPS_PROXY=http://127.0.0.1:7890
SOCKS_PROXY=socks5://127.0.0.1:7891

# OKX特定配置
OKX_PROXY_ENABLED=true
OKX_API_TIMEOUT=30
OKX_RETRY_ATTEMPTS=3
```

### 代理验证脚本

#### 创建验证脚本
```bash
# scripts/verify_proxy_setup.sh
#!/bin/bash

echo "🔍 验证代理配置..."

# 检查代理服务状态
echo "1. 检查代理服务状态"
if curl -s --proxy http://127.0.0.1:7890 --max-time 10 https://www.google.com > /dev/null; then
    echo "✅ HTTP代理可用"
else
    echo "❌ HTTP代理不可用"
fi

# 测试OKX API连接
echo "2. 测试OKX API连接"
if curl -s --proxy http://127.0.0.1:7890 --max-time 15 https://www.okx.com/api/v5/public/time > /dev/null; then
    echo "✅ OKX API通过代理可访问"
else
    echo "❌ OKX API通过代理不可访问"
fi

# 运行MarketPrism OKX测试
echo "3. 运行MarketPrism OKX集成测试"
python scripts/okx_api_integration_optimizer.py

echo "🎉 代理验证完成"
```

## 🚀 自动化配置

### 自动代理检测脚本
```python
# scripts/auto_proxy_setup.py
#!/usr/bin/env python3
"""
自动代理配置脚本
检测可用的代理服务并自动配置MarketPrism
"""

import subprocess
import requests
import yaml
from pathlib import Path

def test_proxy(proxy_url):
    """测试代理可用性"""
    try:
        response = requests.get(
            'https://www.okx.com/api/v5/public/time',
            proxies={'http': proxy_url, 'https': proxy_url},
            timeout=10
        )
        return response.status_code == 200
    except:
        return False

def detect_local_proxies():
    """检测本地代理服务"""
    common_proxies = [
        'http://127.0.0.1:7890',  # Clash
        'http://127.0.0.1:1087',  # V2Ray
        'http://127.0.0.1:8080',  # 通用HTTP代理
        'http://127.0.0.1:3128',  # Squid代理
    ]
    
    available_proxies = []
    for proxy in common_proxies:
        if test_proxy(proxy):
            available_proxies.append(proxy)
            print(f"✅ 发现可用代理: {proxy}")
        else:
            print(f"❌ 代理不可用: {proxy}")
    
    return available_proxies

def update_proxy_config(proxy_url):
    """更新代理配置文件"""
    config_file = Path('config/proxy.yaml')
    
    # 读取现有配置
    if config_file.exists():
        with open(config_file, 'r') as f:
            config = yaml.safe_load(f)
    else:
        config = {'environments': {}}
    
    # 更新配置
    if 'development' not in config['environments']:
        config['environments']['development'] = {}
    
    config['environments']['development']['data-collector'] = {
        'enabled': True,
        'rest_api': {
            'http_proxy': proxy_url,
            'https_proxy': proxy_url,
            'timeout': 30
        },
        'websocket': {
            'socks_proxy': proxy_url.replace('http://', 'socks5://'),
            'timeout': 30
        }
    }
    
    # 保存配置
    with open(config_file, 'w') as f:
        yaml.dump(config, f, default_flow_style=False)
    
    print(f"✅ 代理配置已更新: {proxy_url}")

def main():
    print("🚀 开始自动代理配置...")
    
    # 检测可用代理
    proxies = detect_local_proxies()
    
    if proxies:
        # 使用第一个可用的代理
        best_proxy = proxies[0]
        update_proxy_config(best_proxy)
        
        # 验证配置
        print("🔍 验证配置...")
        subprocess.run(['python', 'scripts/okx_api_integration_optimizer.py'])
    else:
        print("❌ 未发现可用的代理服务")
        print("💡 请手动配置代理服务或使用直连模式")

if __name__ == "__main__":
    main()
```

## 🐳 Docker环境代理配置

### Docker Compose配置
```yaml
# docker-compose.override.yml
version: '3.8'

services:
  data-collector:
    environment:
      - HTTP_PROXY=http://host.docker.internal:7890
      - HTTPS_PROXY=http://host.docker.internal:7890
      - NO_PROXY=localhost,127.0.0.1,redis,postgres,nats
    extra_hosts:
      - "host.docker.internal:host-gateway"
```

### Dockerfile代理配置
```dockerfile
# 在Dockerfile中添加代理支持
FROM python:3.12-slim

# 设置代理环境变量
ARG HTTP_PROXY
ARG HTTPS_PROXY
ENV HTTP_PROXY=$HTTP_PROXY
ENV HTTPS_PROXY=$HTTPS_PROXY

# 安装依赖时使用代理
RUN pip install --proxy $HTTP_PROXY poetry

# 其他构建步骤...
```

## 🔧 故障排除

### 常见问题解决

#### 1. 代理连接失败
```bash
# 检查代理服务状态
netstat -tlnp | grep 7890

# 检查防火墙设置
sudo ufw status

# 测试代理连接
telnet 127.0.0.1 7890
```

#### 2. SSL证书验证失败
```python
# 在代码中禁用SSL验证（仅测试用）
import ssl
ssl._create_default_https_context = ssl._create_unverified_context
```

#### 3. 代理认证问题
```bash
# 使用用户名密码的代理
export HTTP_PROXY=http://username:password@proxy-server:port
export HTTPS_PROXY=http://username:password@proxy-server:port
```

### 调试命令
```bash
# 详细的curl调试
curl -v --proxy http://127.0.0.1:7890 https://www.okx.com/api/v5/public/time

# 检查代理日志
tail -f ~/.config/clash/logs/clash.log

# 网络连接跟踪
traceroute www.okx.com
```

## 📊 性能优化

### 代理性能调优
```yaml
# config/proxy.yaml - 性能优化配置
environments:
  production:
    data-collector:
      enabled: true
      rest_api:
        http_proxy: "http://proxy-server:port"
        https_proxy: "http://proxy-server:port"
        timeout: 30
        max_retries: 3
        retry_delay: 1
        connection_pool_size: 10
        keep_alive: true
      websocket:
        socks_proxy: "socks5://proxy-server:socks-port"
        timeout: 30
        ping_interval: 30
        ping_timeout: 10
```

### 连接池配置
```python
# 在API客户端中配置连接池
import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

session = requests.Session()

# 配置重试策略
retry_strategy = Retry(
    total=3,
    backoff_factor=1,
    status_forcelist=[429, 500, 502, 503, 504],
)

# 配置适配器
adapter = HTTPAdapter(
    max_retries=retry_strategy,
    pool_connections=10,
    pool_maxsize=20
)

session.mount("http://", adapter)
session.mount("https://", adapter)

# 设置代理
session.proxies = {
    'http': 'http://127.0.0.1:7890',
    'https': 'http://127.0.0.1:7890'
}
```

## 🔒 安全考虑

### 代理安全配置
1. **使用加密代理协议** (HTTPS, SOCKS5)
2. **配置代理认证** (用户名/密码)
3. **限制代理访问范围** (仅允许特定域名)
4. **定期更换代理凭据**
5. **监控代理使用情况**

### 生产环境建议
```bash
# 使用专用代理服务器
# 配置SSL/TLS加密
# 实施访问控制
# 启用日志审计
# 定期安全扫描
```

## 📞 支持和维护

### 维护检查清单
- [ ] 每日检查代理服务状态
- [ ] 每周测试OKX API连接
- [ ] 每月更新代理配置
- [ ] 每季度评估代理性能

### 联系支持
- **技术文档**: [MarketPrism文档](https://github.com/MNS-Vic/marketprism/docs)
- **问题报告**: [GitHub Issues](https://github.com/MNS-Vic/marketprism/issues)
- **代理服务商支持**: 联系您的代理服务提供商

---

**配置手册版本**: v1.0  
**最后更新**: 2025-06-21  
**适用版本**: MarketPrism v1.0+
