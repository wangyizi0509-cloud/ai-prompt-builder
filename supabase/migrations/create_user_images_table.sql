-- 创建用户图片表，用于记录上传到 Storage 的图片元数据
CREATE TABLE IF NOT EXISTS user_images (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    user_id TEXT NOT NULL, -- 可以是 UUID 字符串或 "anonymous"
    storage_path TEXT NOT NULL, -- 在 Storage 中的路径
    public_url TEXT NOT NULL, -- 公开访问 URL
    original_filename TEXT, -- 原始文件名
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

-- 创建索引以加速查询
CREATE INDEX IF NOT EXISTS idx_user_images_user_id ON user_images(user_id);
