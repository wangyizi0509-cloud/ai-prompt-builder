import requests
import uuid
import sys

BASE_URL = "http://127.0.0.1:8000"

def test_auth_flow():
    # 1. 准备测试数据
    username = f"test_user_{uuid.uuid4().hex[:8]}"
    email = f"{username}@example.com"
    password = "test_password_123"
    
    print(f"Testing with user: {username} ({email})")
    
    # 2. 注册
    print("\n[1] Testing Register...")
    register_payload = {
        "email": email,
        "password": password,
        "username": username
    }
    try:
        resp = requests.post(f"{BASE_URL}/api/auth/register", json=register_payload)
        print(f"Status: {resp.status_code}")
        print(f"Response: {resp.text}")
        
        if resp.status_code != 200:
            print("Register failed!")
            return
            
        reg_data = resp.json()
        if not reg_data.get("success"):
            print("Register success flag is False!")
            return
            
        token = reg_data.get("token")
        if not token:
            print("No token in register response!")
            return
            
        print("Register successful!")
        
    except Exception as e:
        print(f"Register exception: {e}")
        return

    # 3. 登录 (验证登录接口)
    print("\n[2] Testing Login...")
    login_payload = {
        "email": email,
        "password": password
    }
    try:
        resp = requests.post(f"{BASE_URL}/api/auth/login", json=login_payload)
        print(f"Status: {resp.status_code}")
        print(f"Response: {resp.text}")
        
        if resp.status_code != 200:
            print("Login failed!")
            return
            
        login_data = resp.json()
        if not login_data.get("success"):
            print("Login success flag is False!")
            return
            
        token = login_data.get("token")
        if not token:
            print("No token in login response!")
            return
            
        print("Login successful! Token obtained.")
        
    except Exception as e:
        print(f"Login exception: {e}")
        return

    # 4. 获取用户信息 (验证受保护接口)
    print("\n[3] Testing /api/auth/me...")
    headers = {
        "Authorization": f"Bearer {token}"
    }
    try:
        resp = requests.get(f"{BASE_URL}/api/auth/me", headers=headers)
        print(f"Status: {resp.status_code}")
        print(f"Response: {resp.text}")
        
        if resp.status_code != 200:
            print("Get Me failed!")
            return
            
        me_data = resp.json()
        user_info = me_data.get("user", {})
        
        if user_info.get("email") != email:
            print(f"Email mismatch! Expected {email}, got {user_info.get('email')}")
            return
            
        print("Get Me successful! User info matches.")
        
    except Exception as e:
        print(f"Get Me exception: {e}")
        return

    print("\n=== All Tests Passed! ===")

if __name__ == "__main__":
    test_auth_flow()
