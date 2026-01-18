-- 修复 user_threads 表的 RLS 策略和权限
-- 问题：SERVICE_ROLE_KEY 可能无法正常访问 user_threads 表

-- 1. 添加 SERVICE_ROLE 权限（允许服务端完全访问）
ALTER TABLE public.user_threads OWNER TO postgres;
GRANT ALL ON public.user_threads TO postgres;
GRANT ALL ON public.user_threads TO service_role;

-- 2. 删除有问题的 RLS 策略
DROP POLICY IF EXISTS "Anonymous users cannot access user_threads" ON public.user_threads;
DROP POLICY IF EXISTS "Authenticated users can access own threads" ON public.user_threads;

-- 3. 创建更灵活的 RLS 策略
-- 允许 SERVICE_ROLE 完全访问
CREATE POLICY "Service role has full access" ON public.user_threads
    FOR ALL USING (auth.role() = 'service_role')
    WITH CHECK (auth.role() = 'service_role');

-- 允许认证用户访问自己的 thread
CREATE POLICY "Authenticated users can access own threads" ON public.user_threads
    FOR ALL USING (auth.role() = 'authenticated' AND auth.uid() = user_id)
    WITH CHECK (auth.role() = 'authenticated' AND auth.uid() = user_id);

-- 4. 禁用匿名用户的访问（默认拒绝）
-- RLS 策略是 AND 关系，所以如果没有匹配的策略，默认拒绝

-- 5. 验证权限
SELECT 
    table_name, 
    grantee, 
    privilege_type 
FROM information_schema.role_table_grants 
WHERE table_schema = 'public' 
  AND table_name = 'user_threads'
ORDER BY grantee, privilege_type;
