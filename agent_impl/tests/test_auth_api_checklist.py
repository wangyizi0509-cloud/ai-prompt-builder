
import pytest
from fastapi.testclient import TestClient
from unittest.mock import patch, MagicMock
import sys
import os

# Ensure we can import modules from parent directory
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from server import app
from auth_utils import get_current_user

client = TestClient(app)

# Mock data
MOCK_USER = {
    "id": "test-user-id",
    "email": "test@example.com",
    "username": "testuser",
    "created_at": "2024-01-01T00:00:00Z"
}

MOCK_TOKEN = "mock-jwt-token"

@pytest.fixture
def mock_supabase_functions():
    with patch("api.auth.create_user") as mock_create, \
         patch("api.auth.authenticate_user") as mock_auth, \
         patch("api.auth.get_user_by_id") as mock_get_user, \
         patch("api.auth.create_jwt_token") as mock_jwt:
        
        # Setup default successful behaviors
        mock_create.return_value = {"success": True, "user": MOCK_USER}
        mock_auth.return_value = {"success": True, "user": MOCK_USER}
        mock_get_user.return_value = MOCK_USER
        mock_jwt.return_value = MOCK_TOKEN
        
        yield {
            "create": mock_create,
            "auth": mock_auth,
            "get_user": mock_get_user,
            "jwt": mock_jwt
        }

@pytest.fixture
def mock_auth_utils():
    with patch("api.auth.verify_jwt_token") as mock_verify, \
         patch("api.auth.get_current_user") as mock_get_current:
        
        mock_verify.return_value = {"user_id": MOCK_USER["id"], "email": MOCK_USER["email"]}
        mock_get_current.return_value = {"user_id": MOCK_USER["id"], "email": MOCK_USER["email"]}
        
        yield {
            "verify": mock_verify,
            "get_current": mock_get_current
        }

class TestAuthChecklist:
    """
    Covering AUTH_TEST_CHECKLIST.md API scenarios
    """

    # --- Register Scenarios (R01-R04) ---

    def test_r01_normal_register(self, mock_supabase_functions):
        """R01: Normal Registration"""
        payload = {
            "email": "new@example.com",
            "password": "password123",
            "username": "newuser"
        }
        response = client.post("/api/auth/register", json=payload)
        
        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert data["token"] == MOCK_TOKEN
        assert data["user"] == MOCK_USER
        
        mock_supabase_functions["create"].assert_called_once()

    def test_r02_duplicate_email(self, mock_supabase_functions):
        """R02: Duplicate Email Registration"""
        # Mock create_user to return duplicate error
        mock_supabase_functions["create"].return_value = {
            "success": False,
            "error": "Email already exists"
        }
        
        payload = {
            "email": "test@example.com",
            "password": "password123",
            "username": "testuser"
        }
        response = client.post("/api/auth/register", json=payload)
        
        # Expecting 409 Conflict based on implementation logic for 'email' error
        assert response.status_code == 409
        assert "Email already exists" in response.json()["detail"]

    def test_r03_empty_fields(self, mock_supabase_functions):
        """R03: Form Validation - Empty Fields"""
        # Missing username
        payload = {
            "email": "test@example.com",
            "password": "password123"
        }
        response = client.post("/api/auth/register", json=payload)
        assert response.status_code == 422  # FastAPI validation error

        # Empty strings (logic in api/auth.py handles manual check)
        payload = {
            "email": "",
            "password": "pwd",
            "username": "usr"
        }
        response = client.post("/api/auth/register", json=payload)
        assert response.status_code == 400
        assert "All fields are required" in response.json()["detail"]

    # --- Login Scenarios (L01-L03) ---

    def test_l01_normal_login(self, mock_supabase_functions):
        """L01: Normal Login"""
        payload = {
            "email": "test@example.com",
            "password": "password123"
        }
        response = client.post("/api/auth/login", json=payload)
        
        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert data["token"] == MOCK_TOKEN

    def test_l02_wrong_password(self, mock_supabase_functions):
        """L02: Wrong Password"""
        mock_supabase_functions["auth"].return_value = {
            "success": False,
            "error": "Invalid password"
        }
        
        payload = {
            "email": "test@example.com",
            "password": "wrongpassword"
        }
        response = client.post("/api/auth/login", json=payload)
        
        assert response.status_code == 401
        assert "Invalid password" in response.json()["detail"]

    def test_l03_user_not_found(self, mock_supabase_functions):
        """L03: User Not Exists"""
        mock_supabase_functions["auth"].return_value = {
            "success": False,
            "error": "User not found"
        }
        
        payload = {
            "email": "unknown@example.com",
            "password": "password123"
        }
        response = client.post("/api/auth/login", json=payload)
        
        assert response.status_code == 401
        assert "User not found" in response.json()["detail"]

    # --- API Security Scenarios (S01-S02) ---

    def test_s01_no_token_access(self):
        """S01: Access protected route without token"""
        # We need to ensure we are NOT patching get_current_user here to test the real dependency behavior
        # But FastAPI dependency override might be needed if we want to test the auth_utils logic
        # For now, let's rely on FastAPI's default behavior for missing header
        
        # Note: If get_current_user raises HTTPException, we should see it.
        # But since we are mocking imports in fixtures, we need to be careful.
        # This test checks the endpoint without the fixture that mocks get_current_user
        
        response = client.get("/api/auth/me")
        # 403 or 401 depending on how FastAPI handles missing Bearer token
        assert response.status_code in [401, 403]

    def test_s02_invalid_token(self):
        """S02: Access with invalid token"""
        headers = {"Authorization": "Bearer invalid_token"}
        
        # We need to mock verify_jwt_token to return invalid status
        with patch("auth_utils.verify_jwt_token") as mock_verify_utils:
            mock_verify_utils.return_value = {
                "valid": False,
                "error": "Invalid token"
            }
            
            response = client.get("/api/auth/me", headers=headers)
            assert response.status_code == 401
            assert "Invalid token" in response.json()["detail"]

    def test_get_me_success(self, mock_supabase_functions):
        """Get Me: Successful retrieval"""
        # We need to mock the dependency to return a valid user
        # Use the actual function object as key
        app.dependency_overrides[get_current_user] = lambda: {"user_id": MOCK_USER["id"]}
        
        try:
            headers = {"Authorization": f"Bearer {MOCK_TOKEN}"}
            response = client.get("/api/auth/me", headers=headers)
            
            assert response.status_code == 200
            data = response.json()
            assert data["success"] is True
            assert data["user"] == MOCK_USER
        finally:
            app.dependency_overrides = {}

