"""
E2E 脚本整合测试模块

将 scripts/ 下散落的 e2e Python 脚本统一纳入 pytest 管理。
所有测试标记为 e2e + api_test，需要真实服务运行。

运行方式：
    cd agent_impl
    pytest tests/test_e2e_scripts.py -m e2e -v --timeout=300

环境变量：
    E2E_BASE_URL       - 服务地址（默认 http://localhost:8000）
    TEST_USER_EMAIL    - 测试账号（默认 test01@example.com）
    TEST_USER_PASSWORD - 密码（默认 password123）
"""

import os
import sys
import subprocess
import pytest
from pathlib import Path

SCRIPTS_DIR = Path(__file__).resolve().parents[2] / "scripts"
BASE_URL = os.getenv("E2E_BASE_URL", "http://localhost:8000")
EMAIL = os.getenv("TEST_USER_EMAIL", "test01@example.com")
PASSWORD = os.getenv("TEST_USER_PASSWORD", "password123")
ARTIFACTS_DIR = Path(__file__).resolve().parents[2] / "artifacts" / "e2e"


def _run_script(script_name: str, extra_args: list[str] | None = None, timeout: int = 300) -> subprocess.CompletedProcess:
    """运行 scripts/ 下的 e2e 脚本，返回执行结果。"""
    script_path = SCRIPTS_DIR / script_name
    if not script_path.exists():
        pytest.skip(f"Script not found: {script_path}")

    cmd = [sys.executable, str(script_path)]
    if extra_args:
        cmd.extend(extra_args)

    result = subprocess.run(
        cmd,
        capture_output=True,
        text=True,
        timeout=timeout,
        cwd=str(SCRIPTS_DIR.parent),
    )
    return result


@pytest.mark.e2e
@pytest.mark.api_test
class TestE2EUISmoke:
    """UI 冒烟测试：登录 → 发消息 → 验证回复出现"""

    def test_ui_smoke_probe(self):
        ARTIFACTS_DIR.mkdir(parents=True, exist_ok=True)
        result = _run_script(
            "e2e_ui_smoke_probe.py",
            [
                "--base-url", BASE_URL,
                "--email", EMAIL,
                "--password", PASSWORD,
                "--output-dir", str(ARTIFACTS_DIR / "smoke"),
            ],
        )
        print(result.stdout)
        if result.returncode != 0:
            print(result.stderr)
        assert result.returncode == 0, f"UI smoke probe failed:\n{result.stderr}"


@pytest.mark.e2e
@pytest.mark.api_test
class TestE2EFeedbackUI:
    """行动反馈弹窗 UI 测试：需要真实 LLM"""

    def test_feedback_ui_flow(self):
        result = _run_script("e2e_feedback_ui.py", timeout=300)
        print(result.stdout)
        if result.returncode != 0:
            print(result.stderr)
        assert result.returncode == 0, f"Feedback UI test failed:\n{result.stderr}"


@pytest.mark.e2e
@pytest.mark.api_test
class TestE2EMobileRecovery:
    """移动端断网恢复测试"""

    def test_mobile_background_recovery(self):
        result = _run_script(
            "e2e_mobile_background_recovery.py",
            [
                "--base-url", BASE_URL,
                "--email", EMAIL,
                "--password", PASSWORD,
            ],
            timeout=300,
        )
        print(result.stdout)
        if result.returncode != 0:
            print(result.stderr)
        assert result.returncode == 0, f"Mobile recovery test failed:\n{result.stderr}"


@pytest.mark.e2e
@pytest.mark.api_test
class TestE2EChatStability:
    """前端聊天稳定性回归（使用 mock API，不需要真实后端）"""

    def test_chat_stability_regression(self):
        result = _run_script("e2e_chat_stability_regression.py", timeout=120)
        print(result.stdout)
        if result.returncode != 0:
            print(result.stderr)
        assert result.returncode == 0, f"Chat stability test failed:\n{result.stderr}"


@pytest.mark.e2e
@pytest.mark.api_test
class TestE2EInquiryReceipt:
    """Inquiry 回执联动测试（使用 mock API，不需要真实后端）"""

    def test_inquiry_receipt_linkage(self):
        result = _run_script("e2e_inquiry_receipt_linkage.py", timeout=120)
        print(result.stdout)
        if result.returncode != 0:
            print(result.stderr)
        assert result.returncode == 0, f"Inquiry receipt test failed:\n{result.stderr}"
