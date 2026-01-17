-- 创建 user_threads 表
CREATE TABLE IF NOT EXISTS user_threads (
    id UUID DEFAULT gen_random_uuid() PRIMARY KEY,
    user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    thread_id VARCHAR(255) NOT NULL UNIQUE,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT timezone('utc'::text, now()),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT timezone('utc'::text, now())
);

-- 创建索引
CREATE INDEX IF NOT EXISTS idx_user_threads_user_id ON user_threads(user_id);
CREATE INDEX IF NOT EXISTS idx_user_threads_thread_id ON user_threads(thread_id);

-- 设置自动更新时间戳触发器
CREATE OR REPLACE FUNCTION update_updated_at_column()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = timezone('utc'::text, now());
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER update_user_threads_updated_at
    BEFORE UPDATE ON user_threads
    FOR EACH ROW
    EXECUTE FUNCTION update_updated_at_column();

-- 配置 RLS (Row Level Security)
ALTER TABLE public.user_threads ENABLE ROW LEVEL SECURITY;

-- 匿名用户禁止访问
CREATE POLICY "Anonymous users cannot access user_threads" ON public.user_threads
    FOR ALL USING (auth.role() = 'anon')
    WITH CHECK (false);

-- 认证用户允许访问
CREATE POLICY "Authenticated users can access own threads" ON public.user_threads
    FOR ALL USING (auth.uid() = user_id);

-- 授予权限
GRANT USAGE ON SCHEMA public TO anon, authenticated;
GRANT ALL ON public.user_threads TO authenticated;
