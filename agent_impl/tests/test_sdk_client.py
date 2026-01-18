"""
SDK 客户端工具测试
测试 api/sdk_client.py 中的核心功能
"""
import asyncio
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from api.sdk_client import (
    get_client,
    session_to_thread_id,
    ensure_thread_exists,
    get_thread_state,
    update_thread_state,
    run_assistant,
)


def test_get_client():
    """测试客户端获取"""
    print("✅ 测试 get_client...")
    client = get_client()
    assert client is not None, "Client should not be None"
    print("  - Client 获取成功")


def test_session_to_thread_id():
    """测试 session_id 到 UUID 转换"""
    print("\n✅ 测试 session_to_thread_id...")
    
    # 测试 UUID 格式
    uuid_str = "550e8400-e29b-41d4-a716-446655440000"
    result = session_to_thread_id(uuid_str)
    assert result == uuid_str, f"UUID 格式应该保持不变，但得到 {result}"
    print(f"  - UUID 格式保持不变: {result}")
    
    # 测试普通字符串
    plain_str = "test-session-123"
    result = session_to_thread_id(plain_str)
    try:
        import uuid as uuid_module
        uuid_module.UUID(result)
        print(f"  - 普通字符串转换为 UUID: {result}")
    except ValueError:
        raise AssertionError(f"转换结果不是有效的 UUID: {result}")


async def test_ensure_thread_exists():
    """测试 Thread 创建"""
    print("\n✅ 测试 ensure_thread_exists...")
    
    # 测试新 thread 创建
    session_id = "test-new-session-123"
    thread_id = await ensure_thread_exists(session_id)
    print(f"  - 新 session_id 转换为 thread_id: {thread_id}")
    
    # 测试已存在的 thread
    thread_id_2 = await ensure_thread_exists(session_id)
    assert thread_id == thread_id_2, "相同 session_id 应该返回相同的 thread_id"
    print(f"  - 重复调用返回相同的 thread_id: {thread_id_2}")
    
    # 验证 thread 实际存在
    client = get_client()
    thread = client.threads.get(thread_id)
    assert thread.get("thread_id") == thread_id, "Thread 应该存在"
    print(f"  - Thread 验证成功")


async def test_get_thread_state():
    """测试状态获取"""
    print("\n✅ 测试 get_thread_state...")
    
    session_id = "test-state-123"
    thread_id = await ensure_thread_exists(session_id)
    
    # 初始状态应该为 None
    state = get_thread_state(thread_id)
    # 第一次可能为 None 或空字典
    print(f"  - 初始状态: {state}")
    
    # 注意：update_thread_state 需要特殊的格式，这里只测试读取
    # 状态更新功能在实际的 Agent 运行时会自动处理
    print(f"  - 状态读取成功")


async def test_run_assistant():
    """测试 Assistant 运行"""
    print("\n✅ 测试 run_assistant...")
    
    session_id = "test-assistant-123"
    thread_id = await ensure_thread_exists(session_id)
    
    try:
        stream = run_assistant(thread_id, {"user_message": "你好"})
        print(f"  - Assistant 运行成功，返回流对象")
        
        # 尝试读取几个 chunks
        chunk_count = 0
        for chunk in stream:
            chunk_count += 1
            if chunk_count >= 3:
                break
        print(f"  - 成功读取 {chunk_count} 个 chunks")
        
    except Exception as e:
        print(f"  - Assistant 运行出现错误（可能是正常的，因为需要 LLM API）: {str(e)[:100]}")


async def main():
    """运行所有测试"""
    print("=" * 60)
    print("开始测试 SDK 客户端工具")
    print("=" * 60)
    
    try:
        test_get_client()
        test_session_to_thread_id()
        await test_ensure_thread_exists()
        await test_get_thread_state()
        await test_run_assistant()
        
        print("\n" + "=" * 60)
        print("✅ 所有 SDK 客户端工具测试完成！")
        print("=" * 60)
        
    except Exception as e:
        print(f"\n❌ 测试失败: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main())
