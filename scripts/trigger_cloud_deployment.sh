#!/bin/bash
# 触发GitHub Actions云端部署脚本

echo "☁️ 触发MarketPrism云端部署..."

# 检查GitHub CLI
if ! command -v gh &> /dev/null; then
    echo "❌ GitHub CLI未安装，请先安装: https://cli.github.com/"
    exit 1
fi

# 检查登录状态
if ! gh auth status &> /dev/null; then
    echo "🔑 请先登录GitHub CLI:"
    gh auth login
fi

# 获取当前分支
CURRENT_BRANCH=$(git branch --show-current)
echo "📍 当前分支: $CURRENT_BRANCH"

# 检查是否有未提交的更改
if ! git diff --quiet || ! git diff --cached --quiet; then
    echo "⚠️ 检测到未提交的更改"
    read -p "是否提交更改并继续? (y/N): " commit_changes
    
    if [ "$commit_changes" = "y" ] || [ "$commit_changes" = "Y" ]; then
        echo "📝 提交更改..."
        git add .
        git commit -m "Deploy MarketPrism to cloud environment

- Update configuration for cloud deployment
- Trigger GitHub Actions workflow
- Deploy via Docker Swarm"
        
        echo "📤 推送到远程仓库..."
        git push origin $CURRENT_BRANCH
    else
        echo "❌ 部署已取消"
        exit 1
    fi
fi

# 选择部署环境
echo "🌍 选择部署环境:"
echo "1. staging (测试环境)"
echo "2. production (生产环境)"
read -p "请选择 (1-2): " env_choice

case $env_choice in
    1)
        ENVIRONMENT="staging"
        ;;
    2)
        ENVIRONMENT="production"
        echo "⚠️ 警告: 您选择了生产环境部署"
        read -p "确认部署到生产环境? (yes/no): " confirm_prod
        if [ "$confirm_prod" != "yes" ]; then
            echo "❌ 生产环境部署已取消"
            exit 1
        fi
        ;;
    *)
        echo "❌ 无效选择"
        exit 1
        ;;
esac

echo "🚀 触发云端部署到 $ENVIRONMENT 环境..."

# 触发GitHub Actions工作流
gh workflow run cloud-deployment.yml \
    --field environment=$ENVIRONMENT \
    --ref $CURRENT_BRANCH

if [ $? -eq 0 ]; then
    echo "✅ 云端部署工作流已触发"
    
    # 等待工作流开始
    echo "⏳ 等待工作流开始..."
    sleep 10
    
    # 显示工作流状态
    echo "📊 工作流状态:"
    gh run list --workflow=cloud-deployment.yml --limit=1
    
    # 获取最新运行的ID
    RUN_ID=$(gh run list --workflow=cloud-deployment.yml --limit=1 --json databaseId --jq '.[0].databaseId')
    
    if [ ! -z "$RUN_ID" ]; then
        echo "🔗 工作流链接: https://github.com/$(gh repo view --json nameWithOwner -q .nameWithOwner)/actions/runs/$RUN_ID"
        
        # 询问是否监控部署进度
        read -p "是否监控部署进度? (y/N): " monitor_progress
        
        if [ "$monitor_progress" = "y" ] || [ "$monitor_progress" = "Y" ]; then
            echo "👀 监控部署进度..."
            gh run watch $RUN_ID
        else
            echo "💡 您可以使用以下命令监控部署进度:"
            echo "   gh run watch $RUN_ID"
            echo "   gh run view $RUN_ID"
        fi
    fi
else
    echo "❌ 触发云端部署失败"
    exit 1
fi

# 显示后续步骤
echo ""
echo "📋 后续步骤:"
echo "1. 监控GitHub Actions工作流执行状态"
echo "2. 检查部署日志和测试结果"
echo "3. 验证应用在云端的运行状态"
echo "4. 如果部署成功，访问应用进行功能验证"
echo ""
echo "🔗 有用的命令:"
echo "   gh run list --workflow=cloud-deployment.yml"
echo "   gh run view $RUN_ID"
echo "   gh run download $RUN_ID"
echo ""
echo "🎉 云端部署触发完成！"
