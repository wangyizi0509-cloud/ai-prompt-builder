import os
from datetime import datetime, timedelta
from typing import Optional, Dict, Any
from fastapi import HTTPException, Depends, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from dotenv import load_dotenv

load_dotenv()

JWT_SECRET = os.getenv("JWT_SECRET")

if JWT_SECRET and JWT_SECRET == "your-secret-key-change-this-in-production":
    print("Warning: JWT_SECRET is using default value. Please change it in production.")

security = HTTPBearer()


def is_jwt_configured() -> bool:
    """检查 JWT 是否已配置"""
    return JWT_SECRET is not None and JWT_SECRET != ""


def create_jwt_token(user_id: str, email: str, username: str, expires_days: int = 7) -> str:
    if not is_jwt_configured():
        raise ValueError("JWT_SECRET not configured")
    import jwt
    
    expire = datetime.utcnow() + timedelta(days=expires_days)
    payload = {
        'user_id': user_id,
        'email': email,
        'username': username,
        'exp': expire,
        'iat': datetime.utcnow()
    }
    return jwt.encode(payload, JWT_SECRET, algorithm='HS256')


def verify_jwt_token(token: str) -> Dict[str, Any]:
    if not is_jwt_configured():
        return {
            'valid': False,
            'error': 'JWT not configured'
        }
    import jwt
    
    try:
        payload = jwt.decode(token, JWT_SECRET, algorithms=['HS256'])
        return {
            'valid': True,
            'user_id': payload.get('user_id'),
            'email': payload.get('email'),
            'username': payload.get('username')
        }
    except jwt.ExpiredSignatureError:
        return {
            'valid': False,
            'error': 'Token has expired'
        }
    except jwt.InvalidTokenError:
        return {
            'valid': False,
            'error': 'Invalid token'
        }


async def get_current_user(credentials: HTTPAuthorizationCredentials = Depends(security)) -> Dict[str, Any]:
    if not is_jwt_configured():
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail='Authentication service not configured'
        )
    
    token = credentials.credentials
    result = verify_jwt_token(token)
    
    if not result['valid']:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=result.get('error', 'Invalid token'),
            headers={"WWW-Authenticate": "Bearer"},
        )
    
    return {
        'user_id': result['user_id'],
        'email': result['email'],
        'username': result['username']
    }


async def get_optional_user(credentials: Optional[HTTPAuthorizationCredentials] = Depends(HTTPBearer(auto_error=False))) -> Optional[Dict[str, Any]]:
    if not credentials:
        return None
    
    if not is_jwt_configured():
        return None
    
    token = credentials.credentials
    result = verify_jwt_token(token)
    
    if not result['valid']:
        return None
    
    return {
        'user_id': result['user_id'],
        'email': result['email'],
        'username': result['username']
    }
