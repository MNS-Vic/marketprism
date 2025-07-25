#!/bin/bash
# MarketPrism技术迁移自动检查脚本
# 用于在技术栈迁移时自动验证配置一致性
# 版本: 1.0.0 (2025-04-30)

# 设置颜色输出
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[0;33m'
BLUE='\033[0;34m'
NC='\033[0m' # 无颜色

# 项目根目录
ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR" || exit 1

echo -e "\n${BLUE}====== MarketPrism技术迁移检查工具 ======${NC}\n"

# 检查必要的工具是否可用
for cmd in python docker docker-compose grep find; do
  if ! command -v $cmd &> /dev/null; then
    echo -e "${RED}错误: 找不到必要的命令 '$cmd'${NC}"
    exit 1
  fi
done

# 检查配置验证脚本是否存在
if [ ! -f "scripts/config_validator.py" ]; then
  echo -e "${RED}错误: 找不到配置验证脚本 'scripts/config_validator.py'${NC}"
  exit 1
fi

# 1. 运行配置验证工具
echo -e "${YELLOW}1. 运行配置验证工具...${NC}"
python scripts/config_validator.py
VALIDATOR_EXIT=$?

if [ $VALIDATOR_EXIT -ne 0 ]; then
  echo -e "${RED}配置验证失败，请修复上述问题后重试${NC}"
  exit 1
fi

echo

# 2. 检查docker-compose语法
echo -e "${YELLOW}2. 验证docker-compose配置...${NC}"
if docker-compose config > /dev/null; then
  echo -e "${GREEN}docker-compose配置验证通过!${NC}"
else
  echo -e "${RED}docker-compose配置有误，请修复后重试${NC}"
  exit 1
fi

echo

# 3. 检查Redis相关引用
echo -e "${YELLOW}3. 检查代码中的Redis相关引用...${NC}"

# 检查Python代码中的Redis引用
PYTHON_FILES_WITH_REDIS=$(grep -r --include="*.py" -l "redis\|Redis" services 2>/dev/null || true)
if [ -n "$PYTHON_FILES_WITH_REDIS" ]; then
  echo -e "${RED}在以下Python文件中发现Redis引用:${NC}"
  echo "$PYTHON_FILES_WITH_REDIS"
  echo -e "${YELLOW}请检查这些文件，确保它们已经更新为使用NATS${NC}"
  HAS_ISSUES=1
else
  echo -e "${GREEN}Python代码中未发现Redis引用${NC}"
fi

# 检查Go代码中的Redis引用
GO_FILES_WITH_REDIS=$(grep -r --include="*.go" -l "redis\|Redis" services 2>/dev/null || true)
if [ -n "$GO_FILES_WITH_REDIS" ]; then
  echo -e "${RED}在以下Go文件中发现Redis引用:${NC}"
  echo "$GO_FILES_WITH_REDIS"
  echo -e "${YELLOW}请检查这些文件，确保它们已经更新为使用NATS${NC}"
  HAS_ISSUES=1
else
  echo -e "${GREEN}Go代码中未发现Redis引用${NC}"
fi

echo

# 4. 检查配置文件中的Redis引用
echo -e "${YELLOW}4. 检查配置文件中的Redis引用...${NC}"
CONFIG_FILES_WITH_REDIS=$(grep -r --include="*.yaml" --include="*.yml" -l "redis\|Redis" config 2>/dev/null || true)
if [ -n "$CONFIG_FILES_WITH_REDIS" ]; then
  echo -e "${RED}在以下配置文件中发现Redis引用:${NC}"
  echo "$CONFIG_FILES_WITH_REDIS"
  echo -e "${YELLOW}请检查这些文件，确保移除Redis相关配置${NC}"
  HAS_ISSUES=1
else
  echo -e "${GREEN}配置文件中未发现Redis引用${NC}"
fi

echo

# 5. 检查文档中不必要的Redis引用
echo -e "${YELLOW}5. 检查文档中不必要的Redis引用...${NC}"
README_REDIS_LINES=$(grep -n "redis\|Redis" README.md 2>/dev/null | grep -v "已弃用" | grep -v "历史组件" || true)
if [ -n "$README_REDIS_LINES" ]; then
  echo -e "${YELLOW}在README.md文件中发现潜在过时的Redis引用:${NC}"
  echo "$README_REDIS_LINES"
  echo -e "${YELLOW}请检查这些内容，确保文档已更新${NC}"
  HAS_ISSUES=1
else
  echo -e "${GREEN}文档中未发现不必要的Redis引用${NC}"
fi

echo

# 6. 综合检查结果
echo -e "${YELLOW}6. 检查总结...${NC}"
if [ -n "$HAS_ISSUES" ]; then
  echo -e "${RED}发现潜在的配置不一致问题，请查看上述详情并更新相关文件${NC}"
  echo -e "${YELLOW}推荐使用 'scripts/tech_migration_checklist.md' 进行完整的迁移检查${NC}"
  exit 1
else
  echo -e "${GREEN}所有检查通过! 系统配置与当前技术栈一致${NC}"
fi

echo -e "\n${BLUE}====== 检查完成 ======${NC}\n"
echo -e "如需更详细的迁移指南，请参考: ${YELLOW}scripts/tech_migration_checklist.md${NC}"
exit 0 