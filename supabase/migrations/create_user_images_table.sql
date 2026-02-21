-- 创建用户图片表，用于记录上传到 Storage 的图片元数据
CREATE EXTENSION IF NOT EXISTS pgcrypto;

CREATE TABLE IF NOT EXISTS public.user_images (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id TEXT NOT NULL, -- 可以是 UUID 字符串或 "anonymous"
    storage_path TEXT NOT NULL, -- 在 Storage 中的路径
    public_url TEXT NOT NULL, -- 公开访问 URL
    original_filename TEXT, -- 原始文件名
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

-- 创建索引以加速查询
CREATE INDEX IF NOT EXISTS idx_user_images_user_id ON public.user_images(user_id);
