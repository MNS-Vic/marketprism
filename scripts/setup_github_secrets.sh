#!/bin/bash
# GitHub Secrets配置脚本

echo "🔐 配置GitHub Secrets..."

# 检查GitHub CLI是否安装
if ! command -v gh &> /dev/null; then
    echo "❌ GitHub CLI未安装，请先安装: https://cli.github.com/"
    exit 1
fi

# 检查是否已登录
if ! gh auth status &> /dev/null; then
    echo "🔑 请先登录GitHub CLI:"
    gh auth login
fi

# 获取仓库信息
REPO=$(gh repo view --json nameWithOwner -q .nameWithOwner)
echo "📦 当前仓库: $REPO"

# 生成安全密码
generate_password() {
    openssl rand -base64 32 | tr -d "=+/" | cut -c1-25
}

# 设置必需的secrets
echo "⚙️ 设置必需的secrets..."

# 数据库密码
POSTGRES_PASSWORD=$(generate_password)
echo "设置POSTGRES_PASSWORD..."
gh secret set POSTGRES_PASSWORD --body "$POSTGRES_PASSWORD"

# Redis密码
REDIS_PASSWORD=$(generate_password)
echo "设置REDIS_PASSWORD..."
gh secret set REDIS_PASSWORD --body "$REDIS_PASSWORD"

# JWT密钥
JWT_SECRET=$(generate_password)
echo "设置JWT_SECRET..."
gh secret set JWT_SECRET --body "$JWT_SECRET"

# 告警配置（可选）
echo "设置告警配置secrets（可选）..."

# 邮件配置
read -p "输入邮件SMTP主机 (可选，回车跳过): " SMTP_HOST
if [ ! -z "$SMTP_HOST" ]; then
    gh secret set ALERT_EMAIL_SMTP_HOST --body "$SMTP_HOST"
    
    read -p "输入邮件用户名: " EMAIL_USERNAME
    gh secret set ALERT_EMAIL_USERNAME --body "$EMAIL_USERNAME"
    
    read -s -p "输入邮件密码: " EMAIL_PASSWORD
    echo
    gh secret set ALERT_EMAIL_PASSWORD --body "$EMAIL_PASSWORD"
fi

# Slack配置
read -p "输入Slack Webhook URL (可选，回车跳过): " SLACK_WEBHOOK
if [ ! -z "$SLACK_WEBHOOK" ]; then
    gh secret set ALERT_SLACK_WEBHOOK --body "$SLACK_WEBHOOK"
fi

# 钉钉配置
read -p "输入钉钉Webhook URL (可选，回车跳过): " DINGTALK_WEBHOOK
if [ ! -z "$DINGTALK_WEBHOOK" ]; then
    gh secret set ALERT_DINGTALK_WEBHOOK --body "$DINGTALK_WEBHOOK"
    
    read -p "输入钉钉Secret: " DINGTALK_SECRET
    gh secret set ALERT_DINGTALK_SECRET --body "$DINGTALK_SECRET"
fi

# 云服务器配置（如果使用远程部署）
echo "设置云服务器配置（可选）..."

read -p "输入云服务器SSH主机 (可选，回车跳过): " SSH_HOST
if [ ! -z "$SSH_HOST" ]; then
    gh secret set DEPLOY_HOST --body "$SSH_HOST"
    
    read -p "输入SSH用户名: " SSH_USER
    gh secret set DEPLOY_USER --body "$SSH_USER"
    
    echo "请将SSH私钥内容粘贴到下面（以EOF结束）:"
    SSH_KEY=$(cat)
    gh secret set DEPLOY_SSH_KEY --body "$SSH_KEY"
fi

# 显示已设置的secrets
echo "✅ Secrets配置完成！"
echo "📋 已设置的secrets:"
gh secret list

# 生成环境变量文件模板
echo "📄 生成环境变量文件模板..."
cat > .env.github << EOF
# GitHub Actions环境变量模板
POSTGRES_PASSWORD=\${{ secrets.POSTGRES_PASSWORD }}
REDIS_PASSWORD=\${{ secrets.REDIS_PASSWORD }}
JWT_SECRET=\${{ secrets.JWT_SECRET }}

# 告警配置
ALERT_EMAIL_SMTP_HOST=\${{ secrets.ALERT_EMAIL_SMTP_HOST }}
ALERT_EMAIL_USERNAME=\${{ secrets.ALERT_EMAIL_USERNAME }}
ALERT_EMAIL_PASSWORD=\${{ secrets.ALERT_EMAIL_PASSWORD }}
ALERT_SLACK_WEBHOOK=\${{ secrets.ALERT_SLACK_WEBHOOK }}
ALERT_DINGTALK_WEBHOOK=\${{ secrets.ALERT_DINGTALK_WEBHOOK }}
ALERT_DINGTALK_SECRET=\${{ secrets.ALERT_DINGTALK_SECRET }}

# 云服务器配置
DEPLOY_HOST=\${{ secrets.DEPLOY_HOST }}
DEPLOY_USER=\${{ secrets.DEPLOY_USER }}
DEPLOY_SSH_KEY=\${{ secrets.DEPLOY_SSH_KEY }}
EOF

echo "✅ 环境变量模板已保存: .env.github"

echo "🎉 GitHub Secrets配置完成！"
echo "💡 提示: 请确保在GitHub仓库设置中验证secrets已正确设置"
