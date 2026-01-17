"""
行动指南详情加载工具 (Action Guide Detail Loader)

用于“渐进式披露”：
- 上下文中通常只展示行动指南的元数据（id/title/status/one_liner）
- 当 Agent 需要查看某条指南的完整内容时，通过工具按需加载

注意：该工具需要访问“当前会话的 state”，因此以工厂函数形式创建（闭包注入 state_getter）。
"""

from __future__ import annotations

from typing import Callable, Any

from langchain.tools import tool


def create_guide_loader_tool(state_getter: Callable[[], dict[str, Any]]):
    """
    创建带状态访问能力的 load_action_guide_detail 工具。

    Args:
        state_getter: 一个函数，调用时返回当前 state（dict）
    """

    @tool
    def load_action_guide_detail(guide_id: str) -> str:
        """
        加载指定行动指南的完整内容（Markdown）。

        当上下文中仅看到某条指南的摘要/元数据，但需要查看其完整步骤时，调用本工具。

        Args:
            guide_id: 指南唯一 ID（ActionGuideItem.id，如 "a1b2c3d4"）

        Returns:
            完整的 Markdown 格式指南内容；若找不到则返回错误信息。
        """
        state = state_getter() or {}

        # 优先从 Layer2Memory 全量存储读取
        layer2 = state.get("layer2_memory") or {}
        guides = layer2.get("action_guides") or state.get("action_guides") or []

        target_id = str(guide_id or "").strip()
        if not target_id:
            return "guide_id 不能为空。请传入行动指南的唯一 ID（例如：'a1b2c3d4'）。"

        for g in guides:
            if not isinstance(g, dict):
                continue
            if str(g.get("id") or "") != target_id:
                continue

            guide = g.get("guide") if isinstance(g.get("guide"), dict) else {}
            title = g.get("title") or guide.get("current_task") or "未命名指南"
            status = g.get("status") or "pending"
            created_at = g.get("created_at") or ""

            # 兼容旧结构：guide_content 可能直接在顶层或在 guide 内
            guide_content = ""
            if isinstance(g.get("guide_content"), str) and g.get("guide_content"):
                guide_content = g["guide_content"]
            elif isinstance(guide.get("guide_content"), str) and guide.get("guide_content"):
                guide_content = guide["guide_content"]

            meta_lines = [
                f"## 指南详情：{title}",
                "",
                f"- **ID**: {target_id}",
                f"- **状态**: {status}",
            ]
            if created_at:
                meta_lines.append(f"- **创建时间**: {created_at}")

            if guide_content:
                return "\n".join(meta_lines) + "\n\n" + guide_content

            # 降级：结构化字段拼一个简版
            parts = list(meta_lines)
            steps = guide.get("steps") or []
            if isinstance(steps, list) and steps:
                parts.append("\n### 步骤")
                parts.extend([f"{i}. {s}" for i, s in enumerate([str(x) for x in steps], 1)])
            talking_points = guide.get("talking_points") or []
            if isinstance(talking_points, list) and talking_points:
                parts.append("\n### 话术要点")
                parts.extend([f"- {tp}" for tp in [str(x) for x in talking_points]])

            if len(parts) == len(meta_lines):
                parts.append("\n该指南没有可用的详细内容（guide_content/steps 均为空）。")
            return "\n".join(parts)

        return f"未找到 ID 为 {target_id} 的指南。请检查上下文表格中的 ID 是否正确。"

    return load_action_guide_detail





