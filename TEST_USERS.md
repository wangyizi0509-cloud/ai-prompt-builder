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
| test11@example.com   | password123   | 测试用户11   | 380f24d2-fada-429f-a239-16f35ff20763   | 2026-01-27   |
| test12@example.com   | password123   | 测试用户12   | 2af4c866-8b60-43bd-b57e-bc1e8939b252   | 2026-01-27   |
| test13@example.com   | password123   | 测试用户13   | da384d2d-3083-4a7b-9457-ba6a4794b3e6   | 2026-01-27   |
| test14@example.com   | password123   | 测试用户14   | 9ada670f-20a7-4d00-9ff5-84a819d6b356   | 2026-01-28   |
| test15@example.com   | password123   | 测试用户15   | d1fd2e61-e3c7-42e6-b82d-0ad5328f3c59   | 2026-01-28   |
| test16@example.com   | password123   | 测试用户16   | ff35e531-e5f0-404c-a305-5a15e4fdbb9e   | 2026-01-28   |
| test17@example.com   | password123   | 测试用户17   | a110b940-f696-4450-b301-8ba7b5a6214f   | 2026-01-28   |
| test18@example.com   | password123   | 测试用户18   | 80006eaa-7185-4af5-87c0-c71d9b402329   | 2026-01-28   |
| test19@example.com   | password123   | 测试用户19   | 60c1ab32-d27f-4035-a642-2675809877c0   | 2026-01-28   |
| test20@example.com   | password123   | 测试用户20   | dc173800-ab0c-44a4-8e26-fefc8ab1791f   | 2026-01-28   |
| test21@example.com   | password123   | 测试用户21   | ea0c40a8-07ee-4dc4-8f5c-3f715a7e39b8   | 2026-01-28   |
| test22@example.com   | password123   | 测试用户22   | 4aa8a321-1720-4b5c-957d-5472d891609d   | 2026-01-28   |
| test23@example.com   | password123   | 测试用户23   | 0e7668a2-6eef-4157-b742-877ff3afbdc7   | 2026-01-28   |
| test24@example.com   | password123   | 测试用户24   | 082e9b2e-bd08-4543-8ff3-a000e418270e   | 2026-01-28   |
| test25@example.com   | password123   | 测试用户25   | 8625f56e-db5f-46f3-9d93-37f35e3bf679   | 2026-01-28   |
| test26@example.com   | password123   | 测试用户26   | fc32ac8c-5c3e-4065-b89f-ad81e243cada   | 2026-01-28   |
| test27@example.com   | password123   | 测试用户27   | d7c4ab1b-c94e-4fc8-97a6-023945ccc8b2   | 2026-01-28   |
| test28@example.com   | password123   | 测试用户28   | 123901ed-0fe0-4455-908f-edc5e5ba8b70   | 2026-01-28   |
| test29@example.com   | password123   | 测试用户29   | b673e223-9b7a-4bc8-928f-bdef7248f530   | 2026-01-28   |
| test30@example.com   | password123   | 测试用户30   | 28a63202-592e-4639-8571-0132f9552dad   | 2026-01-28   |

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

1. 所有密码都存储为 bcrypt 哈希值，明文密码仅供测试使用
2. JWT Token 有效期为 7 天
3. 测试完成后请勿在生产环境中使用这些账号
4. 数据库中的用户表已启用 RLS (Row Level Security)
