#!/usr/bin/env python3
import subprocess
from pathlib import Path

def test_manage_all_show_usage():
    project_root = Path(__file__).resolve().parents[2]
    result = subprocess.run([
        "bash", str(project_root / "scripts" / "manage_all.sh")
    ], capture_output=True, text=True, cwd=str(project_root))
    # 应输出用法说明并返回非零（1）
    assert "系统统一管理脚本" in result.stdout or "MarketPrism 系统统一管理脚本" in result.stdout
    assert result.returncode != 0

