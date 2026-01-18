# 用户认证与 Thread 关联功能测试清单 - 2026-01-17

## 测试前准备

### 环境检查
- [ ] 确认 Supabase 连接正常
- [ ] 确认 `.env` 文件中包含 `JWT_SECRET` 环境变量
- [ ] 确认后端服务已启动（`python -m uvicorn agent_impl.server:app`）
- [ ] 确认前端可访问（http://localhost:8000）

### 数据库迁移
- [ ] 执行 `supabase/migrations/create_user_threads_table.sql` 迁移脚本
- [ ] 验证 `user_threads` 表已创建
- [ ] 验证索引 `idx_user_threads_user_id` 和 `idx_user_threads_thread_id` 已创建
- [ ] 验证 RLS 策略已启用

---

## 1. 数据库测试

### 表结构验证
- [ ] 连接到 Supabase 数据库
- [ ] 检查 `user_threads` 表结构：
  - [ ] `id` 字段存在，类型为 UUID，默认值 gen_random_uuid()
  - [ ] `user_id` 字段存在，类型为 UUID，NOT NULL 约束
  - [ ] `thread_id` 字段存在，类型为 VARCHAR(255)，NOT NULL 约束，UNIQUE 约束
  - [ ] `created_at` 字段存在，类型为 TIMESTAMP WITH TIME ZONE
  - [ ] `updated_at` 字段存在，类型为 TIMESTAMP WITH TIME ZONE

### 索引验证
- [ ] 验证 `idx_user_threads_user_id` 索引存在
- [ ] 验证 `idx_user_threads_thread_id` 索引存在

### 触发器验证
- [ ] 验证 `update_updated_at_column()` 函数已创建
- [ ] 验证 `update_user_threads_updated_at` 触发器已创建
- [ ] 测试触发器：更新记录，验证 `updated_at` 字段自动更新

### RLS 策略验证
- [ ] 验证 RLS 已启用：`ALTER TABLE user_threads ENABLE ROW LEVEL SECURITY`
- [ ] 验证策略 "Anonymous users cannot access user_threads" 存在
- [ ] 验证策略 "Authenticated users can access own threads" 存在

### 权限验证
```sql
-- 检查 anon 角色权限
SELECT grantee, table_name, privilege_type 
FROM information_schema.role_table_grants 
WHERE table_schema = 'public' 
  AND table_name = 'user_threads' 
  AND grantee = 'anon';

-- 检查 authenticated 角色权限
SELECT grantee, table_name, privilege_type 
FROM information_schema.role_table_grants 
WHERE table_schema = 'public' 
  AND table_name = 'user_threads' 
  AND grantee = 'authenticated';
```
- [ ] anon 角色有 USAGE 权限
- [ ] authenticated 角色有 ALL PRIVILEGES 权限

---

## 2. 认证 API 测试

### 注册接口测试
**端点**: `POST /api/auth/register`

- [ ] 正常注册（新邮箱）
  ```bash
  curl -X POST http://localhost:8000/api/auth/register \
    -H "Content-Type: application/json" \
    -d '{
      "email": "test@example.com",
      "password": "password123",
      "username": "testuser"
    }'
  ```
  - [ ] 返回 HTTP 200
  - [ ] 响应包含 `success: true`
  - [ ] 响应包含 `token` 字段（JWT）
  - [ ] 响应包含 `user` 对象（id, email, username, created_at）

- [ ] 重复邮箱注册
  ```bash
  curl -X POST http://localhost:8000/api/auth/register \
    -H "Content-Type: application/json" \
    -d '{
      "email": "test@example.com",
      "password": "password456",
      "username": "testuser2"
    }'
  ```
  - [ ] 返回 HTTP 409
  - [ ] 错误信息包含 "Email already exists"

- [ ] 缺少必填字段
  ```bash
  curl -X POST http://localhost:8000/api/auth/register \
    -H "Content-Type: application/json" \
    -d '{
      "email": "test2@example.com"
    }'
  ```
  - [ ] 返回 HTTP 400
  - [ ] 错误信息提示缺少必填字段

- [ ] 无效邮箱格式
  ```bash
  curl -X POST http://localhost:8000/api/auth/register \
    -H "Content-Type: application/json" \
    -d '{
      "email": "invalid-email",
      "password": "password123",
      "username": "testuser"
    }'
  ```
  - [ ] 返回适当的错误响应

### 登录接口测试
**端点**: `POST /api/auth/login`

- [ ] 正常登录
  ```bash
  curl -X POST http://localhost:8000/api/auth/login \
    -H "Content-Type: application/json" \
    -d '{
      "email": "test@example.com",
      "password": "password123"
    }'
  ```
  - [ ] 返回 HTTP 200
  - [ ] 响应包含 `success: true`
  - [ ] 响应包含 `token` 字段（JWT）
  - [ ] 响应包含 `user` 对象

- [ ] 错误密码
  ```bash
  curl -X POST http://localhost:8000/api/auth/login \
    -H "Content-Type: application/json" \
    -d '{
      "email": "test@example.com",
      "password": "wrongpassword"
    }'
  ```
  - [ ] 返回 HTTP 401
  - [ ] 错误信息为 "Authentication failed"

- [ ] 用户不存在
  ```bash
  curl -X POST http://localhost:8000/api/auth/login \
    -H "Content-Type: application/json" \
    -d '{
      "email": "nonexistent@example.com",
      "password": "password123"
    }'
  ```
  - [ ] 返回 HTTP 401

- [ ] 缺少必填字段
  ```bash
  curl -X POST http://localhost:8000/api/auth/login \
    -H "Content-Type: application/json" \
    -d '{
      "email": "test@example.com"
    }'
  ```
  - [ ] 返回 HTTP 400

### 获取当前用户信息接口测试
**端点**: `GET /api/auth/me`

- [ ] 有效 Token
  ```bash
  curl -X GET http://localhost:8000/api/auth/me \
    -H "Authorization: Bearer <valid_token>"
  ```
  - [ ] 返回 HTTP 200
  - [ ] 响应包含 `success: true`
  - [ ] 响应包含 `user` 对象

- [ ] 无效 Token
  ```bash
  curl -X GET http://localhost:8000/api/auth/me \
    -H "Authorization: Bearer invalid_token"
  ```
  - [ ] 返回 HTTP 401

- [ ] 过期 Token
  ```bash
  curl -X GET http://localhost:8000/api/auth/me \
    -H "Authorization: Bearer <expired_token>"
  ```
  - [ ] 返回 HTTP 401

- [ ] 无 Token
  ```bash
  curl -X GET http://localhost:8000/api/auth/me
  ```
  - [ ] 返回 HTTP 401

---

## 3. Thread 关联测试

### 创建用户-Thread 映射
**测试函数**: `create_user_thread(user_id, thread_id)`

- [ ] 创建新映射（第一次聊天）
  - [ ] 返回 `success: true`
  - [ ] 数据库 `user_threads` 表中新增记录
  - [ ] `thread_id` 与传入参数一致
  - [ ] `user_id` 与传入参数一致

- [ ] 重复创建（幂等性测试）
  - [ ] 返回 `success: false`
  - [ ] 错误信息为 "Thread already exists for this user"
  - [ ] 数据库中只有一条记录

### 查询用户的 Thread
**测试函数**: `get_thread_by_user(user_id)`

- [ ] 查询存在的用户
  - [ ] 返回正确的 thread 记录
  - [ ] 包含 id, user_id, thread_id, created_at, updated_at

- [ ] 查询不存在的用户
  - [ ] 返回 `None`

### 查询 Thread 对应的用户
**测试函数**: `get_user_by_thread(thread_id)`

- [ ] 查询存在的 thread
  - [ ] 返回正确的用户-thread 记录

- [ ] 查询不存在的 thread
  - [ ] 返回 `None`

### 获取或创建 Thread
**测试函数**: `get_or_create_user_thread(user_id, thread_id)`

- [ ] 第一次调用（不存在）
  - [ ] 返回 `success: true`
  - [ ] 返回 `created: true`
  - [ ] 数据库中创建新记录

- [ ] 第二次调用（已存在）
  - [ ] 返回 `success: true`
  - [ ] 返回 `created: false`
  - [ ] 数据库中无新记录

---

## 4. 聊天接口测试

### 匿名用户聊天
**端点**: `POST /api/chat`

```bash
curl -X POST http://localhost:8000/api/chat \
  -H "Content-Type: application/json" \
  -d '{
    "message": "你好",
    "session_id": "test_session_123"
  }'
```

- [ ] 返回 HTTP 200
- [ ] 返回正常的聊天响应
- [ ] 不创建 `user_threads` 映射
- [ ] 仍然可以使用 LangGraph Thread

### 登录用户聊天
**端点**: `POST /api/chat`

```bash
curl -X POST http://localhost:8000/api/chat \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer <valid_token>" \
  -d '{
    "message": "你好",
    "session_id": "user_session_456"
  }'
```

- [ ] 返回 HTTP 200
- [ ] 返回正常的聊天响应
- [ ] 创建 `user_threads` 映射（首次）
- [ ] 映射的 `user_id` 正确
- [ ] 映射的 `thread_id` 正确

### 登录用户再次聊天（复用 Thread）
```bash
curl -X POST http://localhost:8000/api/chat \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer <valid_token>" \
  -d '{
    "message": "继续",
    "session_id": "user_session_456"
  }'
```

- [ ] 返回 HTTP 200
- [ ] 返回正常的聊天响应
- [ ] 不创建新的 `user_threads` 映射
- [ ] 复用同一个 `thread_id`
- [ ] 聊天上下文保持（历史消息可访问）

### 流式聊天接口测试
**端点**: `POST /api/chat/stream`

- [ ] 匿名用户流式聊天（无 Authorization header）
  ```bash
  curl -X POST http://localhost:8000/api/chat/stream \
    -H "Content-Type: application/json" \
    -d '{
      "message": "你好",
      "session_id": "stream_session_789"
    }'
  ```
  - [ ] 返回 HTTP 200
  - [ ] 返回流式数据（SSE 格式）

- [ ] 登录用户流式聊天
  ```bash
  curl -X POST http://localhost:8000/api/chat/stream \
    -H "Content-Type: application/json" \
    -H "Authorization: Bearer <valid_token>" \
    -d '{
      "message": "你好",
      "session_id": "user_stream_session_012"
    }'
  ```
  - [ ] 返回 HTTP 200
  - [ ] 返回流式数据
  - [ ] 创建 `user_threads` 映射（首次）

---

## 5. 前端功能测试

### 登录/注册页面
**页面**: `http://localhost:8000/auth.html`

- [ ] 注册功能
  - [ ] 填写用户名、邮箱、密码
  - [ ] 点击注册按钮
  - [ ] 注册成功后跳转到 `/index.html`
  - [ ] localStorage 中保存了 `token`
  - [ ] localStorage 中保存了 `user` 信息

- [ ] 登录功能
  - [ ] 填写邮箱、密码
  - [ ] 点击登录按钮
  - [ ] 登录成功后跳转到 `/index.html`
  - [ ] localStorage 中保存了 `token`
  - [ ] localStorage 中保存了 `user` 信息

- [ ] 错误处理
  - [ ] 注册时使用重复邮箱，显示错误提示
  - [ ] 登录时使用错误密码，显示错误提示
  - [ ] 表单验证（空字段）显示错误提示

### 主页面
**页面**: `http://localhost:8000/index.html`

- [ ] 未登录访问
  - [ ] 自动重定向到 `/auth.html`

- [ ] 已登录访问
  - [ ] 正常显示主页面
  - [ ] Header 显示用户名
  - [ ] 显示"退出"按钮

- [ ] 聊天功能（匿名用户）
  - [ ] 可以发送消息
  - [ ] 收到 AI 回复
  - [ ] 不创建 `user_threads` 记录

- [ ] 聊天功能（登录用户）
  - [ ] 可以发送消息
  - [ ] 收到 AI 回复
  - [ ] 创建 `user_threads` 记录（首次）
  - [ ] 再次聊天时复用同一个 thread
  - [ ] 聊天上下文保持

- [ ] 退出登录
  - [ ] 点击"退出"按钮
  - [ ] 显示确认对话框
  - [ ] 确认后清除 localStorage
  - [ ] 跳转到 `/auth.html`

### API 请求 Header 验证
- [ ] `/api/chat` 请求包含 `Authorization: Bearer <token>` header
- [ ] `/api/chat/stream` 请求包含 `Authorization: Bearer <token>` header
- [ ] `/api/upload-screenshot` 请求包含 `Authorization: Bearer <token>` header
- [ ] `/api/complete_guide` 请求包含 `Authorization: Bearer <token>` header

---

## 6. 安全性测试

### RLS 策略验证
```sql
-- 使用测试用户 ID 尝试访问其他用户的 thread
SELECT * FROM user_threads WHERE user_id = 'other_user_id';
```
- [ ] 匿名用户无法访问 `user_threads` 表
- [ ] 用户只能访问自己的 `user_threads` 记录

### JWT Token 安全性
- [ ] Token 包含正确的 payload（user_id, email, username, exp, iat）
- [ ] Token 使用 HS256 算法签名
- [ ] Token 过期后无法使用
- [ ] 篡改的 Token 无法使用

### 密码安全
- [ ] 密码使用 bcrypt 哈希存储
- [ ] 数据库中不存储明文密码
- [ ] 相同密码的哈希值不同（bcrypt salt）

### SQL 注入防护
- [ ] 注册接口对特殊字符进行防护
- [ ] 登录接口对特殊字符进行防护

---

## 7. 性能测试

### 并发测试
- [ ] 多个用户同时注册
  - [ ] 所有请求都成功
  - [ ] 无数据竞争

- [ ] 多个用户同时登录
  - [ ] 所有请求都成功
  - [ ] Token 正确生成

- [ ] 多个用户同时聊天
  - [ ] 所有请求都成功
  - [ ] Thread 正确创建和关联

### 数据库性能
- [ ] 查询用户 Thread 的响应时间 < 100ms
- [ ] 创建用户-Thread 映射的响应时间 < 100ms
- [ ] 索引查询效率正常

---

## 8. 回归测试

### 现有功能不受影响
- [ ] 匿名用户聊天功能正常
- [ ] 聊天上下文管理正常
- [ ] 截图上传功能正常
- [ ] 任务指南功能正常
- [ ] 调试功能正常

### 向后兼容性
- [ ] 未登录用户可正常使用所有功能
- [ ] 已有的匿名会话不会被破坏
- [ ] API 响应格式保持不变

---

## 9. 部署测试

### 环境变量
- [ ] `.env` 文件包含 `JWT_SECRET`
- [ ] `.env` 文件包含 `SUPABASE_URL`
- [ ] `.env` 文件包含 `SUPABASE_SERVICE_ROLE_KEY`

### 服务启动
- [ ] 后端服务正常启动
- [ ] 无导入错误
- [ ] 无运行时错误

### 数据库连接
- [ ] Supabase 连接正常
- [ ] 所有表可访问
- [ ] 所有函数可执行

---

## 测试结果汇总

### 通过的测试项
- [ ] 数据库表创建成功
- [ ] 索引和触发器工作正常
- [ ] RLS 策略生效
- [ ] 注册接口正常工作
- [ ] 登录接口正常工作
- [ ] 获取用户信息接口正常工作
- [ ] 用户-Thread 映射正常创建
- [ ] 聊天接口支持可选认证
- [ ] 登录用户可持久化 Thread
- [ ] 匿名用户仍可正常使用
- [ ] 前端登录/注册功能正常
- [ ] API 请求正确携带 Token
- [ ] 退出登录功能正常

### 发现的问题
记录测试过程中发现的问题：
1. 
2. 
3. 

### 待修复问题
1. 
2. 
3. 

### 备注
- 测试日期：2026-01-17
- 测试人员：__________
- 测试环境：__________
