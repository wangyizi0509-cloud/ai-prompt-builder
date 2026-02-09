import os
import bcrypt
from typing import Optional, Dict, Any, List
from supabase import create_client, Client
from datetime import datetime
from pathlib import Path
import uuid
from dotenv import load_dotenv

load_dotenv()

SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_SERVICE_ROLE_KEY = os.getenv("SUPABASE_SERVICE_ROLE_KEY")
LOCAL_AUTH_ENABLED = os.getenv("LOCAL_AUTH", "false").lower() == "true"

supabase: Optional[Client] = None

if SUPABASE_URL and SUPABASE_SERVICE_ROLE_KEY and SUPABASE_URL != "your-supabase-url-here":
    try:
        supabase = create_client(SUPABASE_URL, SUPABASE_SERVICE_ROLE_KEY)
    except Exception as e:
        print(f"Warning: Failed to initialize Supabase client: {e}")
        supabase = None


def _get_local_data_dir() -> Path:
    """
    Local auth/dev storage directory.
    Stored under agent_impl/local_data to keep everything in-repo/workspace.
    """
    # .../agent_impl/supabase_service/client.py -> .../agent_impl
    agent_root = Path(__file__).resolve().parents[1]
    d = agent_root / "local_data"
    d.mkdir(parents=True, exist_ok=True)
    return d


def _local_users_path() -> Path:
    return _get_local_data_dir() / "users.json"


def _local_user_threads_path() -> Path:
    return _get_local_data_dir() / "user_threads.json"


def _read_json(path: Path, default):
    try:
        if not path.exists():
            return default
        import json
        return json.loads(path.read_text(encoding="utf-8") or "null") or default
    except Exception:
        return default


def _write_json(path: Path, data) -> None:
    import json
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def _is_local_auth() -> bool:
    # Supabase configured -> always prefer Supabase unless explicitly disabled by env.
    if supabase is not None:
        return False
    return LOCAL_AUTH_ENABLED


def is_supabase_configured() -> bool:
    """检查 Supabase 是否已配置"""
    return supabase is not None


def hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode('utf-8'), bcrypt.gensalt()).decode('utf-8')


def verify_password(password: str, hashed: str) -> bool:
    return bcrypt.checkpw(password.encode('utf-8'), hashed.encode('utf-8'))


async def create_user(email: str, password: str, username: str) -> Dict[str, Any]:
    # Local auth fallback for dev/smoke tests
    if _is_local_auth():
        users_path = _local_users_path()
        users = _read_json(users_path, default=[])
        if any(isinstance(u, dict) and u.get("email") == email for u in users):
            return {"success": False, "error": "Email already exists"}
        user_id = str(uuid.uuid4())
        password_hash = hash_password(password)
        created_at = datetime.now().isoformat()
        users.append(
            {
                "id": user_id,
                "email": email,
                "username": username,
                "password_hash": password_hash,
                "created_at": created_at,
            }
        )
        _write_json(users_path, users)
        return {
            "success": True,
            "user": {"id": user_id, "email": email, "username": username, "created_at": created_at},
        }

    if not is_supabase_configured():
        return {"success": False, "error": "Supabase not configured"}
    
    try:
        password_hash = hash_password(password)
        
        response = supabase.table('users').insert({
            'email': email,
            'password_hash': password_hash,
            'username': username
        }).execute()
        
        user_data = response.data[0] if response.data else None
        if not user_data:
            raise Exception("Failed to create user")
        
        return {
            'success': True,
            'user': {
                'id': user_data.get('id'),
                'email': user_data.get('email'),
                'username': user_data.get('username'),
                'created_at': user_data.get('created_at')
            }
        }
    except Exception as e:
        if "duplicate key" in str(e).lower():
            return {
                'success': False,
                'error': 'Email already exists'
            }
        return {
            'success': False,
            'error': str(e)
        }


async def authenticate_user(email: str, password: str) -> Dict[str, Any]:
    # Local auth fallback for dev/smoke tests
    if _is_local_auth():
        users = _read_json(_local_users_path(), default=[])
        user = next((u for u in users if isinstance(u, dict) and u.get("email") == email), None)
        if not user:
            return {"success": False, "error": "User not found"}
        if not verify_password(password, user.get("password_hash", "")):
            return {"success": False, "error": "Invalid password"}
        return {
            "success": True,
            "user": {
                "id": user.get("id"),
                "email": user.get("email"),
                "username": user.get("username"),
                "created_at": user.get("created_at"),
            },
        }

    if not is_supabase_configured():
        return {"success": False, "error": "Supabase not configured"}
    
    try:
        response = supabase.table('users').select('*').eq('email', email).execute()
        
        if not response.data:
            return {
                'success': False,
                'error': 'User not found'
            }
        
        user = response.data[0]
        
        if not verify_password(password, user['password_hash']):
            return {
                'success': False,
                'error': 'Invalid password'
            }
        
        return {
            'success': True,
            'user': {
                'id': user.get('id'),
                'email': user.get('email'),
                'username': user.get('username'),
                'created_at': user.get('created_at')
            }
        }
    except Exception as e:
        return {
            'success': False,
            'error': str(e)
        }


async def get_user_by_id(user_id: str) -> Optional[Dict[str, Any]]:
    if _is_local_auth():
        users = _read_json(_local_users_path(), default=[])
        for u in users:
            if isinstance(u, dict) and u.get("id") == user_id:
                return {k: u.get(k) for k in ("id", "email", "username", "created_at")}
        return None

    if not is_supabase_configured():
        return None
    
    try:
        response = supabase.table('users').select('id, email, username, created_at').eq('id', user_id).execute()
        
        if response.data:
            return response.data[0]
        return None
    except Exception as e:
        print(f"Error fetching user: {e}")
        return None


async def get_user_by_email(email: str) -> Optional[Dict[str, Any]]:
    if _is_local_auth():
        users = _read_json(_local_users_path(), default=[])
        for u in users:
            if isinstance(u, dict) and u.get("email") == email:
                return {k: u.get(k) for k in ("id", "email", "username", "created_at")}
        return None

    if not is_supabase_configured():
        return None
    
    try:
        response = supabase.table('users').select('id, email, username, created_at').eq('email', email).execute()
        
        if response.data:
            return response.data[0]
        return None
    except Exception as e:
        print(f"Error fetching user by email: {e}")
        return None


async def create_user_thread(user_id: str, thread_id: str) -> Dict[str, Any]:
    if _is_local_auth():
        path = _local_user_threads_path()
        rows = _read_json(path, default=[])
        # one thread per user
        existing = next((r for r in rows if isinstance(r, dict) and r.get("user_id") == user_id), None)
        if existing:
            return {"success": False, "error": "Thread already exists for this user"}
        row = {"id": str(uuid.uuid4()), "user_id": user_id, "thread_id": thread_id, "created_at": datetime.now().isoformat()}
        rows.append(row)
        _write_json(path, rows)
        return {"success": True, "thread": row}

    if not is_supabase_configured():
        return {"success": False, "error": "Supabase not configured"}
    
    try:
        response = supabase.table('user_threads').insert({
            'user_id': user_id,
            'thread_id': thread_id
        }).execute()
        
        thread_data = response.data[0] if response.data else None
        if not thread_data:
            raise Exception("Failed to create user thread")
        
        return {
            'success': True,
            'thread': {
                'id': thread_data.get('id'),
                'user_id': thread_data.get('user_id'),
                'thread_id': thread_data.get('thread_id'),
                'created_at': thread_data.get('created_at')
            }
        }
    except Exception as e:
        if "duplicate key" in str(e).lower():
            return {
                'success': False,
                'error': 'Thread already exists for this user'
            }
        return {
            'success': False,
            'error': str(e)
        }


async def get_thread_by_user(user_id: str) -> Optional[Dict[str, Any]]:
    if _is_local_auth():
        rows = _read_json(_local_user_threads_path(), default=[])
        return next((r for r in rows if isinstance(r, dict) and r.get("user_id") == user_id), None)

    if not is_supabase_configured():
        return None
    
    try:
        response = supabase.table('user_threads').select('*').eq('user_id', user_id).execute()
        
        if response.data:
            return response.data[0]
        return None
    except Exception as e:
        print(f"Error fetching thread: {e}")
        return None


async def get_user_by_thread(thread_id: str) -> Optional[Dict[str, Any]]:
    if _is_local_auth():
        rows = _read_json(_local_user_threads_path(), default=[])
        return next((r for r in rows if isinstance(r, dict) and r.get("thread_id") == thread_id), None)

    if not is_supabase_configured():
        return None
    
    try:
        response = supabase.table('user_threads').select('*').eq('thread_id', thread_id).execute()
        
        if response.data:
            return response.data[0]
        return None
    except Exception as e:
        print(f"Error fetching user by thread: {e}")
        return None


async def get_or_create_user_thread(user_id: str, thread_id: str) -> Dict[str, Any]:
    existing_thread = await get_thread_by_user(user_id)
    
    if existing_thread:
        return {
            'success': True,
            'thread': existing_thread,
            'created': False
        }
    
    return await create_user_thread(user_id, thread_id)


# ============================================================
# 图片存储 (Supabase Storage)
# ============================================================

async def upload_user_image(
    user_id: str, 
    image_data: bytes, 
    filename: str, 
    bucket_name: str = "images"
) -> Dict[str, Any]:
    """
    上传用户图片到 Supabase Storage
    
    Args:
        user_id: 用户 ID
        image_data: 图片二进制数据
        filename: 原始文件名
        bucket_name: 存储桶名称
        
    Returns:
        {
            'success': bool,
            'url': str,  # 公开访问 URL
            'path': str, # 存储路径
            'error': str | None
        }
    """
    if not is_supabase_configured():
        return {
            'success': False,
            'error': 'Supabase not configured'
        }
    
    try:
        # 生成唯一路径: {user_id}/{timestamp}_{uuid}_{filename}
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        unique_id = str(uuid.uuid4())[:8]
        ext = Path(filename).suffix or ".png"
        safe_filename = f"{timestamp}_{unique_id}{ext}"
        storage_path = f"{user_id}/{safe_filename}"
        
        # 1. 上传到 Storage
        # 注意: 如果 bucket 不存在，这里可能会报错，通常需要预先创建 bucket
        supabase.storage.from_(bucket_name).upload(
            path=storage_path,
            file=image_data,
            file_options={"content-type": f"image/{ext.lstrip('.')}"}
        )
        
        # 2. 获取公开 URL
        # 注意: 假设 bucket 是 public 的
        response = supabase.storage.from_(bucket_name).get_public_url(storage_path)
        public_url = response
        
        # 3. 在数据库中记录元数据 (可选)
        try:
            supabase.table('user_images').insert({
                'user_id': user_id,
                'storage_path': storage_path,
                'public_url': public_url,
                'original_filename': filename
            }).execute()
        except Exception as db_err:
            print(f"Warning: Failed to record image metadata in DB: {db_err}")
            # 即使数据库记录失败，只要上传成功也返回成功
            
        return {
            'success': True,
            'url': public_url,
            'path': storage_path
        }
        
    except Exception as e:
        return {
            'success': False,
            'error': str(e)
        }


async def list_user_images_from_supabase(user_id: str, bucket_name: str = "images") -> List[Dict[str, Any]]:
    """
    从 Supabase 获取用户的所有图片信息
    """
    if not is_supabase_configured():
        return []
    
    try:
        response = supabase.table('user_images').select('*').eq('user_id', user_id).execute()
        return response.data or []
    except Exception as e:
        print(f"Error listing user images from Supabase: {e}")
        return []
