"""
LangGraph Agent 入口文件
用于 LangGraph CLI 和 LangSmith Studio 部署
"""

import sys
from pathlib import Path

# 将当前目录添加到 Python 路径，使 from graph.xxx import 能够工作
sys.path.insert(0, str(Path(__file__).parent))

# ---- Shim: 补齐 LangChain Cloud 基础镜像 langgraph/prebuilt 版本冲突 ----
# 平台基础镜像里 langgraph-prebuilt 新版 tool_node.py 顶层执行：
#   from langgraph.runtime import ExecutionInfo, ServerInfo  # noqa: TC002
# 但基础镜像里的 langgraph.runtime 版本太旧、没有这两个符号，导致 ImportError。
# 这两个符号在源文件里仅用于类型注解（noqa: TC002 标记），运行时不使用。
# 因此在最早的 import 之前注入两个占位类，让那行 import 能通过。
try:
    import langgraph.runtime as _lgr
    if not hasattr(_lgr, "ExecutionInfo"):
        class _ExecutionInfo:  # type: ignore[no-redef]
            pass
        _lgr.ExecutionInfo = _ExecutionInfo  # type: ignore[attr-defined]
    if not hasattr(_lgr, "ServerInfo"):
        class _ServerInfo:  # type: ignore[no-redef]
            pass
        _lgr.ServerInfo = _ServerInfo  # type: ignore[attr-defined]
except Exception:
    pass
# ---- End shim ----

from graph.workflow import create_workflow

# 重要提示：
# 当使用 LangGraph CLI 或部署到 LangGraph Cloud 时，平台会自动处理持久化。
# 在这种情况下，显式提供 checkpointer 会导致 ValueError。
# 因此，这里我们只编译图，不传入 checkpointer。
graph = create_workflow().compile()
