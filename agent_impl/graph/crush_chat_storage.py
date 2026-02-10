"""
Crush 聊天记录分层存储
实现 L1-L3 层的存储和检索（L4 语义检索待后续实现）

分层结构：
- L1: 元数据层（常驻上下文）- 聊天频率、消息数、时间跨度
- L2: 结构化摘要层（常驻上下文）- 关键事件、情感转折点、主要话题
- L3: 关键片段层（按需调用）- 最近N条 + 标记为重要的对话
- L4: 全量存储层（语义检索）- 待实现，需向量数据库

数据来源：用户上传的聊天截图，经 OCR 提取的文字内容
"""

import json
from typing import Optional, Any
from datetime import datetime
import uuid
import logging

from graph.context_types import (
    CrushChatMetadata,
    CrushChatSummary,
    CrushChatStorage,
)
from config import get_llm


logger = logging.getLogger(__name__)


# ============================================================
# 配置常量
# ============================================================

CRUSH_CHAT_CONFIG = {
    "recent_messages_count": 20,    # L3: 保留最近 N 条消息
    "max_important_messages": 10,   # L3: 最多保留 N 条重要消息
    "summary_update_threshold": 10, # 每新增 N 条消息更新一次摘要
}


# ============================================================
# 消息数据结构
# ============================================================

class CrushMessage:
    """单条 Crush 聊天消息"""
    
    def __init__(
        self,
        content: str,
        sender: str,  # "user" 或 "crush"
        timestamp: Optional[str] = None,
        source_image: Optional[str] = None,
        is_important: bool = False,
        importance_reason: Optional[str] = None,
    ):
        self.id = str(uuid.uuid4())[:8]
        self.content = content
        self.sender = sender
        self.timestamp = timestamp or datetime.now().isoformat()
        self.source_image = source_image  # 来源截图路径
        self.is_important = is_important
        self.importance_reason = importance_reason
    
    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "content": self.content,
            "sender": self.sender,
            "timestamp": self.timestamp,
            "source_image": self.source_image,
            "is_important": self.is_important,
            "importance_reason": self.importance_reason,
        }
    
    @classmethod
    def from_dict(cls, data: dict) -> "CrushMessage":
        msg = cls(
            content=data.get("content", ""),
            sender=data.get("sender", "unknown"),
            timestamp=data.get("timestamp"),
            source_image=data.get("source_image"),
            is_important=data.get("is_important", False),
            importance_reason=data.get("importance_reason"),
        )
        msg.id = data.get("id", msg.id)
        return msg


# ============================================================
# 核心存储管理器
# ============================================================

class CrushChatManager:
    """
    Crush 聊天记录管理器
    
    管理 L1-L3 层的存储和检索
    """
    
    def __init__(self):
        # L3: 全部消息（内存中）
        self.all_messages: list[CrushMessage] = []
        
        # L1: 元数据
        self.metadata: CrushChatMetadata = CrushChatMetadata(
            total_messages=0,
            chat_frequency="未知",
            time_span="未知",
            last_chat_time="",
        )
        
        # L2: 结构化摘要
        self.summary: CrushChatSummary = CrushChatSummary(
            key_events=[],
            emotional_turns=[],
            main_topics=[],
        )
        
        # 上次更新摘要时的消息数
        self._last_summary_count = 0
    
    # ========== L3: 消息管理 ==========
    
    def add_message(
        self,
        content: str,
        sender: str,
        timestamp: Optional[str] = None,
        source_image: Optional[str] = None,
    ) -> CrushMessage:
        """
        添加一条消息
        
        Args:
            content: 消息内容
            sender: 发送者 ("user" 或 "crush")
            timestamp: 时间戳（可选）
            source_image: 来源截图路径（可选）
        
        Returns:
            创建的消息对象
        """
        msg = CrushMessage(
            content=content,
            sender=sender,
            timestamp=timestamp,
            source_image=source_image,
        )
        self.all_messages.append(msg)
        
        # 更新 L1 元数据
        self._update_metadata()
        
        # 检查是否需要更新 L2 摘要
        self._check_summary_update()
        
        return msg
    
    def add_messages_batch(
        self,
        messages: list[dict],
        source_image: Optional[str] = None,
    ) -> list[CrushMessage]:
        """
        批量添加消息（从截图提取的对话）
        
        Args:
            messages: [{"content": "...", "sender": "user/crush", "timestamp": "..."}]
            source_image: 来源截图路径
        
        Returns:
            创建的消息对象列表
        """
        added = []
        for msg_data in messages:
            msg = self.add_message(
                content=msg_data.get("content", ""),
                sender=msg_data.get("sender", "unknown"),
                timestamp=msg_data.get("timestamp"),
                source_image=source_image,
            )
            added.append(msg)
        
        return added
    
    def mark_as_important(
        self,
        message_id: str,
        reason: Optional[str] = None,
    ) -> bool:
        """标记消息为重要"""
        for msg in self.all_messages:
            if msg.id == message_id:
                msg.is_important = True
                msg.importance_reason = reason
                return True
        return False
    
    def get_recent_messages(self, count: Optional[int] = None) -> list[CrushMessage]:
        """获取最近 N 条消息"""
        n = count or CRUSH_CHAT_CONFIG["recent_messages_count"]
        return self.all_messages[-n:] if self.all_messages else []
    
    def get_important_messages(self) -> list[CrushMessage]:
        """获取所有标记为重要的消息"""
        return [msg for msg in self.all_messages if msg.is_important]
    
    def search_messages(self, keyword: str) -> list[CrushMessage]:
        """关键词搜索消息（简单文本匹配，L4 实现后可用语义搜索）"""
        keyword_lower = keyword.lower()
        return [
            msg for msg in self.all_messages
            if keyword_lower in msg.content.lower()
        ]
    
    # ========== L1: 元数据 ==========
    
    def _update_metadata(self):
        """更新 L1 元数据"""
        total = len(self.all_messages)
        self.metadata["total_messages"] = total
        
        if total > 0:
            # 最后聊天时间
            self.metadata["last_chat_time"] = self.all_messages[-1].timestamp
            
            # 时间跨度
            first_time = self.all_messages[0].timestamp
            last_time = self.all_messages[-1].timestamp
            self.metadata["time_span"] = f"{first_time[:10]} 至 {last_time[:10]}"
            
            # 聊天频率（简单估算）
            if total < 10:
                self.metadata["chat_frequency"] = "较少"
            elif total < 50:
                self.metadata["chat_frequency"] = "一般"
            elif total < 100:
                self.metadata["chat_frequency"] = "频繁"
            else:
                self.metadata["chat_frequency"] = "非常频繁"
    
    def get_metadata(self) -> CrushChatMetadata:
        """获取 L1 元数据"""
        return self.metadata
    
    # ========== L2: 结构化摘要 ==========
    
    def _check_summary_update(self):
        """检查是否需要更新摘要"""
        current_count = len(self.all_messages)
        threshold = CRUSH_CHAT_CONFIG["summary_update_threshold"]
        
        if current_count - self._last_summary_count >= threshold:
            self._update_summary()
            self._last_summary_count = current_count
    
    def _update_summary(self):
        """更新 L2 结构化摘要（调用 LLM）"""
        if len(self.all_messages) < 5:
            return
        
        try:
            llm = get_llm(temperature=0.3)
            
            # 准备最近的消息
            recent = self.all_messages[-30:]  # 最多取最近 30 条
            messages_text = "\n".join([
                f"{'用户' if m.sender == 'user' else 'Crush'}: {m.content}"
                for m in recent
            ])
            
            prompt = f"""分析以下聊天记录，提取结构化信息：

## 聊天记录
{messages_text}

## 任务
请提取：
1. **关键事件**：发生的重要事情（如约会、争吵、表白等）
2. **情感转折点**：关系或情绪的明显变化
3. **主要话题**：他们经常聊什么

## 输出格式（JSON）
```json
{{
  "key_events": ["事件1", "事件2"],
  "emotional_turns": ["转折1", "转折2"],
  "main_topics": ["话题1", "话题2", "话题3"]
}}
```"""
            
            response = llm.invoke(prompt)
            parsed = self._parse_json_response(response.content)
            
            if parsed:
                self.summary = CrushChatSummary(
                    key_events=parsed.get("key_events", []),
                    emotional_turns=parsed.get("emotional_turns", []),
                    main_topics=parsed.get("main_topics", []),
                )
                logger.info("Updated summary: %s events", len(self.summary.get("key_events", [])))
        
        except Exception as e:
            logger.exception("Failed to update summary")
    
    def get_summary(self) -> CrushChatSummary:
        """获取 L2 结构化摘要"""
        return self.summary
    
    def force_update_summary(self):
        """强制更新摘要（手动触发）"""
        self._update_summary()
        self._last_summary_count = len(self.all_messages)
    
    # ========== 序列化/反序列化 ==========
    
    def to_dict(self) -> dict:
        """序列化为字典（用于存储）"""
        return {
            "all_messages": [m.to_dict() for m in self.all_messages],
            "metadata": dict(self.metadata),
            "summary": dict(self.summary),
            "_last_summary_count": self._last_summary_count,
        }
    
    @classmethod
    def from_dict(cls, data: dict) -> "CrushChatManager":
        """从字典反序列化"""
        manager = cls()
        
        # 恢复消息
        messages_data = data.get("all_messages", [])
        manager.all_messages = [CrushMessage.from_dict(m) for m in messages_data]
        
        # 恢复元数据
        if data.get("metadata"):
            manager.metadata = CrushChatMetadata(**data["metadata"])
        
        # 恢复摘要
        if data.get("summary"):
            manager.summary = CrushChatSummary(**data["summary"])
        
        manager._last_summary_count = data.get("_last_summary_count", 0)
        
        return manager
    
    def to_storage(self) -> CrushChatStorage:
        """转换为 AgentState 使用的 CrushChatStorage 格式"""
        return CrushChatStorage(
            metadata=self.metadata,
            summary=self.summary,
        )
    
    # ========== 上下文构建 ==========
    
    def build_context_l1_l2(self) -> str:
        """
        构建 L1+L2 的上下文内容（常驻）
        
        Returns:
            格式化的 Markdown 文本
        """
        parts = ["## Crush 聊天记录概况"]
        
        # L1: 元数据
        parts.append(f"""
### 基本信息
- 总消息数：{self.metadata.get('total_messages', 0)} 条
- 聊天频率：{self.metadata.get('chat_frequency', '未知')}
- 时间跨度：{self.metadata.get('time_span', '未知')}
- 最后聊天：{self.metadata.get('last_chat_time', '未知')[:10] if self.metadata.get('last_chat_time') else '未知'}
""")
        
        # L2: 结构化摘要
        key_events = self.summary.get("key_events", [])
        emotional_turns = self.summary.get("emotional_turns", [])
        main_topics = self.summary.get("main_topics", [])
        
        if key_events or emotional_turns or main_topics:
            parts.append("### 聊天分析")
            
            if key_events:
                events_text = "\n".join(f"- {e}" for e in key_events[:5])
                parts.append(f"**关键事件**：\n{events_text}")
            
            if emotional_turns:
                turns_text = "\n".join(f"- {t}" for t in emotional_turns[:3])
                parts.append(f"**情感转折**：\n{turns_text}")
            
            if main_topics:
                parts.append(f"**主要话题**：{', '.join(main_topics[:5])}")
        
        return "\n\n".join(parts)
    
    def build_context_l3(self, include_recent: int = 10) -> str:
        """
        构建 L3 的上下文内容（按需调用）
        
        Args:
            include_recent: 包含最近 N 条消息
        
        Returns:
            格式化的 Markdown 文本
        """
        parts = ["## 最近的 Crush 聊天记录"]
        
        recent = self.get_recent_messages(include_recent)
        if recent:
            for msg in recent:
                sender = "用户" if msg.sender == "user" else "Crush"
                time_str = msg.timestamp[:10] if msg.timestamp else ""
                parts.append(f"**{sender}** ({time_str}): {msg.content}")
        else:
            parts.append("暂无聊天记录")
        
        # 重要消息
        important = self.get_important_messages()
        if important:
            parts.append("\n### 标记为重要的消息")
            for msg in important[:5]:
                sender = "用户" if msg.sender == "user" else "Crush"
                reason = f"（{msg.importance_reason}）" if msg.importance_reason else ""
                parts.append(f"- **{sender}**: {msg.content} {reason}")
        
        return "\n\n".join(parts)
    
    # ========== 辅助函数 ==========
    
    @staticmethod
    def _parse_json_response(content: str) -> dict:
        """解析 LLM 的 JSON 输出"""
        try:
            if "```json" in content:
                json_str = content.split("```json")[1].split("```")[0].strip()
            elif "```" in content:
                json_str = content.split("```")[1].split("```")[0].strip()
            else:
                start = content.find("{")
                end = content.rfind("}") + 1
                if start != -1 and end > start:
                    json_str = content[start:end]
                else:
                    return {}
            
            return json.loads(json_str)
        except (json.JSONDecodeError, IndexError):
            return {}


# ============================================================
# 便捷函数
# ============================================================

def create_crush_chat_manager() -> CrushChatManager:
    """创建新的 Crush 聊天管理器"""
    return CrushChatManager()


def extract_messages_from_screenshot_text(
    ocr_text: str,
    crush_name: str = "Crush",
) -> list[dict]:
    """
    从截图 OCR 文本中提取消息（简单规则解析）
    
    实际使用时应调用更智能的解析（如 LLM）
    
    Args:
        ocr_text: OCR 提取的文本
        crush_name: Crush 的名称（用于识别发送者）
    
    Returns:
        [{"content": "...", "sender": "user/crush"}]
    """
    # 这是一个简化的实现，实际应该用 LLM 解析
    messages = []
    lines = ocr_text.strip().split("\n")
    
    for line in lines:
        line = line.strip()
        if not line:
            continue
        
        # 简单规则：如果包含 crush_name 开头，认为是 crush 说的
        if line.lower().startswith(crush_name.lower()):
            content = line[len(crush_name):].strip(": ：")
            messages.append({"content": content, "sender": "crush"})
        else:
            # 否则认为是用户说的（这个逻辑很粗糙，实际需要更智能的解析）
            messages.append({"content": line, "sender": "user"})
    
    return messages
