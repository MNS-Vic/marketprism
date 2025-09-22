import sys
from pathlib import Path

# 将 services/data-collector 加入 sys.path，便于测试直接导入 collector 包
DATA_COLLECTOR_ROOT = Path(__file__).resolve().parent.parent
if str(DATA_COLLECTOR_ROOT) not in sys.path:
    sys.path.insert(0, str(DATA_COLLECTOR_ROOT))

