"""
LangGraph Agent 入口文件
用于 LangGraph CLI 和 LangSmith Studio 部署
"""

from graph.workflow import create_workflow

# 注意：不使用 checkpointer，LangGraph API 会自动处理持久化
graph = create_workflow().compile()
