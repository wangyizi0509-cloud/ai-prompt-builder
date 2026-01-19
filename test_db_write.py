"""
测试数据库写入功能
"""

import asyncio
import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'agent_impl'))

from dotenv import load_dotenv
load_dotenv()

from supabase_service.client import (
    is_supabase_configured,
    get_thread_by_user,
    create_user_thread,
    get_or_create_user_thread,
    get_user_by_id
)


async def test_db_operations():
    """
    测试数据库操作
    """
    print("测试数据库操作")
    print("="*60)
    
    # 1. 检查配置
    print("\n1. 检查 Supabase 配置...")
    if is_supabase_configured():
        print("   ✓ Supabase 已配置")
    else:
        print("   ✗ Supabase 未配置")
        return
    
    # 2. 测试查询用户
    print("\n2. 测试查询用户...")
    user_id = "fbb05249-f46c-4af5-b819-3e38cc830156"
    user = await get_user_by_id(user_id)
    if user:
        print(f"   ✓ 用户存在: {user['username']} ({user['email']})")
    else:
        print(f"   ✗ 用户不存在")
        return
    
    # 3. 测试查询用户的 thread
    print("\n3. 测试查询用户的 thread...")
    user_thread = await get_thread_by_user(user_id)
    if user_thread:
        print(f"   ✓ 找到 thread 绑定:")
        print(f"     - Thread ID: {user_thread['thread_id']}")
        print(f"     - Created: {user_thread['created_at']}")
    else:
        print(f"   ✗ 未找到 thread 绑定")
    
    # 4. 测试创建 thread 绑定
    print("\n4. 测试创建 thread 绑定...")
    import uuid
    test_thread_id = str(uuid.uuid4())
    result = await create_user_thread(user_id, test_thread_id)
    
    if result['success']:
        print(f"   ✓ 创建成功:")
        print(f"     - Thread ID: {result['thread']['thread_id']}")
        print(f"     - User ID: {result['thread']['user_id']}")
    else:
        print(f"   ✗ 创建失败:")
        print(f"     - 错误: {result.get('error')}")
    
    # 5. 再次查询
    print("\n5. 再次查询用户的 thread...")
    user_thread = await get_thread_by_user(user_id)
    if user_thread:
        print(f"   ✓ 找到 thread 绑定:")
        print(f"     - Thread ID: {user_thread['thread_id']}")
    else:
        print(f"   ✗ 仍未找到 thread 绑定")
    
    print("\n" + "="*60)
    print("测试完成")
    print("="*60)


if __name__ == '__main__':
    asyncio.run(test_db_operations())
