import os
import bcrypt
from typing import Optional, Dict, Any
from supabase import create_client, Client
from dotenv import load_dotenv

load_dotenv()

SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_SERVICE_ROLE_KEY = os.getenv("SUPABASE_SERVICE_ROLE_KEY")

supabase: Optional[Client] = None

if SUPABASE_URL and SUPABASE_SERVICE_ROLE_KEY and SUPABASE_URL != "your-supabase-url-here":
    try:
        supabase = create_client(SUPABASE_URL, SUPABASE_SERVICE_ROLE_KEY)
    except Exception as e:
        print(f"Warning: Failed to initialize Supabase client: {e}")
        supabase = None


def is_supabase_configured() -> bool:
    """检查 Supabase 是否已配置"""
    return supabase is not None


def hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode('utf-8'), bcrypt.gensalt()).decode('utf-8')


def verify_password(password: str, hashed: str) -> bool:
    return bcrypt.checkpw(password.encode('utf-8'), hashed.encode('utf-8'))


async def create_user(email: str, password: str, username: str) -> Dict[str, Any]:
    if not is_supabase_configured():
        return {
            'success': False,
            'error': 'Supabase not configured'
        }
    
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
    if not is_supabase_configured():
        return {
            'success': False,
            'error': 'Supabase not configured'
        }
    
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


async def create_user_thread(user_id: str, thread_id: str) -> Dict[str, Any]:
    if not is_supabase_configured():
        return {
            'success': False,
            'error': 'Supabase not configured'
        }
    
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
