#!/bin/bash
# MarketPrism SSL证书生成脚本
# 为各服务组件生成SSL证书

set -e  # 遇到错误立即退出

CERTS_DIR="./ssl-certs"
CA_DIR="$CERTS_DIR/ca"
DAYS_VALID=365  # 证书有效期(天)

# 确保目录存在
mkdir -p "$CERTS_DIR"/{clickhouse,nats,go-collector,data-ingestion,data-archiver}
mkdir -p "$CA_DIR"

echo "===== 生成根证书(CA) ====="
# 生成CA私钥
openssl genrsa -out "$CA_DIR/ca-key.pem" 4096
# 生成CA证书
openssl req -new -x509 -days $((DAYS_VALID*2)) -key "$CA_DIR/ca-key.pem" -out "$CA_DIR/ca-cert.pem" \
    -subj "/C=CN/ST=Beijing/L=Beijing/O=MarketPrism/OU=Root/CN=MarketPrism-RootCA"

echo "===== 为各组件生成证书 ====="

generate_component_cert() {
    local component=$1
    local cn=$2
    local dir="$CERTS_DIR/$component"
    
    echo "正在为 $component 生成证书..."
    
    # 生成私钥
    openssl genrsa -out "$dir/key.pem" 2048
    
    # 生成CSR (证书签名请求)
    openssl req -new -key "$dir/key.pem" -out "$dir/csr.pem" \
        -subj "/C=CN/ST=Beijing/L=Beijing/O=MarketPrism/OU=$component/CN=$cn"
    
    # 创建x509 v3扩展配置文件
    cat > "$dir/extfile.cnf" <<EOF
[v3_req]
keyUsage = keyEncipherment, dataEncipherment, digitalSignature
extendedKeyUsage = serverAuth, clientAuth
subjectAltName = @alt_names

[alt_names]
DNS.1 = $cn
DNS.2 = localhost
IP.1 = 127.0.0.1
EOF
    
    # 由CA签发证书
    openssl x509 -req -days $DAYS_VALID -in "$dir/csr.pem" \
        -CA "$CA_DIR/ca-cert.pem" -CAkey "$CA_DIR/ca-key.pem" -CAcreateserial \
        -out "$dir/cert.pem" -extfile "$dir/extfile.cnf" -extensions v3_req
    
    # 将CA证书也复制到组件目录
    cp "$CA_DIR/ca-cert.pem" "$dir/"
    
    # 适当的文件权限
    chmod 600 "$dir/key.pem"
    chmod 644 "$dir/cert.pem" "$dir/ca-cert.pem"
    
    echo "$component 证书已生成!"
}

# 为各组件生成证书
generate_component_cert "clickhouse" "clickhouse-server"
generate_component_cert "nats" "nats-server"
generate_component_cert "go-collector" "go-collector"
generate_component_cert "data-ingestion" "data-ingestion"
generate_component_cert "data-archiver" "data-archiver"

echo "===== 所有证书已生成 ====="
echo "警告: 证书文件位于 $CERTS_DIR 下，请勿提交到代码仓库！"

# 创建一个示例openssl连接测试命令，可以用于测试服务是否正确配置SSL
cat > "$CERTS_DIR/test_ssl_connection.sh" <<EOF
#!/bin/bash
# 用法: ./test_ssl_connection.sh <服务名> <主机> <端口>
# 例如: ./test_ssl_connection.sh nats localhost 4222

SERVICE=\$1
HOST=\$2
PORT=\$3

echo "测试 \$SERVICE SSL连接 (\$HOST:\$PORT)..."
openssl s_client -connect \$HOST:\$PORT -CAfile "$CERTS_DIR/\$SERVICE/ca-cert.pem"
EOF

chmod +x "$CERTS_DIR/test_ssl_connection.sh"

# 创建README.md说明文件，以帮助团队成员理解目录结构和文件用途
cat > "$CERTS_DIR/README.md" <<EOF
# MarketPrism SSL证书

此目录包含MarketPrism项目各组件的SSL证书。

## 目录结构

- \`ca/\` - 根证书(CA)，用于签发其它组件证书
- \`clickhouse/\` - ClickHouse数据库的证书
- \`nats/\` - NATS消息队列的证书
- \`go-collector/\` - Go数据收集服务的证书
- \`data-ingestion/\` - 数据接收服务的证书
- \`data-archiver/\` - 数据归档服务的证书

## 证书文件

每个组件目录包含以下文件:
- \`cert.pem\` - 公钥证书
- \`key.pem\` - 私钥(敏感文件)
- \`ca-cert.pem\` - CA证书副本
- \`csr.pem\` - 证书签名请求(仅生成过程使用)
- \`extfile.cnf\` - 扩展配置(仅生成过程使用)

## 重要提示

1. **请勿提交这些证书到代码仓库!**
2. 证书有效期为${DAYS_VALID}天，请记得在到期前更新
3. 使用 \`test_ssl_connection.sh\` 可测试SSL连接
EOF

echo "===== 不要忘记添加证书目录到.gitignore! =====" 