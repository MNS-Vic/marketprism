#!/bin/bash

# 快速网络测试脚本
set -e

# 颜色定义
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

echo -e "${BLUE}🔍 快速网络测试${NC}"

# 1. 代理测试
echo "1. 测试代理..."
if curl -s -I --connect-timeout 2 --max-time 3 --proxy http://127.0.0.1:1087 https://www.google.com >/dev/null 2>&1; then
    echo -e "${GREEN}✅ 代理可用: http://127.0.0.1:1087${NC}"
    PROXY_URL="http://127.0.0.1:1087"
    export http_proxy=$PROXY_URL
    export https_proxy=$PROXY_URL
else
    echo -e "${YELLOW}⚠️  代理不可用，使用直连${NC}"
fi

# 2. 快速测试关键源
echo "2. 测试关键下载源..."

# Docker源测试
echo -n "   Docker官方源... "
if curl -s --connect-timeout 2 --max-time 3 https://registry-1.docker.io/v2/ >/dev/null 2>&1; then
    echo -e "${GREEN}✅${NC}"
    DOCKER_REGISTRY="https://registry-1.docker.io"
else
    echo -e "${YELLOW}❌ 尝试中科大镜像...${NC}"
    if curl -s --connect-timeout 2 --max-time 3 https://docker.mirrors.ustc.edu.cn/v2/ >/dev/null 2>&1; then
        echo -e "${GREEN}✅ 中科大镜像可用${NC}"
        DOCKER_REGISTRY="https://docker.mirrors.ustc.edu.cn"
    else
        echo -e "${YELLOW}❌ 使用网易镜像${NC}"
        DOCKER_REGISTRY="https://hub-mirror.c.163.com"
    fi
fi

# Python源测试
echo -n "   Python包源... "
if curl -s --connect-timeout 2 --max-time 3 https://pypi.org/simple/ >/dev/null 2>&1; then
    echo -e "${GREEN}✅ 官方源可用${NC}"
    PYTHON_INDEX="https://pypi.org/simple/"
else
    echo -e "${YELLOW}❌ 使用清华源${NC}"
    PYTHON_INDEX="https://pypi.tuna.tsinghua.edu.cn/simple/"
fi

# Go代理测试
echo -n "   Go模块代理... "
if curl -s --connect-timeout 2 --max-time 3 https://proxy.golang.org >/dev/null 2>&1; then
    echo -e "${GREEN}✅ 官方代理可用${NC}"
    GO_PROXY="https://proxy.golang.org"
else
    echo -e "${YELLOW}❌ 使用七牛云代理${NC}"
    GO_PROXY="https://goproxy.cn"
fi

# 3. 生成配置
echo "3. 生成优化配置..."

# Docker配置
cat > docker-daemon-optimized.json << EOF
{
  "experimental": false,
  "features": {
    "buildkit": true
  },
  "registry-mirrors": [
    "$DOCKER_REGISTRY"
  ],
  "builder": {
    "gc": {
      "defaultKeepStorage": "20GB",
      "enabled": true
    }
  }
}
EOF

# 构建环境脚本
cat > scripts/setup_build_env.sh << EOF
#!/bin/bash

# 快速构建环境设置
set -e

echo "🔧 设置优化的构建环境..."

EOF

if [ -n "$PROXY_URL" ]; then
    cat >> scripts/setup_build_env.sh << EOF
# 设置代理
export http_proxy=$PROXY_URL
export https_proxy=$PROXY_URL
export HTTP_PROXY=$PROXY_URL
export HTTPS_PROXY=$PROXY_URL
echo "✅ 代理已设置: $PROXY_URL"

EOF
fi

cat >> scripts/setup_build_env.sh << EOF
# 设置包源
export PIP_INDEX_URL=$PYTHON_INDEX
export PIP_TRUSTED_HOST=\$(echo $PYTHON_INDEX | sed 's|https\?://||' | cut -d/ -f1)
export GOPROXY=$GO_PROXY,direct
export GOSUMDB=off

echo "✅ Python包源: $PYTHON_INDEX"
echo "✅ Go代理: $GO_PROXY"
echo "✅ Docker镜像源: $DOCKER_REGISTRY"
echo "🎉 构建环境设置完成！"
EOF

chmod +x scripts/setup_build_env.sh

echo -e "${GREEN}✅ 配置生成完成！${NC}"
echo "   - docker-daemon-optimized.json: Docker优化配置"
echo "   - scripts/setup_build_env.sh: 构建环境脚本"

echo ""
echo -e "${BLUE}📋 测试结果总结：${NC}"
echo "   🌐 代理: ${PROXY_URL:-无}"
echo "   🐳 Docker镜像源: $DOCKER_REGISTRY"
echo "   🐍 Python包源: $PYTHON_INDEX"
echo "   �� Go代理: $GO_PROXY" 