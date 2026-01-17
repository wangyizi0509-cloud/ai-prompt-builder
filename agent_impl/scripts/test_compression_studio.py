#!/usr/bin/env python3
"""
测试 Studio 模式下的对话压缩功能

目标：验证当用户消息轮次超过 threshold（4）时，是否正确触发压缩并生成 conversation_summaries

用法：
    python scripts/test_compression_studio.py

前置条件：
    - Studio 正在运行（./start_studio.sh）
    - API 地址：http://127.0.0.1:2024
"""

import requests
import json
import time
import uuid
from datetime import datetime

# Studio API 配置
STUDIO_API = "http://127.0.0.1:2024"
GRAPH_NAME = "crushe_agent"

def create_thread() -> str:
    """创建新线程"""
    resp = requests.post(f"{STUDIO_API}/threads", json={})
    resp.raise_for_status()
    thread_id = resp.json()["thread_id"]
    print(f"✅ 创建线程: {thread_id}")
    return thread_id

def send_message(thread_id: str, content: str, turn: int) -> dict:
    """发送消息并等待回复（阻塞模式）"""
    print(f"\n--- 轮次 {turn} ---")
    print(f"📤 发送: {content}")
    
    # 使用 wait 模式创建 run（阻塞直到完成）
    resp = requests.post(
        f"{STUDIO_API}/threads/{thread_id}/runs/wait",
        json={
            "assistant_id": GRAPH_NAME,
            "input": {
                "messages": [
                    {"role": "user", "content": content}
                ]
            },
        },
        timeout=120,  # 2分钟超时
    )
    resp.raise_for_status()
    
    # 解析响应
    result = resp.json()
    final_state = result
    
    messages = final_state.get("messages", [])
    if messages:
        last_msg = messages[-1]
        msg_content = last_msg.get("content", "") if isinstance(last_msg, dict) else str(last_msg)
        print(f"📥 回复: {msg_content[:100]}...")
    
    return final_state

def get_thread_state(thread_id: str) -> dict:
    """获取线程当前状态"""
    resp = requests.get(f"{STUDIO_API}/threads/{thread_id}/state")
    resp.raise_for_status()
    return resp.json()

def analyze_compression_status(state: dict) -> None:
    """分析压缩状态"""
    print("\n" + "=" * 60)
    print("📊 压缩状态分析")
    print("=" * 60)
    
    # 检查 layer3_memory
    layer3_memory = state.get("values", {}).get("layer3_memory") or {}
    all_messages = layer3_memory.get("all_messages", [])
    summaries = layer3_memory.get("conversation_summaries", [])
    
    print(f"📝 layer3_memory.all_messages 数量: {len(all_messages)}")
    print(f"📋 conversation_summaries 数量: {len(summaries)}")
    
    # 统计用户消息数量
    user_turns = 0
    for msg in all_messages:
        role = None
        if isinstance(msg, dict):
            role = msg.get("type") or msg.get("role")
        if role in ("human", "user"):
            user_turns += 1
    print(f"👤 用户轮次: {user_turns}")
    
    # 检查维护队列
    maintenance_queue = state.get("values", {}).get("maintenance_queue", [])
    print(f"🔧 maintenance_queue: {len(maintenance_queue)} 个任务")
    for item in maintenance_queue:
        if isinstance(item, dict):
            print(f"   - {item.get('type')}: {item.get('status')} ({item.get('task_key')})")
    
    # 检查维护标志
    maintenance_flags = state.get("values", {}).get("maintenance_flags", {})
    print(f"🚩 maintenance_flags: {maintenance_flags}")
    
    # 输出摘要详情
    if summaries:
        print("\n📄 生成的对话摘要:")
        for i, summary in enumerate(summaries):
            print(f"   [{i+1}] {summary.get('summary', '')[:80]}...")
            print(f"       topics: {summary.get('topics', '')}")
            print(f"       turn_range: {summary.get('turn_range', '')}")
    else:
        print("\n⚠️  尚未生成对话摘要")

def main():
    print("=" * 60)
    print("🧪 Studio 对话压缩测试")
    print(f"⏰ {datetime.now().isoformat()}")
    print("=" * 60)
    
    # 测试消息（模拟真实对话）
    test_messages = [
        "你好，我想咨询一些恋爱问题",
        "我喜欢一个女生，但不知道怎么开口",
        "我们是同事关系，平时会一起吃午饭",
        "她好像对我也有好感，但我不太确定",
        "上周她主动约我看电影，这是什么信号？",  # 第 5 轮，应该触发压缩
        "电影看完后我们一起吃了晚饭，聊得很开心",  # 第 6 轮
    ]
    
    try:
        # 1. 创建新线程
        thread_id = create_thread()
        
        # 2. 连续发送消息
        for i, msg in enumerate(test_messages, 1):
            state = send_message(thread_id, msg, i)
            time.sleep(1)  # 等待处理完成
        
        # 3. 获取最终状态并分析
        print("\n⏳ 等待 3 秒让后台任务完成...")
        time.sleep(3)
        
        final_state = get_thread_state(thread_id)
        analyze_compression_status(final_state)
        
        print("\n" + "=" * 60)
        print("✅ 测试完成")
        print(f"📌 Thread ID: {thread_id}")
        print("=" * 60)
        
    except requests.exceptions.ConnectionError:
        print("❌ 无法连接到 Studio API，请确保 Studio 正在运行")
        print("   运行命令: cd agent_impl && ./start_studio.sh")
    except Exception as e:
        print(f"❌ 测试失败: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    main()
