"""
修复 user_threads 表的 RLS 权限问题
"""

import os
import sys
from dotenv import load_dotenv
import psycopg2
from psycopg2 import sql

load_dotenv()

def get_db_connection():
    """
    获取数据库连接
    从 SUPABASE_URL 解析连接信息
    """
    supabase_url = os.getenv("SUPABASE_URL")
    if not supabase_url:
        raise ValueError("SUPABASE_URL not found in .env")
    
    # 解析 URL: postgresql://postgres:[password]@[host]:[port]/[database]
    # Supabase URL 格式: https://[project-id].supabase.co
    # 需要转换为 postgresql:// 格式
    
    # Supabase 连接信息
    db_host = f"db.{supabase_url.replace('https://', '')}"
    db_port = "5432"
    db_name = "postgres"
    db_user = "postgres"
    
    # 从 SERVICE_ROLE_KEY 获取密码（格式: eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...）
    db_password = os.getenv("SUPABASE_SERVICE_ROLE_KEY")
    
    conn = psycopg2.connect(
        host=db_host,
        port=db_port,
        database=db_name,
        user=db_user,
        password=db_password
    )
    return conn


def fix_permissions():
    """
    修复 user_threads 表的权限问题
    """
    print("开始修复 user_threads 表权限...")
    
    conn = None
    try:
        conn = get_db_connection()
        conn.autocommit = True
        cursor = conn.cursor()
        
        # 1. 授予 SERVICE_ROLE 完全访问权限
        print("\n1. 授予 SERVICE_ROLE 完全访问权限...")
        cursor.execute("""
            GRANT ALL ON public.user_threads TO postgres;
        """)
        print("   ✓ 已授予 postgres 完全访问权限")
        
        # 2. 删除有问题的 RLS 策略
        print("\n2. 删除有问题的 RLS 策略...")
        cursor.execute("""
            DROP POLICY IF EXISTS "Anonymous users cannot access user_threads" ON public.user_threads;
        """)
        print("   ✓ 已删除 'Anonymous users cannot access user_threads' 策略")
        
        # 3. 创建新的 RLS 策略
        print("\n3. 创建新的 RLS 策略...")
        
        # 允许 SERVICE_ROLE 完全访问
        cursor.execute("""
            CREATE POLICY "Service role has full access" ON public.user_threads
            FOR ALL USING (auth.role() = 'service_role')
            WITH CHECK (auth.role() = 'service_role');
        """)
        print("   ✓ 已创建 'Service role has full access' 策略")
        
        # 允许认证用户访问自己的 thread
        cursor.execute("""
            CREATE POLICY "Authenticated users can access own threads" ON public.user_threads
            FOR ALL USING (auth.role() = 'authenticated' AND auth.uid() = user_id)
            WITH CHECK (auth.role() = 'authenticated' AND auth.uid() = user_id);
        """)
        print("   ✓ 已创建 'Authenticated users can access own threads' 策略")
        
        # 4. 验证权限
        print("\n4. 验证权限...")
        cursor.execute("""
            SELECT 
                table_name, 
                grantee, 
                privilege_type 
            FROM information_schema.role_table_grants 
            WHERE table_schema = 'public' 
              AND table_name = 'user_threads'
            ORDER BY grantee, privilege_type;
        """)
        
        grants = cursor.fetchall()
        print("\n当前权限:")
        for grant in grants:
            print(f"   - {grant[0]}: {grant[1]} -> {grant[2]}")
        
        # 5. 查询现有记录
        print("\n5. 查询现有记录...")
        cursor.execute("SELECT COUNT(*) FROM public.user_threads;")
        count = cursor.fetchone()[0]
        print(f"   user_threads 表中有 {count} 条记录")
        
        if count > 0:
            cursor.execute("""
                SELECT user_id, thread_id, created_at 
                FROM public.user_threads 
                ORDER BY created_at DESC 
                LIMIT 5;
            """)
            records = cursor.fetchall()
            print("\n最近的 5 条记录:")
            for record in records:
                print(f"   - User ID: {record[0]}, Thread ID: {record[1]}, Created: {record[2]}")
        
        print("\n" + "="*60)
        print("权限修复完成！")
        print("="*60)
        
    except Exception as e:
        print(f"\n✗ 发生错误: {str(e)}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
    finally:
        if conn:
            conn.close()


if __name__ == '__main__':
    print("user_threads 表权限修复工具")
    print("="*60)
    
    try:
        fix_permissions()
    except KeyboardInterrupt:
        print("\n\n操作已取消")
        sys.exit(0)
