import os
import sys
from pathlib import Path

# 添加项目根目录到路径
current_dir = Path(__file__).parent.parent
sys.path.insert(0, str(current_dir))

from supabase_service.client import supabase, is_supabase_configured

def init_supabase_storage(bucket_name: str = "images"):
    """
    初始化 Supabase Storage Bucket
    """
    if not is_supabase_configured():
        print("❌ 错误: Supabase 未配置，请检查 .env 文件中的 SUPABASE_URL 和 SUPABASE_SERVICE_ROLE_KEY")
        return

    try:
        # 1. 检查 Bucket 是否已存在
        buckets = supabase.storage.list_buckets()
        exists = any(b.name == bucket_name for b in buckets)

        if exists:
            # 2. 如果已存在，更新为私有
            supabase.storage.update_bucket(bucket_name, options={"public": False})
            print(f"ℹ️  Bucket '{bucket_name}' 已更新为私有 (Private)。")
        else:
            # 3. 创建私有 Bucket
            supabase.storage.create_bucket(bucket_name, options={"public": False})
            print(f"✅ 成功创建私有 Bucket: '{bucket_name}'")

        print(f"\n🚀 Supabase Storage 初始化完成！")
        print(f"🔗 你可以在 Supabase 控制台查看: {os.getenv('SUPABASE_URL')}/storage/buckets/{bucket_name}")

    except Exception as e:
        print(f"❌ 初始化失败: {str(e)}")

if __name__ == "__main__":
    init_supabase_storage()
