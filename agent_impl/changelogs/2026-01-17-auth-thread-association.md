# 用户认证与 Thread 关联功能 - 2026-01-17

## 概述
实现了基于 JWT 的用户认证系统，并建立了用户与 LangGraph Thread 的一一关联机制，确保每个用户拥有持久化的会话上下文。

## 变更内容

### 新增数据库表
创建了 `user_threads` 表用于存储用户 ID 与 Thread ID 的映射关系：
- `id`: UUID 主键
- `user_id`: 用户 ID（外键关联 users 表）
- `thread_id`: LangGraph Thread ID（唯一）
- `created_at` / `updated_at`: 时间戳

配置了 RLS（行级安全）策略，确保用户只能访问自己的 Thread。

### 新增数据库迁移文件
- `supabase/migrations/create_user_threads_table.sql`

### 修改的文件
- `supabase_service/client.py` - 添加 user_threads 表操作函数
- `auth_utils.py` - 已存在，未修改
- `api/auth.py` - 已存在，未修改
- `api/sdk_client.py` - 更新 `ensure_thread_exists()` 支持用户绑定
- `api/chat.py` - 添加可选用户认证依赖
- `api/stream.py` - 添加可选用户认证依赖
- `frontend/index.html` - 为 API 请求添加 Authorization header
- `frontend/auth.html` - 已存在，未修改

### 新增功能函数
在 `supabase_service/client.py` 中添加：
- `create_user_thread(user_id, thread_id)` - 创建用户-thread 映射
- `get_thread_by_user(user_id)` - 查询用户的 thread
- `get_user_by_thread(thread_id)` - 反向查询
- `get_or_create_user_thread(user_id, thread_id)` - 幂等操作

## 技术细节

### 实现要点
1. **可选认证设计**：使用 `get_optional_user` 而非 `get_current_user`，允许匿名用户继续使用
2. **Thread 绑定逻辑**：当用户登录后发起聊天时，自动创建或更新 user_threads 映射
3. **幂等操作**：`get_or_create_user_thread()` 确保即使重复调用也不会创建重复记录
4. **RLS 安全策略**：配置了行级安全，用户只能访问自己的 thread 数据

### Thread 管理流程
1. 用户发起聊天时，后端检查 `user_threads` 表
2. 如果存在映射，复用该 `thread_id`
3. 如果不存在，创建新的 UUID 作为 `thread_id`，调用 LangGraph SDK 创建 Thread，并写入 `user_threads` 表
4. 前端所有 API 请求自动携带 `Authorization: Bearer <token>` header

### 兼容性说明
**向后兼容**：
- 未登录用户仍可正常使用所有功能，只是没有持久化的 thread
- API 路径完全不变，行为向后兼容
- 已有的匿名会话不会被破坏

**前端兼容**：
- 登录/注册页面已存在并正常工作
- 新增的 Authorization header 不会影响未登录用户（token 为空字符串）

## 验证结果

- ✅ 数据库迁移脚本语法正确
- ✅ Supabase 服务层函数实现完成
- ✅ `ensure_thread_exists()` 函数支持可选 user_id 参数
- ✅ `/api/chat` 和 `/api/chat/stream` 端点添加了可选认证依赖
- ✅ 前端 API 请求添加了 Authorization header
- ✅ 使用 `get_optional_user` 确保匿名用户仍可访问

## 后续优化建议

1. **Token 刷新机制**：当前 JWT 有效期为 7 天，后续可添加 refresh token 机制
2. **Thread 清理策略**：为长期不活跃的用户 thread 添加自动清理机制
3. **Session 管理**：支持多设备登录，每个设备独立的 session
4. **权限细化**：根据用户角色提供不同的功能访问权限

## 影响范围

### 代码文件
- 新增：1 个数据库迁移文件
- 修改：4 个后端文件（`supabase_service/client.py`, `api/sdk_client.py`, `api/chat.py`, `api/stream.py`）
- 修改：1 个前端文件（`frontend/index.html`）

### 数据库
- 新增表：`user_threads`
- 新增索引：`idx_user_threads_user_id`, `idx_user_threads_thread_id`
- 新增 RLS 策略：2 个（匿名用户禁止访问，认证用户可访问自己的数据）

### API 接口
- 路径无变化
- `/api/chat` 和 `/api/chat/stream` 现在支持可选的用户认证
- `/api/auth/register`, `/api/auth/login`, `/api/auth/me` 已存在并正常工作

### 部署方式
需要执行以下步骤：
1. 应用数据库迁移：`supabase/migrations/create_user_threads_table.sql`
2. 确保 `.env` 中包含 `JWT_SECRET` 环境变量
3. 重启后端服务
