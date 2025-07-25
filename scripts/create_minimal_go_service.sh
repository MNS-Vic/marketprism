#!/bin/bash

# 创建最小化Go服务的脚本
# 用于演示本地构建概念

set -e

SERVICE_NAME="go-collector-minimal"
SERVICE_DIR="services/$SERVICE_NAME"

echo "🚀 创建最小化Go服务: $SERVICE_NAME"

# 创建服务目录
mkdir -p "$SERVICE_DIR"
cd "$SERVICE_DIR"

# 创建最小化的go.mod
cat > go.mod << 'EOF'
module github.com/marketprism/go-collector-minimal

go 1.21

require (
	github.com/gorilla/websocket v1.5.0
)

// 本地路径替换
replace github.com/marketprism/go-collector-minimal => ./
EOF

# 创建简单的main.go
cat > main.go << 'EOF'
package main

import (
	"fmt"
	"log"
	"net/http"
	"time"
)

func main() {
	fmt.Println("🚀 MarketPrism Go Collector Minimal Edition")
	fmt.Printf("Version: 1.0.0\n")
	fmt.Printf("Build Time: %s\n", time.Now().Format("2006-01-02 15:04:05"))
	
	// 简单的HTTP服务器
	http.HandleFunc("/health", func(w http.ResponseWriter, r *http.Request) {
		w.WriteHeader(http.StatusOK)
		fmt.Fprintf(w, `{"status":"ok","service":"go-collector-minimal","timestamp":"%s"}`, time.Now().Format(time.RFC3339))
	})
	
	http.HandleFunc("/", func(w http.ResponseWriter, r *http.Request) {
		w.WriteHeader(http.StatusOK)
		fmt.Fprintf(w, "MarketPrism Go Collector Minimal - Running Successfully!")
	})
	
	fmt.Println("🌐 HTTP服务启动在 :8080")
	fmt.Println("📊 健康检查: http://localhost:8080/health")
	fmt.Println("✅ 服务运行中，按 Ctrl+C 停止")
	
	log.Fatal(http.ListenAndServe(":8080", nil))
}
EOF

# 创建config目录和配置文件
mkdir -p config
cat > config/config.yaml << 'EOF'
# MarketPrism Go Collector Minimal Configuration
app_name: "go-collector-minimal"
version: "1.0.0"
log_level: "info"
server:
  port: 8080
  host: "0.0.0.0"
EOF

# 创建Dockerfile
cat > Dockerfile << 'EOF'
FROM golang:1.21-alpine AS builder

WORKDIR /app
COPY go.mod go.sum ./
RUN go mod download

COPY . .
RUN CGO_ENABLED=0 GOOS=linux go build -o collector .

FROM alpine:latest
RUN apk --no-cache add ca-certificates
WORKDIR /root/
COPY --from=builder /app/collector .
COPY --from=builder /app/config ./config
EXPOSE 8080
CMD ["./collector"]
EOF

# 创建go.sum（空文件，将在首次构建时生成）
touch go.sum

# 设置权限
chmod +x ../../../scripts/local_build.sh

echo "✅ 最小化Go服务创建完成: $SERVICE_DIR"
echo ""
echo "📋 下一步操作："
echo "1. 构建服务: ./scripts/local_build.sh go-collector-minimal"
echo "2. 运行服务: ./services/go-collector-minimal/bin/collector"
echo "3. 测试健康检查: curl http://localhost:8080/health"
echo ""
echo "📁 生成的文件："
echo "  - services/$SERVICE_NAME/main.go (主程序)"
echo "  - services/$SERVICE_NAME/go.mod (模块配置)"
echo "  - services/$SERVICE_NAME/config/config.yaml (配置文件)"
echo "  - services/$SERVICE_NAME/Dockerfile (容器构建文件)" 