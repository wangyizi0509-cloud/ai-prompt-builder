import os
import sys
import uuid

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from tests.helpers.feedback_test_utils import (
    DEFAULT_EMAIL,
    DEFAULT_PASSWORD,
    ensure_thread_id,
    get_base_url,
    login,
)


@pytest.fixture(scope="session")
def base_url() -> str:
    return get_base_url()


@pytest.fixture(scope="session")
def test_credentials() -> dict:
    return {
        "email": os.getenv("TEST_USER_EMAIL", DEFAULT_EMAIL),
        "password": os.getenv("TEST_USER_PASSWORD", DEFAULT_PASSWORD),
    }


@pytest.fixture(scope="session")
def auth_data(base_url: str, test_credentials: dict) -> dict:
    return login(base_url, test_credentials["email"], test_credentials["password"])


@pytest.fixture(scope="session")
def auth_token(auth_data: dict) -> str:
    return auth_data["token"]


@pytest.fixture(scope="session")
def session_id(base_url: str, auth_token: str) -> str:
    return ensure_thread_id(base_url, auth_token)


@pytest.fixture()
def unique_tag() -> str:
    return uuid.uuid4().hex[:8]
