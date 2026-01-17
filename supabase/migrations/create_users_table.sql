-- 创建 users 表
CREATE TABLE IF NOT EXISTS users (
    id UUID DEFAULT gen_random_uuid() PRIMARY KEY,
    email VARCHAR(255) UNIQUE NOT NULL,
    password_hash VARCHAR(255) NOT NULL,
    username VARCHAR(100) NOT NULL,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- 创建索引
CREATE INDEX IF NOT EXISTS idx_users_email ON users(email);
CREATE INDEX IF NOT EXISTS idx_users_username ON users(username);

-- 启用 Row Level Security
ALTER TABLE users ENABLE ROW LEVEL SECURITY;

-- 创建策略：允许注册（插入新用户）
CREATE POLICY "Allow user registration" ON users
    FOR INSERT
    WITH CHECK (true);

-- 创建策略：允许用户查看自己的数据
CREATE POLICY "Users can view own data" ON users
    FOR SELECT
    USING (auth.uid()::text = id::text);

-- 创建策略：允许用户更新自己的数据
CREATE POLICY "Users can update own data" ON users
    FOR UPDATE
    USING (auth.uid()::text = id::text);

-- 创建策略：允许用户删除自己的数据
CREATE POLICY "Users can delete own data" ON users
    FOR DELETE
    USING (auth.uid()::text = id::text);

-- 创建更新时间触发器
CREATE OR REPLACE FUNCTION update_updated_at_column()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$ language 'plpgsql';

CREATE TRIGGER update_users_updated_at BEFORE UPDATE ON users
    FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

-- 授予 anon 角色读取权限（用于注册前检查邮箱是否存在）
GRANT SELECT ON users TO anon;
GRANT INSERT ON users TO anon;

-- 授予 authenticated 角色所有权限
GRANT ALL ON users TO authenticated;
