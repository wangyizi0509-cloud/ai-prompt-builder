import os
from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials

router = APIRouter()
security = HTTPBearer()


class RegisterRequest(BaseModel):
    email: str
    password: str
    username: str


class LoginRequest(BaseModel):
    email: str
    password: str


from utils.logger import get_logger

logger = get_logger("auth")

ALLOW_REGISTRATION = os.getenv("ALLOW_REGISTRATION", "false").lower() == "true"

@router.post("/register")
async def register(request: RegisterRequest):
    """
    用户注册接口
    """
    from auth_utils import create_jwt_token
    from supabase_service.client import create_user
    if not ALLOW_REGISTRATION:
        raise HTTPException(status_code=403, detail="Registration is currently disabled")

    if not request.email or not request.password or not request.username:
        raise HTTPException(status_code=400, detail="All fields are required")
    
    result = await create_user(request.email, request.password, request.username)
    
    if not result['success']:
        if 'email' in result.get('error', '').lower():
            raise HTTPException(status_code=409, detail=result.get('error'))
        raise HTTPException(status_code=400, detail=result.get('error'))
    
    user_data = result['user']
    token = create_jwt_token(user_data['id'], user_data['email'], user_data['username'])
    
    return {
        'success': True,
        'token': token,
        'user': user_data
    }


@router.post("/login")
async def login(request: LoginRequest):
    """
    用户登录接口
    """
    from auth_utils import create_jwt_token
    from supabase_service.client import authenticate_user

    if not request.email or not request.password:
        raise HTTPException(status_code=400, detail="Email and password are required")
    
    result = await authenticate_user(request.email, request.password)
    
    if not result['success']:
        raise HTTPException(status_code=401, detail=result.get('error', 'Authentication failed'))
    
    user_data = result['user']
    token = create_jwt_token(user_data['id'], user_data['email'], user_data['username'])
    
    return {
        'success': True,
        'token': token,
        'user': user_data
    }


async def get_current_user_dep(
    credentials: HTTPAuthorizationCredentials = Depends(security),
):
    from auth_utils import get_current_user
    return await get_current_user(credentials)


@router.get("/me")
async def get_current_user_info(current_user=Depends(get_current_user_dep)):
    """
    获取当前登录用户信息
    """
    from supabase_service.client import get_user_by_id

    user_info = await get_user_by_id(current_user['user_id'])
    
    if not user_info:
        raise HTTPException(status_code=404, detail="User not found")
    
    return {
        'success': True,
        'user': user_info
    }


@router.get("/me/thread")
async def get_user_thread_info(current_user=Depends(get_current_user_dep)):
    """
    获取当前登录用户的 Thread 信息
    """
    logger.debug(f"get_user_thread_info request for user: {current_user['user_id']}")
    from supabase_service.client import get_thread_by_user
    user_thread = await get_thread_by_user(current_user['user_id'])
    
    if not user_thread:
        logger.info(f"No thread bound for user: {current_user['user_id']}")
        return {
            'success': True,
            'thread_id': None
        }
    
    logger.info(f"Found thread {user_thread['thread_id']} for user: {current_user['user_id']}")
    return {
        'success': True,
        'thread_id': user_thread['thread_id']
    }
