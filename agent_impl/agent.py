"""
LangGraph Agent 入口文件
用于 LangGraph CLI 和 LangSmith Studio 部署
"""

import sys
from pathlib import Path

# 将当前目录添加到 Python 路径，使 from graph.xxx import 能够工作
sys.path.insert(0, str(Path(__file__).parent))

from graph.workflow import create_workflow

# 重要提示：
# 当使用 LangGraph CLI 或部署到 LangGraph Cloud 时，平台会自动处理持久化。
# 在这种情况下，显式提供 checkpointer 会导致 ValueError。
# 因此，这里我们只编译图，不传入 checkpointer。
graph = create_workflow().compile()
