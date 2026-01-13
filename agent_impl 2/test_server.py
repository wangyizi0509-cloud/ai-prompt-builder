#!/usr/bin/env python3
"""测试服务器启动"""
import os
import sys

# 添加路径
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

print("1. 测试基础导入...")
try:
    from pydantic import BaseModel
    print("   ✓ pydantic 导入成功")
except Exception as e:
    print(f"   ✗ pydantic 导入失败: {e}")
    sys.exit(1)

try:
    from fastapi import FastAPI
    print("   ✓ fastapi 导入成功")
except Exception as e:
    print(f"   ✗ fastapi 导入失败: {e}")
    sys.exit(1)

print("\n2. 测试工作流导入...")
try:
    from graph.workflow import get_workflow
    print("   ✓ workflow 导入成功")
except Exception as e:
    print(f"   ✗ workflow 导入失败: {e}")
    import traceback
    traceback.print_exc()
    sys.exit(1)

print("\n3. 测试状态导入...")
try:
    from graph.state import create_initial_state
    print("   ✓ state 导入成功")
except Exception as e:
    print(f"   ✗ state 导入失败: {e}")
    import traceback
    traceback.print_exc()
    sys.exit(1)

print("\n4. 测试创建 FastAPI 应用...")
try:
    app = FastAPI(title="Test")
    print("   ✓ FastAPI 应用创建成功")
except Exception as e:
    print(f"   ✗ FastAPI 应用创建失败: {e}")
    sys.exit(1)

print("\n✅ 所有测试通过！服务器应该可以正常启动。")
print("\n现在可以运行: python agent_impl/server.py")
