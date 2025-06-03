# MarketPrism 网络加速指南

本文档记录了在开发和部署 MarketPrism 项目时使用的各种镜像源和代理设置，以解决网络问题。

## 整体开发策略

为了解决重复下载依赖的问题，我们采用以下开发策略：

1. **本地开发优先**：在本地环境完成所有功能开发和测试，利用本地缓存和镜像源加速开发过程
2. **容器化部署后置**：功能开发完成后再构建Docker镜像并部署
3. **分层构建缓存**：利用Docker的分层构建和缓存机制减少重复下载

## 代理设置

### HTTP/HTTPS 代理

在本地开发环境中，设置以下环境变量：

```bash
# 使用本机代理
export http_proxy=http://127.0.0.1:1087
export https_proxy=http://127.0.0.1:1087
export ALL_PROXY=socks5://127.0.0.1:1087
```

在Docker容器中，需要使用宿主机IP：

```bash
# 使用宿主机IP地址
export http_proxy=http://192.168.31.145:1088
export https_proxy=http://192.168.31.145:1088
export ALL_PROXY=socks5://192.168.31.145:1088
```

> **注意**：Docker容器内不能使用`127.0.0.1`来访问宿主机代理，需要使用宿主机实际IP或者使用`docker-proxy.py`桥接服务。

### docker-proxy.py 桥接服务

为解决Docker容器内访问宿主机代理的问题，我们提供了`docker-proxy.py`服务：

```bash
# 启动代理桥接服务
python docker-proxy.py &
```

该服务默认监听1088端口，将请求转发到宿主机的1087端口。

## 镜像源配置

### Go 模块镜像

成功实践：使用 [goproxy.io](https://goproxy.io) 替代默认的Go模块源

```bash
# 本地环境设置
export GOPROXY=https://goproxy.io,direct

# Dockerfile中设置
ENV GOPROXY=https://goproxy.io,direct
ENV GO111MODULE=on
```

### Debian/Ubuntu 软件源

成功实践：使用腾讯云内网镜像源

```
# Debian bullseye 配置
deb http://mirrors.tencentyun.com/debian bullseye main contrib non-free
deb http://mirrors.tencentyun.com/debian bullseye-updates main contrib non-free
deb http://mirrors.tencentyun.com/debian-security bullseye-security main contrib non-free
```

在Dockerfile中的使用方法：

```Dockerfile
RUN echo "deb http://mirrors.tencentyun.com/debian bullseye main contrib non-free" > /etc/apt/sources.list && \
    echo "deb http://mirrors.tencentyun.com/debian bullseye-updates main contrib non-free" >> /etc/apt/sources.list && \
    echo "deb http://mirrors.tencentyun.com/debian-security bullseye-security main contrib non-free" >> /etc/apt/sources.list
```

### Python 包镜像

成功实践：使用腾讯云PyPI镜像源

```bash
# 本地环境临时使用
pip install package-name -i https://mirrors.tencentyun.com/pypi/simple/

# 永久配置
pip config set global.index-url https://mirrors.tencentyun.com/pypi/simple/
pip config set global.trusted-host mirrors.tencentyun.com
```

在Dockerfile中的使用方法：

```Dockerfile
ENV PIP_INDEX_URL=https://mirrors.tencentyun.com/pypi/simple/
ENV PIP_TRUSTED_HOST=mirrors.tencentyun.com

# 或者使用RUN命令
RUN pip config set global.index-url https://mirrors.tencentyun.com/pypi/simple/ && \
    pip config set global.trusted-host mirrors.tencentyun.com
```

### Docker 镜像加速

成功实践：使用腾讯云内网镜像加速Docker镜像拉取

```json
// ~/.docker/daemon.json
{
  "registry-mirrors": [
    "https://mirror.ccs.tencentyun.com",
    "https://mirrors.tencentyun.com",
    "https://docker.mirrors.ustc.edu.cn",
    "https://hub-mirror.c.163.com"
  ]
}
```

## Docker构建优化

为了减少Docker构建时重复下载依赖的问题，建议采用以下策略：

1. **使用多阶段构建**：将构建环境与运行环境分离
2. **合理分层**：将不常变更的依赖安装步骤放在Dockerfile前面
3. **本地开发完成再构建**：本地开发完成并测试通过后再构建Docker镜像
4. **预先拉取基础镜像**：手动拉取和缓存基础镜像

示例优化后的构建流程：

```bash
# 1. 本地开发
cd services/go-collector
export GOPROXY=https://goproxy.io,direct
go mod tidy
go build ./...

# 2. 预拉取基础镜像
docker pull golang:1.20
docker pull debian:bullseye-slim
docker pull python:3.9-slim

# 3. 使用--build-arg传递代理设置
docker build \
  --build-arg HTTP_PROXY=http://192.168.31.145:1088 \
  --build-arg HTTPS_PROXY=http://192.168.31.145:1088 \
  --build-arg ALL_PROXY=socks5://192.168.31.145:1088 \
  -t marketprism/go-collector .
```

## 总结

1. 本地开发时使用代理和镜像源加速开发过程
2. 所有功能在本地完成开发和测试
3. 利用容器构建缓存减少重复下载
4. 部署前清除不必要的代理设置

通过以上策略，可以有效解决网络问题和重复下载依赖的问题，提高开发效率。 