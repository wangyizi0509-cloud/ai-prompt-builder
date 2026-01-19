"""
用户认证与 Thread 关联调试脚本
用于诊断用户登录后找不到 thread_id 的问题
"""

import asyncio
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'agent_impl'))

from dotenv import load_dotenv
load_dotenv()

from supabase_service.client import get_thread_by_user, create_user_thread, get_user_by_id


async def debug_user_thread(user_id: str, email: str):
    """
    调试指定用户的 thread 绑定情况
    """
    print(f"\n{'='*60}")
    print(f"调试用户: {email} (ID: {user_id})")
    print(f"{'='*60}\n")

    # 1. 检查用户是否存在
    print("1. 检查用户是否存在...")
    user = await get_user_by_id(user_id)
    if user:
        print(f"   ✓ 用户存在: {user['username']} ({user['email']})")
    else:
        print(f"   ✗ 用户不存在")
        return

    # 2. 检查用户的 thread 绑定
    print("\n2. 检查用户的 thread 绑定...")
    user_thread = await get_thread_by_user(user_id)
    if user_thread:
        print(f"   ✓ 找到 thread 绑定:")
        print(f"     - Thread ID: {user_thread['thread_id']}")
        print(f"     - 创建时间: {user_thread['created_at']}")
        print(f"     - 更新时间: {user_thread['updated_at']}")
    else:
        print(f"   ✗ 未找到 thread 绑定")
        print(f"   提示: 用户需要至少发起一次聊天才能创建 thread 绑定")

    # 3. 测试 API 调用
    print("\n3. 测试 API 调用...")
    import requests
    
    # 获取 token
    print("   3.1 获取 JWT Token...")
    try:
        login_response = requests.post(
            'http://localhost:8000/api/auth/login',
            json={
                'email': email,
                'password': 'password123'
            }
        )
        
        if login_response.status_code == 200:
            login_data = login_response.json()
            token = login_data.get('token')
            print(f"   ✓ 登录成功，获取到 token")
            
            # 获取用户 thread 信息
            print("\n   3.2 获取用户 thread 信息...")
            thread_response = requests.get(
                'http://localhost:8000/api/auth/me/thread',
                headers={'Authorization': f'Bearer {token}'}
            )
            
            if thread_response.status_code == 200:
                thread_data = thread_response.json()
                print(f"   ✓ API 调用成功:")
                print(f"     - Success: {thread_data.get('success')}")
                print(f"     - Thread ID: {thread_data.get('thread_id')}")
            else:
                print(f"   ✗ API 调用失败: {thread_response.status_code}")
                print(f"     错误信息: {thread_response.text}")
        else:
            print(f"   ✗ 登录失败: {login_response.status_code}")
            print(f"     错误信息: {login_response.text}")
    except requests.exceptions.ConnectionError:
        print(f"   ✗ 无法连接到服务器 (http://localhost:8000)")
        print(f"     提示: 请确保后端服务已启动")
    except Exception as e:
        print(f"   ✗ 发生错误: {str(e)}")

    print(f"\n{'='*60}")
    print("调试完成")
    print(f"{'='*60}\n")


async def main():
    """
    主函数
    """
    if len(sys.argv) > 1:
        # 从命令行参数获取用户 ID
        user_id = sys.argv[1]
        email = input("请输入用户邮箱: ")
    else:
        # 测试用户列表
        print("可用测试用户:")
        test_users = [
            ('test01@example.com', 'fbb05249-f46c-4af5-b819-3e38cc830156'),
            ('test02@example.com', '136ecd08-856b-40fd-8e6a-98c12e687415'),
            ('test03@example.com', '41e84541-8be4-4511-9060-2bca12fbee0e'),
            ('test04@example.com', 'ecdb1e7c-3e1c-4a48-a0d1-f8fe66c111d5'),
            ('test05@example.com', '1a33c9a1-a45b-432f-b1d9-b9502b0379f1'),
        ]
        
        for i, (email, user_id) in enumerate(test_users, 1):
            print(f"  {i}. {email} (ID: {user_id})")
        
        print("\n请选择要调试的用户 (1-5): ", end="")
        choice = input()
        
        try:
            choice_idx = int(choice) - 1
            if 0 <= choice_idx < len(test_users):
                email, user_id = test_users[choice_idx]
            else:
                print("无效的选择")
                return
        except ValueError:
            print("无效的输入")
            return
    
    await debug_user_thread(user_id, email)


if __name__ == '__main__':
    asyncio.run(main())
