# MarketPrism WebSocket 实时数据协议

## 📋 概述
MarketPrism系统使用WebSocket协议提供实时数据推送服务，支持市场数据、系统监控、服务状态等多种数据的实时更新。

## 🔗 连接信息

### WebSocket服务端点
```
开发环境: ws://localhost:8086/ws
生产环境: wss://api.marketprism.com/ws
```

### 连接认证
```javascript
// 连接时携带认证信息
const ws = new WebSocket('ws://localhost:8086/ws', [], {
  headers: {
    'Authorization': 'Bearer your-api-key'
  }
});
```

## 📨 消息协议

### 基础消息格式
```typescript
interface WebSocketMessage {
  type: 'subscribe' | 'unsubscribe' | 'data' | 'error' | 'ping' | 'pong';
  channel: string;
  data?: any;
  timestamp?: number;
  id?: string;              // 消息ID，用于追踪
}
```

### 连接生命周期

#### 1. 连接建立
```javascript
ws.onopen = function(event) {
  console.log('WebSocket连接已建立');
  
  // 发送ping保持连接
  setInterval(() => {
    ws.send(JSON.stringify({
      type: 'ping',
      timestamp: Date.now()
    }));
  }, 30000);
};
```

#### 2. 心跳机制
```javascript
// 客户端发送ping
{
  "type": "ping",
  "timestamp": 1697123456789
}

// 服务端响应pong
{
  "type": "pong",
  "timestamp": 1697123456789
}
```

## 📺 频道订阅

### 订阅消息格式
```typescript
interface SubscribeMessage {
  type: 'subscribe';
  channel: string;
  filters?: {
    symbol?: string;        // 交易对
    exchange?: string;      // 交易所
    interval?: string;      // 时间间隔
    [key: string]: any;     // 其他过滤条件
  };
}
```

### 可用频道列表

#### 1. 系统监控频道 (`system`)
```javascript
// 订阅系统监控数据
ws.send(JSON.stringify({
  type: 'subscribe',
  channel: 'system'
}));

// 接收数据格式
{
  "type": "data",
  "channel": "system",
  "data": {
    "cpu_usage": 19.5,
    "memory_usage": 56.2,
    "disk_usage": 1.13,
    "network_in": 125.6,
    "network_out": 89.3,
    "timestamp": 1697123456789
  }
}
```

#### 2. 服务状态频道 (`services`)
```javascript
// 订阅服务状态数据
ws.send(JSON.stringify({
  type: 'subscribe',
  channel: 'services'
}));

// 接收数据格式
{
  "type": "data",
  "channel": "services",
  "data": {
    "service_name": "data-collector",
    "status": "running",
    "cpu_usage": 12.3,
    "memory_usage": 156,
    "response_time": 28,
    "timestamp": 1697123456789
  }
}
```

#### 3. 告警频道 (`alerts`)
```javascript
// 订阅告警信息
ws.send(JSON.stringify({
  type: 'subscribe',
  channel: 'alerts'
}));

// 接收数据格式
{
  "type": "data",
  "channel": "alerts",
  "data": {
    "id": "alert_123",
    "level": "warning",
    "title": "CPU使用率过高",
    "message": "API Gateway CPU使用率达到85%",
    "service": "api-gateway",
    "timestamp": 1697123456789
  }
}
```

#### 4. 价格数据频道 (`prices`)
```javascript
// 订阅特定交易对价格
ws.send(JSON.stringify({
  type: 'subscribe',
  channel: 'prices',
  filters: {
    symbol: 'BTC/USDT',
    exchange: 'binance'
  }
}));

// 接收数据格式
{
  "type": "data",
  "channel": "prices",
  "data": {
    "symbol": "BTC/USDT",
    "exchange": "binance",
    "price": 43256.78,
    "change_24h": 2.34,
    "volume_24h": 1247.89,
    "timestamp": 1697123456789
  }
}
```

#### 5. 订单簿频道 (`orderbook`)
```javascript
// 订阅订单簿数据
ws.send(JSON.stringify({
  type: 'subscribe',
  channel: 'orderbook',
  filters: {
    symbol: 'BTC/USDT',
    exchange: 'binance',
    depth: 20
  }
}));

// 接收数据格式
{
  "type": "data",
  "channel": "orderbook",
  "data": {
    "symbol": "BTC/USDT",
    "exchange": "binance",
    "asks": [
      {"price": 43267.89, "amount": 0.1234, "total": 5341.23}
    ],
    "bids": [
      {"price": 43254.12, "amount": 0.3456, "total": 14945.78}
    ],
    "timestamp": 1697123456789
  }
}
```

#### 6. 交易记录频道 (`trades`)
```javascript
// 订阅交易记录
ws.send(JSON.stringify({
  type: 'subscribe',
  channel: 'trades',
  filters: {
    symbol: 'BTC/USDT',
    exchange: 'binance'
  }
}));

// 接收数据格式
{
  "type": "data",
  "channel": "trades",
  "data": {
    "id": "trade_123456",
    "symbol": "BTC/USDT",
    "exchange": "binance",
    "side": "buy",
    "price": 43256.78,
    "amount": 0.1234,
    "timestamp": 1697123456789
  }
}
```

## 🔄 订阅管理

### 取消订阅
```javascript
// 取消特定频道订阅
ws.send(JSON.stringify({
  type: 'unsubscribe',
  channel: 'prices',
  filters: {
    symbol: 'BTC/USDT'
  }
}));

// 取消所有订阅
ws.send(JSON.stringify({
  type: 'unsubscribe',
  channel: '*'
}));
```

### 订阅确认
```javascript
// 服务端确认订阅成功
{
  "type": "subscribed",
  "channel": "prices",
  "filters": {
    "symbol": "BTC/USDT",
    "exchange": "binance"
  },
  "timestamp": 1697123456789
}

// 服务端确认取消订阅
{
  "type": "unsubscribed",
  "channel": "prices",
  "timestamp": 1697123456789
}
```

## ⚠️ 错误处理

### 错误消息格式
```javascript
{
  "type": "error",
  "channel": "prices",
  "error": {
    "code": 400,
    "message": "Invalid symbol format",
    "details": "Symbol must be in format BASE/QUOTE"
  },
  "timestamp": 1697123456789
}
```

### 常见错误码
```typescript
enum WebSocketErrorCode {
  INVALID_MESSAGE = 400,      // 消息格式错误
  UNAUTHORIZED = 401,         // 认证失败
  FORBIDDEN = 403,            // 权限不足
  CHANNEL_NOT_FOUND = 404,    // 频道不存在
  RATE_LIMITED = 429,         // 订阅频率限制
  INTERNAL_ERROR = 500        // 服务器内部错误
}
```

### 重连机制
```javascript
let reconnectAttempts = 0;
const maxReconnectAttempts = 5;
const reconnectInterval = 1000; // 1秒

function connectWebSocket() {
  const ws = new WebSocket('ws://localhost:8086/ws');
  
  ws.onopen = function() {
    console.log('WebSocket connected');
    reconnectAttempts = 0;
    
    // 重新订阅之前的频道
    restoreSubscriptions();
  };
  
  ws.onclose = function() {
    console.log('WebSocket disconnected');
    
    if (reconnectAttempts < maxReconnectAttempts) {
      setTimeout(() => {
        reconnectAttempts++;
        connectWebSocket();
      }, reconnectInterval * Math.pow(2, reconnectAttempts));
    }
  };
  
  ws.onerror = function(error) {
    console.error('WebSocket error:', error);
  };
}
```

## 📊 数据更新频率

### 推送频率说明
| 频道 | 更新频率 | 说明 |
|------|----------|------|
| system | 5秒 | 系统监控数据 |
| services | 10秒 | 服务状态数据 |
| alerts | 实时 | 告警信息即时推送 |
| prices | 实时 | 价格变化时立即推送 |
| orderbook | 100ms | 订单簿深度变化 |
| trades | 实时 | 成交记录实时推送 |

### 数据压缩
```javascript
// 订阅时可以请求数据压缩
ws.send(JSON.stringify({
  type: 'subscribe',
  channel: 'orderbook',
  options: {
    compression: true,    // 启用数据压缩
    diff_only: true      // 只推送差异数据
  }
}));
```

## 🔧 前端集成示例

### React Hook示例
```typescript
import { useEffect, useState, useRef } from 'react';

interface WebSocketHookConfig {
  url: string;
  token?: string;
  reconnect?: boolean;
}

export function useWebSocket(config: WebSocketHookConfig) {
  const [data, setData] = useState<any>(null);
  const [status, setStatus] = useState<'connecting' | 'connected' | 'disconnected'>('disconnected');
  const ws = useRef<WebSocket | null>(null);
  
  useEffect(() => {
    connect();
    return () => disconnect();
  }, [config.url]);
  
  const connect = () => {
    setStatus('connecting');
    ws.current = new WebSocket(config.url);
    
    ws.current.onopen = () => {
      setStatus('connected');
    };
    
    ws.current.onmessage = (event) => {
      const message = JSON.parse(event.data);
      if (message.type === 'data') {
        setData(message.data);
      }
    };
    
    ws.current.onclose = () => {
      setStatus('disconnected');
      if (config.reconnect) {
        setTimeout(connect, 3000);
      }
    };
  };
  
  const subscribe = (channel: string, filters?: any) => {
    if (ws.current?.readyState === WebSocket.OPEN) {
      ws.current.send(JSON.stringify({
        type: 'subscribe',
        channel,
        filters
      }));
    }
  };
  
  const disconnect = () => {
    ws.current?.close();
  };
  
  return { data, status, subscribe, disconnect };
}
```

### Vue Composition API示例
```typescript
import { ref, onMounted, onUnmounted } from 'vue';

export function useWebSocket(url: string) {
  const data = ref(null);
  const status = ref('disconnected');
  let ws: WebSocket | null = null;
  
  const connect = () => {
    status.value = 'connecting';
    ws = new WebSocket(url);
    
    ws.onopen = () => {
      status.value = 'connected';
    };
    
    ws.onmessage = (event) => {
      const message = JSON.parse(event.data);
      if (message.type === 'data') {
        data.value = message.data;
      }
    };
    
    ws.onclose = () => {
      status.value = 'disconnected';
    };
  };
  
  const subscribe = (channel: string, filters?: any) => {
    if (ws?.readyState === WebSocket.OPEN) {
      ws.send(JSON.stringify({
        type: 'subscribe',
        channel,
        filters
      }));
    }
  };
  
  onMounted(connect);
  onUnmounted(() => ws?.close());
  
  return { data, status, subscribe };
}
```

## 🎯 最佳实践

### 1. 连接管理
- 使用心跳机制维持连接
- 实现自动重连机制
- 合理设置重连间隔和最大尝试次数

### 2. 订阅优化
- 按需订阅，避免不必要的数据传输
- 及时取消不再需要的订阅
- 使用过滤条件减少数据量

### 3. 性能优化
- 使用数据压缩减少传输量
- 合理处理高频数据更新
- 避免在UI线程中处理大量数据

### 4. 错误处理
- 实现完善的错误处理机制
- 记录错误日志便于调试
- 为用户提供友好的错误提示

这个WebSocket协议文档为前端团队提供了完整的实时数据集成指南，确保前后端能够高效地进行实时数据交互。