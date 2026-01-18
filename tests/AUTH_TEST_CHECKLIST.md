# 认证系统测试清单 (Auth System Test Checklist)

本文档列出了 Crushe AI Agent 认证系统的测试用例。

## 1. 注册流程 (Register)

| ID | 测试场景 | 前置条件 | 操作步骤 | 预期结果 | 状态 |
|---|---|---|---|---|---|
| R01 | **正常注册** | 无 | 1. 打开 `/auth.html`<br>2. 填写有效的用户名、邮箱、密码<br>3. 点击"注册" | 1. 注册成功提示<br>2. 自动跳转到主页 `/`<br>3. 主页显示用户名 | ✅ |
| R02 | **重复邮箱注册** | 已存在邮箱 `test@example.com` | 1. 打开 `/auth.html`<br>2. 使用 `test@example.com` 注册<br>3. 点击"注册" | 1. 显示错误提示 "User already registered" 或类似信息<br>2. 停留在注册页 | ✅ |
| R03 | **表单验证 - 空字段** | 无 | 1. 打开 `/auth.html`<br>2. 留空任意字段<br>3. 点击"注册" | 1. 浏览器或前端提示字段必填<br>2. 不发送 API 请求 | ✅ |
| R04 | **密码过短** | 无 | 1. 打开 `/auth.html`<br>2. 输入过短密码 (如 1 位)<br>3. 点击"注册" | 1. 根据 Supabase 配置可能报错 (默认 6 位)<br>2. 显示相应错误 | ⚪ |

## 2. 登录流程 (Login)

| ID | 测试场景 | 前置条件 | 操作步骤 | 预期结果 | 状态 |
|---|---|---|---|---|---|
| L01 | **正常登录** | 已注册用户 | 1. 打开 `/auth.html` (切换到登录)<br>2. 输入正确邮箱密码<br>3. 点击"登录" | 1. 登录成功提示<br>2. 自动跳转到主页 `/`<br>3. localStorage 中存有 token | ✅ |
| L02 | **密码错误** | 已注册用户 | 1. 打开 `/auth.html`<br>2. 输入错误密码<br>3. 点击"登录" | 1. 显示错误提示 "Invalid login credentials"<br>2. 停留在登录页 | ✅ |
| L03 | **用户不存在** | 无 | 1. 打开 `/auth.html`<br>2. 输入不存在的邮箱<br>3. 点击"登录" | 1. 显示错误提示 "Invalid login credentials"<br>2. 停留在登录页 | ✅ |

## 3. 路由守卫与持久化 (Route Guard & Persistence)

| ID | 测试场景 | 前置条件 | 操作步骤 | 预期结果 | 状态 |
|---|---|---|---|---|---|
| G01 | **未登录访问主页** | 清除 localStorage | 1. 直接访问 `/` 或 `/index.html` | 1. 自动重定向到 `/auth.html` | ✅ |
| G02 | **已登录访问主页** | 已登录 (localStorage 有 token) | 1. 访问 `/` | 1. 正常显示主页<br>2. 顶部显示用户名<br>3. 不跳转到 `/auth.html` | ✅ |
| G03 | **页面刷新保持登录** | 已登录 | 1. 在主页点击刷新按钮 | 1. 保持登录状态<br>2. 用户名依然显示 | ✅ |
| G04 | **Token 过期/无效** | 已登录 | 1. 手动修改 localStorage 中的 token 为无效值<br>2. 刷新页面 | 1. API `/api/auth/me` 返回 401<br>2. 前端捕获错误并清除本地数据<br>3. 自动重定向到 `/auth.html` | ✅ |

## 4. 退出登录 (Logout)

| ID | 测试场景 | 前置条件 | 操作步骤 | 预期结果 | 状态 |
|---|---|---|---|---|---|
| O01 | **正常退出** | 已登录 | 1. 点击顶部"退出"按钮<br>2. 在确认弹窗点击"确认退出" | 1. 清除 localStorage (token, user)<br>2. 跳转到 `/auth.html` | ✅ |
| O02 | **取消退出** | 已登录 | 1. 点击顶部"退出"按钮<br>2. 在确认弹窗点击"取消" | 1. 弹窗关闭<br>2. 保持登录状态 | ✅ |

## 5. API 安全性 (Backend Security)

| ID | 测试场景 | 前置条件 | 操作步骤 | 预期结果 | 状态 |
|---|---|---|---|---|---|
| S01 | **无 Token 访问受保护接口** | 无 | 1. 使用 Postman/curl 访问 `GET /api/auth/me` | 1. 返回 401 Unauthorized 或 403 Forbidden | ✅ |
| S02 | **伪造 Token 访问** | 无 | 1. 使用伪造 token 访问 `GET /api/auth/me` | 1. 返回 401 Unauthorized (Invalid token) | ✅ |

---
*Last Updated: 2026-01-17*
