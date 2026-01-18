# 测试用户账号

本文档记录了用于测试的用户账号信息。

## 用户列表

| 邮箱                 | 密码          | 用户名       | 用户 ID                                | 创建时间     |
|----------------------|---------------|--------------|----------------------------------------|--------------|
| test01@example.com   | password123   | 测试用户01   | fbb05249-f46c-4af5-b819-3e38cc830156   | 2026-01-17   |
| test02@example.com   | password123   | 测试用户02   | 136ecd08-856b-40fd-8e6a-98c12e687415   | 2026-01-17   |
| test03@example.com   | password123   | 测试用户03   | 41e84541-8be4-4511-9060-2bca12fbee0e   | 2026-01-17   |
| test04@example.com   | password123   | 测试用户04   | ecdb1e7c-3e1c-4a48-a0d1-f8fe66c111d5   | 2026-01-17   |
| test05@example.com   | password123   | 测试用户05   | 1a33c9a1-a45b-432f-b1d9-b9502b0379f1   | 2026-01-17   |
| test06@example.com   | password123   | 测试用户06   | 14455e46-fbea-4805-a8a6-3a7cf2351f73   | 2026-01-17   |
| test07@example.com   | password123   | 测试用户07   | 4f646a46-6562-4855-b502-b6f7ef19f02e   | 2026-01-17   |
| test08@example.com   | password123   | 测试用户08   | f196dc78-ce1a-4a0b-814c-fbcd4d968f27   | 2026-01-17   |
| test09@example.com   | password123   | 测试用户09   | 0f8a1b2f-4eb0-4122-94a1-7dd619be9036   | 2026-01-17   |
| test10@example.com   | password123   | 测试用户10   | 31a266b1-b5e6-4989-b365-70bfed8ba971   | 2026-01-17   |

## 使用说明

### 登录页面
访问 `http://localhost:8000/auth.html` 进行登录或注册

### API 测试

#### 注册用户
```bash
curl -X POST http://localhost:8000/api/auth/register \
  -H "Content-Type: application/json" \
  -d '{"email":"newuser@example.com","password":"newpass123","username":"新用户"}'
```

#### 登录用户
```bash
curl -X POST http://localhost:8000/api/auth/login \
  -H "Content-Type: application/json" \
  -d '{"email":"user1@example.com","password":"password123"}'
```

#### 获取当前用户信息
```bash
# 需要先登录获取 token
curl -X GET "http://localhost:8000/api/auth/me?authorization=YOUR_TOKEN"
```

## 注意事项

1. 所有密码都存储为 SHA-256 哈希值，明文密码仅供测试使用
2. JWT Token 有效期为 7 天
3. 测试完成后请勿在生产环境中使用这些账号
4. 数据库中的用户表已启用 RLS (Row Level Security)
