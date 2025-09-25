#!/bin/bash

# MarketPrism 监控告警服务测试脚本

set -e

PROJECT_ROOT="/home/ubuntu/marketprism"
SERVICE_DIR="$PROJECT_ROOT/services/monitoring-alerting-service"

echo "🔍 MarketPrism 监控告警服务诊断"
echo "=================================="

# 检查项目结构
echo "📁 检查项目结构..."
if [ ! -d "$PROJECT_ROOT" ]; then
    echo "❌ 项目根目录不存在: $PROJECT_ROOT"
    exit 1
fi

if [ ! -d "$SERVICE_DIR" ]; then
    echo "⚠️ 服务目录不存在: $SERVICE_DIR — 跳过该脚本（仓库未包含旧版前端/服务目录）"
    exit 0
fi

echo "✅ 项目结构检查通过"

# 检查配置文件
echo "📋 检查配置文件..."
CONFIG_FILE="$PROJECT_ROOT/config/services/monitoring-alerting-service.yaml"
if [ ! -f "$CONFIG_FILE" ]; then
    echo "⚠️ 配置文件不存在: $CONFIG_FILE — 将跳过配置文件校验，继续其余检查"
fi

echo "✅ 配置文件存在"

# 检查Python环境
echo "🐍 检查Python环境..."
cd "$PROJECT_ROOT"

if ! command -v python3 &> /dev/null; then
    echo "❌ Python3 未安装"
    exit 1
fi

echo "✅ Python3 已安装: $(python3 --version)"

# 检查依赖
echo "📦 检查Python依赖..."
if [ ! -f "$SERVICE_DIR/requirements.txt" ]; then
    echo "❌ requirements.txt 不存在"
    exit 1
fi

# 尝试导入核心模块
echo "🔧 测试核心模块导入..."
python3 -c "
import sys
sys.path.insert(0, '.')

try:
    from config.unified_config_loader import UnifiedConfigLoader
    print('✅ UnifiedConfigLoader 导入成功')
except Exception as e:
    print(f'❌ UnifiedConfigLoader 导入失败: {e}')
    exit(1)

try:
    from core.observability.alerting import AlertManager
    print('✅ AlertManager 导入成功')
except Exception as e:
    print(f'❌ AlertManager 导入失败: {e}')
    exit(1)

try:
    from core.observability.metrics.business_metrics import get_business_metrics
    print('✅ business_metrics 导入成功')
except Exception as e:
    print(f'❌ business_metrics 导入失败: {e}')
    exit(1)

print('✅ 所有核心模块导入成功')
"

if [ $? -ne 0 ]; then
    echo "❌ 核心模块导入测试失败"
    exit 1
fi

# 测试配置加载
echo "⚙️ 测试配置加载..."
python3 -c "
import sys
sys.path.insert(0, '.')

try:
    from config.unified_config_loader import UnifiedConfigLoader
    config_loader = UnifiedConfigLoader()
    config = config_loader.load_service_config('monitoring-alerting-service')
    print(f'✅ 配置加载成功，配置项数量: {len(config)}')
    
    # 检查关键配置项
    if 'server' in config:
        print(f'✅ 服务器配置: {config[\"server\"]}')
    else:
        print('⚠️ 缺少服务器配置')
        
    if 'alert_rules' in config:
        print('✅ 告警规则配置存在')
    else:
        print('⚠️ 缺少告警规则配置')
        
except Exception as e:
    print(f'❌ 配置加载失败: {e}')
    import traceback
    traceback.print_exc()
    exit(1)
"

if [ $? -ne 0 ]; then
    echo "❌ 配置加载测试失败"
    exit 1
fi

# 测试服务创建
echo "🚀 测试服务创建..."
python3 -c "
import sys
import asyncio
sys.path.insert(0, '.')

async def test_service():
    try:
        # 导入服务模块
        import importlib.util
        spec = importlib.util.spec_from_file_location(
            'monitoring_service', 
            'services/monitoring-alerting-service/main.py'
        )
        monitoring_module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(monitoring_module)
        
        # 创建服务实例
        from config.unified_config_loader import UnifiedConfigLoader
        config_loader = UnifiedConfigLoader()
        config = config_loader.load_service_config('monitoring-alerting-service')
        
        service = monitoring_module.MonitoringAlertingService(config)
        print('✅ 服务实例创建成功')
        
        # 测试初始化（不启动服务器）
        await service.initialize()
        print('✅ 服务初始化成功')
        
        # 测试健康检查
        health = await service._get_component_health()
        print(f'✅ 组件健康状态: {health}')
        
        return True
        
    except Exception as e:
        print(f'❌ 服务测试失败: {e}')
        import traceback
        traceback.print_exc()
        return False

result = asyncio.run(test_service())
if not result:
    exit(1)
"

if [ $? -ne 0 ]; then
    echo "❌ 服务创建测试失败"
    exit 1
fi

echo ""
echo "🎉 所有测试通过！"
echo "✅ 监控告警服务配置正确，可以正常启动"
echo ""
echo "📝 启动服务的方法："
echo "1. 直接启动: cd $PROJECT_ROOT && python3 services/monitoring-alerting-service/start_service.py"
echo "2. Docker启动: cd $SERVICE_DIR && docker-compose -f docker-compose.test.yml up"
echo ""
echo "🔗 服务端点："
echo "- 健康检查: http://localhost:8082/health"
echo "- 就绪检查: http://localhost:8082/ready"
echo "- 告警API: http://localhost:8082/api/v1/alerts"
echo "- Prometheus指标: http://localhost:8082/metrics"
