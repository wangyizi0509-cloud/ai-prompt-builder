"""
归档管理器 (Archive Manager)
管理分层长期记忆的归档和压缩

职责：
1. Layer 2 归档：报告/规划/指南的历史摘要管理
2. Layer 3 归档：对话压缩和摘要生成
3. Layer 1 更新：从归档内容中提取高价值信息
4. 任务推理归档：任务思考过程 (Rolling Scratchpad) 的滚动摘要

策略文档参考：
- 综合压缩策略：context_system/03_Strategies/Compression_Strategy/compression_strategy_v1.0.md
- Organize Agent Prompt：context_system/03_Strategies/Compression_Strategy/organize_agent_prompts.md
- 提纯策略：context_system/03_Strategies/Refining_Strategy/refining_strategy_v1.0.md
- 存储策略：context_system/03_Strategies/Storage_Strategy/storage_strategy_v1.0.md

规范文档参考：
- Layer 1 规范：context_system/02_Specs/layer1_spec_v1.0.md
- Layer 2 规范：context_system/02_Specs/layer2_spec_v1.0.md
- Layer 3 规范：context_system/02_Specs/layer3_spec_v1.0.md
- 组装规范：context_system/02_Specs/context_assembly_spec.md
"""

from typing import TYPE_CHECKING, Optional
from datetime import datetime
import uuid
import logging

if TYPE_CHECKING:
    from graph.state import AgentState

from graph.context_types import (
    # Layer 1
    UserContext,
    Layer1Memory,
    create_empty_user_context,
    create_empty_layer1_memory,
    # Layer 2
    Layer2Memory,
    ActionGuideItem,
    StatusReportItem,
    ActionPlanItem,
    create_empty_layer2_memory,
    DynamicIntelItem,
    # Layer 3
    Layer3Memory,
    ConversationSummary,
    create_empty_layer3_memory,
    create_conversation_summary,
    AgentTaskRegistry,
    TaskState,
    get_active_task,
    # 处理状态
    start_layer_processing,
    finish_layer_processing,
    is_layer_processing,
)
from graph.storage_strategy import (
    StorageRouter,
    StorageProcessor,
)
from graph.state import get_message_id
from langchain.messages import RemoveMessage
from graph.nodes.organize_agent import (
    archive_completed_guide,
    archive_replaced_status_report,
    archive_replaced_action_plan,
    archive_conversation_batch,
    summarize_task_reasoning,
)
from utils.message_utils import count_user_turns


logger = logging.getLogger(__name__)


# ============================================================
# 配置常量
# ============================================================

LAYER2_ARCHIVE_CONFIG = {
    "recent_summary_count": 2,      # 最近 N 份保留中等摘要
    "max_one_liner_count": 10,      # 最多保留 N 条一句话摘要
    "max_total_history": 20,        # 每类历史最多保留条数
}

LAYER3_ARCHIVE_CONFIG = {
    "max_recent_turns": 20,         # 保留最近 N 轮完整对话
    "compression_batch_size": 1,    # 每超出 batch_size 轮集中压缩一次
    "compression_threshold": 25,    # 超过此轮次开始检查是否需要压缩
    "max_summaries": 10,            # 最多保留的对话摘要数
    "reasoning_limit": 10,          # 任务思考过程记录保留条数 (n)
    "reasoning_compression_batch": 2, # 思考过程压缩批量大小 (n-5 到 n 条一起摘要)
}

# 存储策略路由器（供归档流程复用，前置占位便于后续扩展）
_storage_router = StorageRouter()


# ============================================================
# Layer 3: 对话压缩管理
# ============================================================

def check_layer3_compression_needed(state: "AgentState") -> bool:
    """
    检查 Layer 3 是否需要触发对话压缩
    
    触发条件：
    - 工作区对话轮次超过 compression_threshold（默认 25）
    - 且超出部分达到 compression_batch_size 的倍数
    
    重要：使用工作区消息 (messages) 而非全量存储 (all_messages) 判断
    因为 all_messages 是全量保留的历史记录，只增不减；
    而 messages 是实际参与上下文的工作区消息，压缩后会减少。
    
    例如：阈值 25，批量大小 1
    - 24 轮：不压缩
    - 25 轮：不压缩（刚到阈值）
    - 26 轮：触发压缩（超出 1 轮）
    """
    # [FIX] 使用工作区消息 (messages) 判断，而非全量存储 (all_messages)
    # all_messages 是全量保留的，永远只增不减，会导致压缩条件永远满足
    workspace_messages = state.get("messages", [])
    
    # 以用户消息数量为基准计算"轮次"
    current_turns = count_user_turns(workspace_messages)
    
    threshold = LAYER3_ARCHIVE_CONFIG["compression_threshold"]
    batch_size = LAYER3_ARCHIVE_CONFIG["compression_batch_size"]
    
    # [DEBUG] 详细日志输出
    excess_turns = max(0, current_turns - threshold)
    should_trigger = current_turns > threshold and excess_turns % batch_size == 0
    print(f"[Archive] check_layer3_compression_needed: "
          f"workspace_messages={len(workspace_messages)}, "
          f"user_turns={current_turns}, "
          f"threshold={threshold}, batch_size={batch_size}, "
          f"excess={excess_turns}, result={should_trigger}")
    
    if current_turns <= threshold:
        return False
    
    # 检查是否达到批量压缩的触发点
    return excess_turns > 0 and excess_turns % batch_size == 0


def get_layer3_messages_to_compress(state: "AgentState") -> tuple[list[dict], list[dict]]:
    """
    获取 Layer 3 需要压缩的消息和保留的消息
    
    重要：使用工作区消息 (messages) 而非全量存储 (all_messages)
    压缩的目的是减少工作区的上下文窗口大小。
    
    Returns:
        (to_compress, to_keep): 需要压缩的消息列表, 需要保留的消息列表
    """
    # [FIX] 使用工作区消息 (messages) 进行压缩判断
    workspace_messages = state.get("messages", [])
    
    max_recent = LAYER3_ARCHIVE_CONFIG["max_recent_turns"]
    
    # 以用户消息数量为基准计算轮次
    user_turn_count = count_user_turns(workspace_messages)
    
    if user_turn_count <= max_recent:
        return [], workspace_messages
    
    # 找到保留的最近 N 轮用户消息的边界
    # 从后往前数，找到第 max_recent 个用户消息的位置
    user_count = 0
    split_index = len(workspace_messages)
    for i in range(len(workspace_messages) - 1, -1, -1):
        from utils.message_utils import get_msg_role_and_content
        role, _ = get_msg_role_and_content(workspace_messages[i])
        if role == "user":
            user_count += 1
            if user_count == max_recent:
                split_index = i
                break
    
    # 在该用户消息之前的所有消息都压缩
    to_compress = workspace_messages[:split_index]
    to_keep = workspace_messages[split_index:]
    
    return to_compress, to_keep


def compress_layer3(state: "AgentState") -> dict:
    """
    执行 Layer 3 对话压缩
    
    流程：
    1. 设置处理状态（标记为正在压缩）
    2. 获取需要压缩的消息
    3. 调用整理 Agent 处理（LLM 生成摘要）
    4. 生成对话摘要，存入 layer3_memory.conversation_summaries
    5. 提取高价值信息，写入 layer1_memory
    6. 清除处理状态
    
    并发处理：
    - 开始压缩前设置 processing_status
    - 保存压缩前的数据快照作为 fallback
    - 压缩完成后清除状态并递增版本号
    
    Returns:
        状态更新字典，包含：
        - layer3_memory: 更新后的 Layer 3 长期记忆
        - layer1_memory: 更新后的 Layer 1 长期记忆（如有新信息）
        - messages: 压缩后保留的消息（向后兼容）
    """
    to_compress, to_keep = get_layer3_messages_to_compress(state)
    
    if not to_compress:
        return {}
    
    # 获取现有的长期记忆
    layer1_memory = state.get("layer1_memory") or create_empty_layer1_memory()
    layer2_memory = state.get("layer2_memory") or create_empty_layer2_memory()
    layer3_memory = state.get("layer3_memory") or create_empty_layer3_memory()
    
    # 检查是否已经在处理中（防止重复触发）
    if is_layer_processing(layer3_memory):
        print("[Archive] Layer 3 is already processing, skipping")
        return {}
    
    # 1. 设置处理状态，保存降级数据快照
    fallback_data = {
        "all_messages": list(layer3_memory.get("all_messages", [])),
        "conversation_summaries": list(layer3_memory.get("conversation_summaries", [])),
        "task_registry": dict(layer3_memory.get("task_registry", {})), # 也保存 task_registry 快照
    }
    layer3_memory = start_layer_processing(
        layer3_memory,
        processing_type="compression",
        fallback_data=fallback_data,
    )
    
    print(f"[Archive] Layer 3 compression started, processing {len(to_compress)} messages")
    
    # 获取 Layer 1 的用户上下文
    existing_context = layer1_memory.get("full_data", create_empty_user_context())
    
    try:
        # 2. 调用整理 Agent 处理对话归档（这里会调用 LLM）
        print(f"[Archive] Calling archive_conversation_batch with {len(to_compress)} messages")
        result = archive_conversation_batch(to_compress, existing_context, layer2_memory)
        print(f"[Archive] archive_conversation_batch returned keys: {list(result.keys()) if isinstance(result, dict) else type(result)}")
        
        # 3. 创建对话摘要
        conv_archive = result.get("conversation_archive", {})
        print(f"[Archive] conversation_archive type: {type(conv_archive)}")
        if isinstance(conv_archive, list):
            conv_archive = conv_archive[0] if conv_archive else {}
        if not isinstance(conv_archive, dict):
            print(f"[Archive] Unexpected conversation_archive type: {type(conv_archive)}")
            conv_archive = {}
        turn_count = conv_archive.get("turn_count", len(to_compress))
        key_topics = conv_archive.get("key_topics", [])
        print(f"[Archive] Creating summary with turn_count={turn_count}, key_topics type={type(key_topics)}")
        new_summary = create_conversation_summary(
            summary=conv_archive.get("summary", ""),
            topics=", ".join(key_topics) if isinstance(key_topics, list) else str(key_topics),
            turn_range=f"1-{turn_count}",
        )
        print(f"[Archive] Summary created successfully")
        
        # 4. 通过存储策略路由到 Layer 3 并写入摘要
        decision = _storage_router.route({"type": "conversation_summary", "payload": conv_archive})
        max_summaries = LAYER3_ARCHIVE_CONFIG["max_summaries"]
        if decision.get("target_layer") != "layer3":
            print("[Archive] StorageRouter returned non-layer3 target, fallback to layer3")
        updated_layer3 = StorageProcessor.append_conversation_summary(
            layer3_memory,
            new_summary,
            max_summaries=max_summaries,
            total_turns_delta=len(to_compress),
        )
        print(f"[Archive] Layer3 updated with new summary")
        
        # 更新 Layer 1 长期记忆（如有提取的信息）
        updated_context = result.get("updated_context", existing_context)
        print(f"[Archive] updated_context type: {type(updated_context)}")
        updated_layer1 = StorageProcessor.save_layer1(
            updated_context,
            layer1_memory,
        )
        print(f"[Archive] Layer1 saved")

        # 5. 写入动态情报
        updated_layer2 = layer2_memory
        dynamic_intels = result.get("dynamic_intels", [])
        print(f"[Archive] dynamic_intels type: {type(dynamic_intels)}, count: {len(dynamic_intels) if isinstance(dynamic_intels, list) else 'N/A'}")
        # [FIX] 确保 dynamic_intels 是列表，并且每个元素是 dict
        if not isinstance(dynamic_intels, list):
            dynamic_intels = []
        for intel in dynamic_intels:
            if not isinstance(intel, dict):
                print(f"[Archive] WARNING: Skipping invalid intel type: {type(intel)}")
                continue
            updated_layer2 = StorageProcessor.upsert_dynamic_intel(
                updated_layer2,
                intel,
            )
        
        print(f"[Archive] Layer 3 compressed: {len(to_compress)} messages -> summary, kept {len(to_keep)} messages")
        
    except Exception as e:
        # 压缩失败，清除处理状态但不更新数据
        print(f"[Archive] Layer 3 compression failed: {e}")
        layer3_memory = finish_layer_processing(layer3_memory, increment_version=False)
        return {
            "layer3_memory": layer3_memory,
        }
    
    # 使用 RemoveMessage 删除工作区中的旧消息（全量存储已保留）
    # 仅删除当前 messages 中真实存在的消息，避免 id 不存在导致报错
    messages_in_state = state.get("messages", []) or []
    existing_ids = {get_message_id(m) for m in messages_in_state if get_message_id(m)}
    remove_ops = []
    for m in to_compress:
        mid = get_message_id(m)
        if mid and mid in existing_ids:
            remove_ops.append(RemoveMessage(id=mid))
    
    messages_update = remove_ops if remove_ops else []
    
    return {
        "layer3_memory": updated_layer3,
        "layer1_memory": updated_layer1,
        "layer2_memory": updated_layer2,
        "messages": messages_update,  # 仅删除工作区消息
        "user_context": updated_context,  # 向后兼容
    }


# ============================================================
# Layer 3: 任务思考过程 (Reasoning) 压缩管理
# ============================================================

def check_task_reasoning_compression_needed(state: "AgentState") -> list[tuple[str, str]]:
    """
    检查 Layer 3 中的任务思考过程是否需要压缩
    
    触发条件：
    - 任意活跃任务的 reasoning 列表长度超过 reasoning_limit (n)
    
    Returns:
        需要压缩的任务列表 [(agent_name, task_id), ...]
    """
    layer3_memory = state.get("layer3_memory")
    if not layer3_memory:
        return []
        
    task_registry = layer3_memory.get("task_registry", {})
    limit = LAYER3_ARCHIVE_CONFIG["reasoning_limit"]
    
    tasks_to_compress = []
    
    for agent_name, tasks in task_registry.items():
        if not tasks:
            continue
            
        active_task = get_active_task(tasks)
        if active_task and len(active_task.get("reasoning", [])) > limit:
            tasks_to_compress.append((agent_name, active_task.get("task_id")))
            
    return tasks_to_compress


def compress_task_reasoning(state: "AgentState") -> dict:
    """
    执行任务思考过程压缩
    
    逻辑：
    1. 找到需要压缩的任务
    2. 取出 0 到 n-5 条 reasoning 记录
    3. 调用 LLM 生成摘要
    4. 将摘要追加/更新到 summary 字段
    5. 更新 reasoning 列表，只保留最近 n-5 条
    
    Returns:
        状态更新字典 (layer3_memory)
    """
    tasks_to_compress = check_task_reasoning_compression_needed(state)
    if not tasks_to_compress:
        return {}
        
    layer3_memory = state.get("layer3_memory") or create_empty_layer3_memory()
    
    # 检查是否已经在处理中
    if is_layer_processing(layer3_memory):
        print("[Archive] Layer 3 is processing, skipping reasoning compression")
        return {}
        
    # 设置处理状态
    fallback_data = {
        "all_messages": list(layer3_memory.get("all_messages", [])),
        "conversation_summaries": list(layer3_memory.get("conversation_summaries", [])),
        "task_registry": dict(layer3_memory.get("task_registry", {})),
    }
    layer3_memory = start_layer_processing(
        layer3_memory,
        processing_type="compression",
        fallback_data=fallback_data,
    )
    
    task_registry = layer3_memory.get("task_registry", {})
    # 深度复制 task_registry 以便修改
    updated_registry = {k: [t.copy() for t in v] for k, v in task_registry.items()}
    
    limit = LAYER3_ARCHIVE_CONFIG["reasoning_limit"]
    batch_size = LAYER3_ARCHIVE_CONFIG["reasoning_compression_batch"]
    # 保留最近 batch_size 条，压缩之前的
    keep_count = batch_size 
    
    try:
        for agent_name, task_id in tasks_to_compress:
            tasks = updated_registry.get(agent_name, [])
            target_task = None
            task_idx = -1
            
            for i, t in enumerate(tasks):
                if t.get("task_id") == task_id:
                    target_task = t
                    task_idx = i
                    break
            
            if not target_task:
                continue
                
            reasoning = target_task.get("reasoning", [])
            # 需要压缩的部分：从开头到 (总数 - 保留数)
            split_idx = len(reasoning) - keep_count
            to_compress_items = reasoning[:split_idx]
            to_keep_items = reasoning[split_idx:]
            
            # 调用 LLM 生成摘要
            current_summary = target_task.get("summary", "")
            new_summary = summarize_task_reasoning(to_compress_items, current_summary)
            
            # 更新任务状态
            target_task["summary"] = new_summary
            target_task["reasoning"] = to_keep_items
            updated_registry[agent_name][task_idx] = target_task
            
            print(f"[Archive] Compressed task reasoning for {task_id}: {len(to_compress_items)} items -> summary")

        # 更新 Layer 3
        updated_layer3 = Layer3Memory(
            all_messages=layer3_memory.get("all_messages", []),
            conversation_summaries=layer3_memory.get("conversation_summaries", []),
            task_registry=updated_registry,
            extraction_config=layer3_memory.get("extraction_config", {}),
            processing_status=None,
            last_updated=datetime.now().isoformat(),
            total_turns=layer3_memory.get("total_turns", 0),
            version=layer3_memory.get("version", 1) + 1,
        )
        
        return {"layer3_memory": updated_layer3}
        
    except Exception as e:
        print(f"[Archive] Task reasoning compression failed: {e}")
        layer3_memory = finish_layer_processing(layer3_memory, increment_version=False)
        return {"layer3_memory": layer3_memory}


# ============================================================
# Layer 2: 报告/指南归档管理
# ============================================================

def archive_guide_to_layer2(
    guide: ActionGuideItem,
    state: "AgentState",
) -> dict:
    """
    当行动指南进入终态时，归档到 Layer 2 长期记忆
    
    Args:
        guide: 终态行动指南（completed/cancelled/expired）
        state: 当前状态
    
    Returns:
        状态更新字典
    """
    # 获取现有的长期记忆
    layer1_memory = state.get("layer1_memory") or create_empty_layer1_memory()
    layer2_memory = state.get("layer2_memory") or create_empty_layer2_memory()
    
    existing_context = layer1_memory.get("full_data", create_empty_user_context())
    
    # 仅终态触发归档；paused 不归档（可恢复）
    status = (guide.get("status") or "pending").strip()
    if status not in ("completed", "cancelled", "expired"):
        return {}

    # 调用整理 Agent
    result = archive_completed_guide(guide, existing_context, layer2_memory)
    
    # 更新指南的摘要字段
    guide_summary = result.get("guide_summary", {})
    guide["summary"] = guide_summary.get("summary", "")
    guide["one_liner"] = guide_summary.get("one_liner", "")
    # 保留原状态（completed/cancelled/expired），只补齐时间戳
    if not guide.get("completed_at"):
        guide["completed_at"] = datetime.now().isoformat()
    
    # 更新 Layer 2 长期记忆中的指南列表
    decision = _storage_router.route({"type": "action_guide", "payload": guide})
    if decision.get("target_layer") != "layer2":
        print("[Archive] StorageRouter returned non-layer2 target, fallback to layer2")
    updated_layer2 = StorageProcessor.upsert_completed_guide(
        layer2_memory,
        guide,
        recent_count=LAYER2_ARCHIVE_CONFIG["recent_summary_count"],
        max_one_liner=LAYER2_ARCHIVE_CONFIG["max_one_liner_count"],
    )
    
    # 更新 Layer 1（如有提取的信息）
    updated_context = result.get("updated_context", existing_context)
    updated_layer1 = Layer1Memory(
        full_data=updated_context,
        extraction_config=layer1_memory.get("extraction_config", {}),
        last_updated=datetime.now().isoformat(),
        update_count=layer1_memory.get("update_count", 0) + 1,
    )
    
    return {
        "layer2_memory": updated_layer2,
        "layer1_memory": updated_layer1,
        "user_context": updated_context,  # 向后兼容
    }


def archive_status_to_layer2(
    old_report: StatusReportItem,
    state: "AgentState",
) -> dict:
    """
    当现状分析被新版替换时，归档到 Layer 2 长期记忆
    
    Args:
        old_report: 被替换的旧报告
        state: 当前状态
    
    Returns:
        状态更新字典
    """
    # 获取现有的长期记忆
    layer1_memory = state.get("layer1_memory") or create_empty_layer1_memory()
    layer2_memory = state.get("layer2_memory") or create_empty_layer2_memory()
    
    existing_context = layer1_memory.get("full_data", create_empty_user_context())
    
    # 调用整理 Agent
    result = archive_replaced_status_report(old_report, existing_context, layer2_memory)
    
    # 更新报告的摘要字段
    status_summary = result.get("status_summary", {})
    old_report["summary"] = status_summary.get("summary", "")
    old_report["one_liner"] = status_summary.get("one_liner", "")
    
    # 更新 Layer 2 长期记忆中的报告列表
    decision = _storage_router.route({"type": "status_report", "payload": old_report})
    if decision.get("target_layer") != "layer2":
        print("[Archive] StorageRouter returned non-layer2 target, fallback to layer2")
    updated_layer2 = StorageProcessor.upsert_status_report(
        layer2_memory,
        old_report,
        recent_count=LAYER2_ARCHIVE_CONFIG["recent_summary_count"],
        max_one_liner=LAYER2_ARCHIVE_CONFIG["max_one_liner_count"],
    )
    
    # 更新 Layer 1（如有提取的信息）
    updated_context = result.get("updated_context", existing_context)
    updated_layer1 = Layer1Memory(
        full_data=updated_context,
        extraction_config=layer1_memory.get("extraction_config", {}),
        last_updated=datetime.now().isoformat(),
        update_count=layer1_memory.get("update_count", 0) + 1,
    )

    # 写入动态情报
    updated_layer2 = updated_layer2
    for intel in result.get("dynamic_intels", []):
        updated_layer2 = StorageProcessor.upsert_dynamic_intel(
            updated_layer2,
            intel,
        )
    
    return {
        "layer2_memory": updated_layer2,
        "layer1_memory": updated_layer1,
        "user_context": updated_context,  # 向后兼容
    }


def archive_plan_to_layer2(
    old_plan: ActionPlanItem,
    state: "AgentState",
) -> dict:
    """
    当行动规划被新版替换时，归档到 Layer 2 长期记忆
    - 为旧规划生成 summary/one_liner
    - 提取高价值信息写回 Layer1
    """
    layer1_memory = state.get("layer1_memory") or create_empty_layer1_memory()
    layer2_memory = state.get("layer2_memory") or create_empty_layer2_memory()

    existing_context = layer1_memory.get("full_data", create_empty_user_context())

    result = archive_replaced_action_plan(old_plan, existing_context, layer2_memory)

    plan_summary = result.get("plan_summary", {})
    old_plan["summary"] = plan_summary.get("summary", "")
    old_plan["one_liner"] = plan_summary.get("one_liner", "")

    decision = _storage_router.route({"type": "action_plan", "payload": old_plan})
    if decision.get("target_layer") != "layer2":
        print("[Archive] StorageRouter returned non-layer2 target, fallback to layer2")

    updated_layer2 = StorageProcessor.upsert_action_plan(
        layer2_memory,
        old_plan,
        recent_count=LAYER2_ARCHIVE_CONFIG["recent_summary_count"],
        max_one_liner=LAYER2_ARCHIVE_CONFIG["max_one_liner_count"],
    )

    updated_context = result.get("updated_context", existing_context)
    updated_layer1 = Layer1Memory(
        full_data=updated_context,
        extraction_config=layer1_memory.get("extraction_config", {}),
        last_updated=datetime.now().isoformat(),
        update_count=layer1_memory.get("update_count", 0) + 1,
    )

    return {
        "layer2_memory": updated_layer2,
        "layer1_memory": updated_layer1,
        "user_context": updated_context,  # 向后兼容
    }


# ============================================================
# 统一归档入口
# ============================================================

def process_archiving_if_needed(state: "AgentState") -> dict:
    """
    统一归档入口：检查并处理所有需要归档的内容
    
    在每轮结束时调用，检查：
    1. Layer 3 是否需要对话压缩
    2. Layer 3 是否需要任务思考过程压缩
    3. Layer 2 是否有已完成的行动指南需要归档 (在 main_agent 中已触发，这里略)
    
    Returns:
        状态更新字典（如果没有需要归档的内容，返回空字典）
    """
    updates = {}
    
    # 1. 检查 Layer 3 对话压缩
    if check_layer3_compression_needed(state):
        compression_result = compress_layer3(state)
        updates.update(compression_result)
        
    # 2. 检查任务思考过程压缩
    if check_task_reasoning_compression_needed(state):
        reasoning_result = compress_task_reasoning(state)
        # 合并更新 (小心覆盖)
        if "layer3_memory" in updates and "layer3_memory" in reasoning_result:
            # 如果两者都更新了 layer3，需要小心合并
            # 简单起见，这里假设两者不会冲突太严重，或者我们接受后者的覆盖
            # 更好的做法是在 memory 对象内部做合并，或者串行处理并传递更新后的 state
            pass # TODO: 处理合并冲突，暂且认为概率较低
        updates.update(reasoning_result)
    
    return updates


def refine_on_onboarding_complete(state: "AgentState") -> dict:
    """
    Onboarding 结束时触发的提纯：
    - 读取全量对话
    - 提取静态情报 & 动态情报
    - 生成对话摘要（可选）
    """
    layer1_memory = state.get("layer1_memory") or create_empty_layer1_memory()
    layer2_memory = state.get("layer2_memory") or create_empty_layer2_memory()
    layer3_memory = state.get("layer3_memory") or create_empty_layer3_memory()

    messages = layer3_memory.get("all_messages", state.get("messages", []))
    if not messages:
        return {}

    existing_context = layer1_memory.get("full_data", create_empty_user_context())
    result = archive_conversation_batch(messages, existing_context, layer2_memory)

    updated_context = result.get("updated_context", existing_context)
    updated_layer1 = StorageProcessor.save_layer1(updated_context, layer1_memory)

    updated_layer2 = layer2_memory
    for intel in result.get("dynamic_intels", []):
        updated_layer2 = StorageProcessor.upsert_dynamic_intel(updated_layer2, intel)

    updated_layer3 = layer3_memory
    conv_archive = result.get("conversation_archive")
    if isinstance(conv_archive, list):
        conv_archive = conv_archive[0] if conv_archive else {}
    if not isinstance(conv_archive, dict):
        if conv_archive:
            print(f"[Archive] Unexpected conversation_archive type: {type(conv_archive)}")
        conv_archive = {}
    if conv_archive:
        turn_count = conv_archive.get("turn_count", len(messages))
        key_topics = conv_archive.get("key_topics", [])
        new_summary = create_conversation_summary(
            summary=conv_archive.get("summary", ""),
            topics=", ".join(key_topics) if isinstance(key_topics, list) else str(key_topics),
            turn_range=f"1-{turn_count}",
        )
        max_summaries = LAYER3_ARCHIVE_CONFIG["max_summaries"]
        updated_layer3 = StorageProcessor.append_conversation_summary(
            layer3_memory,
            new_summary,
            max_summaries=max_summaries,
            total_turns_delta=turn_count,
        )

    return {
        "layer1_memory": updated_layer1,
        "layer2_memory": updated_layer2,
        "layer3_memory": updated_layer3,
        "user_context": updated_context,
    }


# ============================================================
# 调试/查询函数
# ============================================================

def get_archive_stats(state: "AgentState") -> dict:
    """
    获取归档统计信息（用于调试）
    """
    layer2_memory = state.get("layer2_memory", {})
    layer3_memory = state.get("layer3_memory", {})
    
    all_messages = layer3_memory.get("all_messages", state.get("messages", []))
    all_guides = layer2_memory.get("action_guides", [])
    current_report = layer2_memory.get("current_status_report")
    history_reports = layer2_memory.get("status_report_history", [])
    
    return {
        "conversation_turns": len(all_messages),
        "conversation_summaries": len(layer3_memory.get("conversation_summaries", [])),
        "status_reports_total": (1 if current_report else 0) + len(history_reports),
        "status_reports_history": len(history_reports),
        "action_guides_total": len(all_guides),
        "action_guides_terminal": len([g for g in all_guides if g.get("status") in ("completed", "cancelled", "expired")]),
        "compression_needed": check_layer3_compression_needed(state),
    }


def get_full_history_content(
    state: "AgentState",
    layer: str,
    item_type: str,
    index: int,
) -> Optional[str]:
    """
    获取历史记录的完整内容（抽屉式调用）
    
    Args:
        state: 当前状态
        layer: "layer2" 或 "layer3"
        item_type: "status_report" / "action_guide" / "conversation"
        index: 历史记录索引
    
    Returns:
        完整内容，如果不存在返回 None
    """
    if layer == "layer2":
        layer2_memory = state.get("layer2_memory", {})
        
        if item_type == "status_report":
            history = layer2_memory.get("status_report_history", [])
            if 0 <= index < len(history):
                return history[index].get("report_content")
        
        elif item_type == "action_guide":
            guides = layer2_memory.get("action_guides", [])
            terminal = [g for g in guides if g.get("status") in ("completed", "cancelled", "expired")]
            if 0 <= index < len(terminal):
                return terminal[index].get("guide", {}).get("guide_content")
    
    elif layer == "layer3":
        layer3_memory = state.get("layer3_memory", {})
        
        if item_type == "conversation":
            summaries = layer3_memory.get("conversation_summaries", [])
            if 0 <= index < len(summaries):
                return summaries[index].get("summary")
    
    # 向后兼容：尝试从旧版 history_archive 获取
    archive = state.get("history_archive", {})
    type_map = {
        "status_report": "status_history",
        "action_guide": "guide_history",
        "conversation": "conversation_archive",
    }
    
    history_key = type_map.get(item_type)
    if history_key:
        history_list = archive.get(history_key, [])
        if 0 <= index < len(history_list):
            return history_list[index].get("full_content", history_list[index].get("summary"))
    
    return None
