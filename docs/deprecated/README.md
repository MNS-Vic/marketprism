# Deprecated（已弃用/历史保留）

下列文件/脚本由于架构升级或统一入口自愈机制引入，已不再推荐在生产环境中直接使用。它们保留在仓库中仅用于历史参考与迁移辅助，后续版本可能移除。

## 清单

- scripts/service_manager.py
  - 理由：data-collector 已内置“统一入口自愈重启”，无需外部服务管理器
  - 替代：`services/data-collector/main.py`（统一入口，内置健康监控与自愈）

- services/data-collector/fixed_normalizer.py
  - 理由：历史修复版标准化器，标准实现已统一到 `collector/normalizer.py`
  - 替代：`services/data-collector/collector/normalizer.py`

- services/data-collector/normalizer_fix.py
  - 理由：历史修复示例，标准实现已统一到 `collector/normalizer.py`
  - 替代：`services/data-collector/collector/normalizer.py`

## 使用建议
- 生产环境：请使用统一入口 `services/data-collector/main.py` 启动；通过环境变量启用自愈
- 如果确需多进程编排：优先使用 systemd、Docker 或 K8s 等标准化编排方式
- 对于历史修复脚本：仅供阅读/迁移参考，不建议在生产代码中 import 使用

