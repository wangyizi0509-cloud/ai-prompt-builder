# API 模块化重构 - 2026-01-17

## 概述
将原本集中在 `server.py` 中的所有 API 接口按功能点拆分为独立模块，提升代码可维护性和可扩展性。

## 变更内容

### 新增文件结构
```
agent_impl/
├── api/                          # 新增 API 模块目录
│   ├── __init__.py               # 统一路由导出
│   ├── auth.py                  # 认证相关接口
│   ├── upload.py                # 图片上传接口
│   ├── chat.py                  # 聊天接口
│   ├── stream.py                # 流式聊天接口
│   ├── guide.py                 # 指南管理接口
│   └── debug.py                # 调试接口
└── server.py                    # 精简后的主文件
```

### 模块划分

#### 1. 认证模块 (`api/auth.py`)
负责用户认证相关功能：
- `POST /api/auth/register` - 用户注册
- `POST /api/auth/login` - 用户登录
- `GET /api/auth/me` - 获取当前用户信息

#### 2. 上传模块 (`api/upload.py`)
负责文件上传处理：
- `POST /api/upload-screenshot` - 上传截图并转换为文本

#### 3. 聊天模块 (`api/chat.py`)
负责标准聊天接口及后台维护任务：
- `POST /api/chat` - 标准聊天接口
- `_run_maintenance_tasks()` - 后台维护任务（提纯/归档/压缩）

#### 4. 流式聊天模块 (`api/stream.py`)
负责流式聊天接口：
- `POST /api/chat/stream` - SSE 流式聊天接口
  - 支持 values/updates/messages/debug 多种流模式

#### 5. 指南管理模块 (`api/guide.py`)
负责行动指南状态管理：
- `POST /api/update_guide_status` - 更新指南状态（6状态机）
- `POST /api/complete_guide` - 完成指南（兼容旧接口）

#### 6. 调试模块 (`api/debug.py`)
负责调试和状态查看：
- `GET /api/debug/context/{session_id}` - 获取会话上下文调试信息
- `GET /api/debug/detail/status_report/{session_id}/{report_id}` - 获取现状报告全文
- `GET /api/debug/detail/action_guide/{session_id}/{guide_id}` - 获取行动指南全文
- `GET /api/debug/detail/compressed_messages/{session_id}/{summary_index}` - 获取压缩消息详情

### 精简 server.py
原 `server.py` 从 1244 行精简至 67 行，仅保留：
- FastAPI 应用初始化
- CORS 中间件配置
- LangGraph SDK 配置和工具函数 (`get_client`, `session_to_thread_id`, `ensure_thread_exists`)
- API 路由引入 (`app.include_router(api_router)`)
- 前端静态文件挂载

## 技术细节

### 路由统一管理
```python
# api/__init__.py
from fastapi import APIRouter

from .auth import router as auth_router
from .upload import router as upload_router
from .chat import router as chat_router
from .stream import router as stream_router
from .guide import router as guide_router
from .debug import router as debug_router

api_router = APIRouter()

api_router.include_router(auth_router, prefix="/api/auth", tags=["认证"])
api_router.include_router(upload_router, tags=["上传"])
api_router.include_router(chat_router, tags=["聊天"])
api_router.include_router(stream_router, tags=["流式聊天"])
api_router.include_router(guide_router, tags=["指南"])
api_router.include_router(debug_router, prefix="/api/debug", tags=["调试"])
```

### 依赖说明
- 各模块按需导入依赖，避免全局导入导致的性能问题
- `graph.*` 相关导入在各 endpoint 内按需懒加载
- 共享的配置函数（如 `_run_maintenance_tasks`）在需要时内部导入

## 兼容性

### API 路径保持不变
所有 API 路径与重构前完全一致，无需修改前端代码。

### 数据格式保持不变
请求和响应的数据格式完全兼容原有实现。

## 验证结果

- ✅ 所有 API 模块通过 Python 编译检查
- ✅ `server.py` 通过 Python 编译检查
- ✅ 路由结构正确加载
- ✅ 语法错误已修复（字符串引号问题）

## 后续优化建议

1. **添加 API 文档标签**：为每个路由模块添加更详细的 OpenAPI 标签和描述
2. **提取共享工具函数**：如 `_append_debug_log`、`_safe_update_state` 等可考虑提取到 `utils/` 目录
3. **添加单元测试**：为每个 API 模块编写独立的单元测试
4. **性能监控**：为关键接口添加性能监控和日志记录

## 影响范围

- 代码文件：新增 7 个文件，重构 1 个文件
- API 接口：无变化（路径和行为完全兼容）
- 部署方式：无变化（`python server.py` 仍然可用）
