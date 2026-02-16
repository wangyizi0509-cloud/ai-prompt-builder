import argparse
import asyncio
import datetime
import os
import secrets
import string
import sys
from dataclasses import dataclass

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, PROJECT_ROOT)


@dataclass(frozen=True)
class TestAccount:
    email: str
    password: str
    username: str
    user_id: str
    created_at: str
    source: str


def _gbk_len(value: str) -> int:
    return len(str(value).encode("gbk", errors="ignore"))


def _normalize_date(value: str) -> str:
    if not value:
        return ""
    if "T" in value:
        return value.split("T", 1)[0]
    return value


def _default_md_output_path() -> str:
    ts = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    return os.path.join("generated", f"test_accounts_{ts}.md")


def _ensure_parent_dir(path: str) -> None:
    parent = os.path.dirname(os.path.abspath(path))
    if parent:
        os.makedirs(parent, exist_ok=True)


def _gen_unique_password() -> str:
    """生成 16 位随机密码（大小写+数字+符号），不可预测"""
    alphabet = string.ascii_letters + string.digits + "!@#$%&*"
    while True:
        pwd = "".join(secrets.choice(alphabet) for _ in range(16))
        if (
            any(c.isupper() for c in pwd)
            and any(c.islower() for c in pwd)
            and any(c.isdigit() for c in pwd)
        ):
            return pwd


def _make_accounts_offline(
    count: int, start_index: int, password: str, unique_passwords: bool = False
) -> list[TestAccount]:
    accounts: list[TestAccount] = []
    for i in range(start_index, start_index + count):
        username_en = f"test{i:02d}"
        pwd = _gen_unique_password() if unique_passwords else password
        accounts.append(
            TestAccount(
                email=f"{username_en}@example.com",
                password=pwd,
                username=f"测试用户{i:02d}",
                user_id="",
                created_at="",
                source="offline",
            )
        )
    return accounts


async def _create_or_get_user_supabase(email: str, password: str, username: str) -> TestAccount:
    from agent_impl.supabase_service.client import create_user, get_user_by_email

    result = await create_user(email, password, username)
    if result.get("success"):
        user = result.get("user", {}) or {}
        user_id = str(user.get("id") or "")
        created_at = _normalize_date(str(user.get("created_at") or ""))
        return TestAccount(
            email=email,
            password=password,
            username=username,
            user_id=user_id,
            created_at=created_at,
            source="supabase_insert",
        )

    err = str(result.get("error") or "")
    if "exists" in err.lower() or "duplicate" in err.lower():
        user = await get_user_by_email(email)
        if not user:
            raise RuntimeError(f"Supabase 返回已存在，但查询不到用户: {email}")
        user_id = str(user.get("id") or "")
        resolved_username = str(user.get("username") or username)
        created_at = _normalize_date(str(user.get("created_at") or ""))
        return TestAccount(
            email=email,
            password=password,
            username=resolved_username,
            user_id=user_id,
            created_at=created_at,
            source="supabase_existing",
        )

    raise RuntimeError(f"写入 Supabase 失败: {email} ({err})")


async def _generate_accounts_supabase(
    count: int, start_index: int, password: str, unique_passwords: bool = False
) -> list[TestAccount]:
    accounts: list[TestAccount] = []
    for idx, i in enumerate(range(start_index, start_index + count), start=1):
        username_en = f"test{i:02d}"
        email = f"{username_en}@example.com"
        username = f"测试用户{i:02d}"
        pwd = _gen_unique_password() if unique_passwords else password
        account = await _create_or_get_user_supabase(email, pwd, username)
        accounts.append(account)
        print(f"[{idx}/{count}] {account.source}: {account.username} ({account.email})")
    return accounts


def write_markdown(accounts: list[TestAccount], output_path: str) -> None:
    _ensure_parent_dir(output_path)

    headers = ["邮箱", "密码", "用户名", "用户 ID", "创建时间"]
    rows = [[a.email, a.password, a.username, a.user_id, a.created_at] for a in accounts]

    widths = [_gbk_len(h) for h in headers]
    for r in rows:
        for i, cell in enumerate(r):
            widths[i] = max(widths[i], _gbk_len(str(cell)))
    widths = [w + 2 for w in widths]

    def fmt_row(cols: list[str]) -> str:
        out = "|"
        for i, c in enumerate(cols):
            cell = str(c)
            padding = widths[i] - _gbk_len(cell)
            if padding < 0:
                padding = 0
            out += f" {cell}{' ' * padding} |"
        return out + "\n"

    header_row = "|"
    sep_row = "|"
    for i, h in enumerate(headers):
        padding = widths[i] - _gbk_len(h)
        header_row += f" {h}{' ' * padding} |"
        sep_row += f"-{'-' * widths[i]}-|"

    content = []
    content.append("# 测试用户账号\n\n")
    content.append("本文档由脚本自动生成。\n\n")
    content.append("## 用户列表\n\n")
    content.append(header_row + "\n")
    content.append(sep_row + "\n")
    for r in rows:
        content.append(fmt_row([str(x) for x in r]))

    with open(output_path, "w", encoding="utf-8") as f:
        f.writelines(content)


def update_test_users_md(master_path: str, new_accounts: list[TestAccount]) -> None:
    new_by_email = {a.email: a for a in new_accounts}

    if os.path.exists(master_path):
        with open(master_path, "r", encoding="utf-8") as f:
            lines = f.readlines()
    else:
        lines = ["# 测试用户账号\n\n", "本文档记录了用于测试的用户账号信息。\n\n", "## 用户列表\n\n"]

    start_index = -1
    end_index = -1
    for i, line in enumerate(lines):
        if line.strip().startswith("| 邮箱"):
            start_index = i
            continue
        if start_index != -1 and i > start_index and not line.strip().startswith("|"):
            end_index = i
            break
    if start_index != -1 and end_index == -1:
        end_index = len(lines)

    existing: dict[str, TestAccount] = {}
    if start_index != -1:
        for line in lines[start_index:end_index]:
            s = line.strip()
            if not s.startswith("|"):
                continue
            if s.startswith("|---") or s.startswith("| ---"):
                continue
            if s.startswith("| 邮箱"):
                continue
            parts = [p.strip() for p in s.strip("|").split("|")]
            if len(parts) < 5:
                continue
            email, password, username, user_id, created_at = parts[:5]
            existing[email] = TestAccount(
                email=email,
                password=password,
                username=username,
                user_id=user_id,
                created_at=created_at,
                source="existing",
            )

    merged = existing | new_by_email
    merged_list = [merged[k] for k in sorted(merged.keys())]

    headers = ["邮箱", "密码", "用户名", "用户 ID", "创建时间"]
    rows = [[a.email, a.password, a.username, a.user_id, a.created_at] for a in merged_list]

    widths = [_gbk_len(h) for h in headers]
    for r in rows:
        for i, cell in enumerate(r):
            widths[i] = max(widths[i], _gbk_len(str(cell)))
    widths = [w + 2 for w in widths]

    def fmt_row(cols: list[str]) -> str:
        out = "|"
        for i, c in enumerate(cols):
            cell = str(c)
            padding = widths[i] - _gbk_len(cell)
            if padding < 0:
                padding = 0
            out += f" {cell}{' ' * padding} |"
        return out + "\n"

    header_row = "|"
    sep_row = "|"
    for i, h in enumerate(headers):
        padding = widths[i] - _gbk_len(h)
        header_row += f" {h}{' ' * padding} |"
        sep_row += f"-{'-' * widths[i]}-|"

    table_lines = [header_row + "\n", sep_row + "\n"]
    for r in rows:
        table_lines.append(fmt_row([str(x) for x in r]))

    if start_index != -1:
        lines[start_index:end_index] = table_lines
    else:
        insert_idx = -1
        for i, line in enumerate(lines):
            if "## 用户列表" in line:
                insert_idx = i + 1
                break
        if insert_idx == -1:
            lines.extend(["\n## 用户列表\n\n"])
            insert_idx = len(lines)
        lines[insert_idx:insert_idx] = ["\n"] + table_lines

    with open(master_path, "w", encoding="utf-8") as f:
        f.writelines(lines)


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="生成测试账号并导出到 Markdown")
    p.add_argument("--count", type=int, default=20)
    p.add_argument("--start", type=int, default=1, help="起始序号：1 -> test01")
    p.add_argument("--password", type=str, default="password123")
    p.add_argument(
        "--unique-passwords",
        action="store_true",
        help="每个账号使用 16 位随机密码（不可预测），适合分发给不同用户",
    )
    p.add_argument(
        "--mode",
        type=str,
        choices=["supabase", "offline"],
        default="supabase",
        help="supabase: 直接写入 users 表；offline: 仅生成清单",
    )
    p.add_argument("--md-output", type=str, default=_default_md_output_path(), help="输出 Markdown 路径")
    p.add_argument(
        "--update-test-users-md",
        type=str,
        default="",
        help="写入到主测试账号文档（例如 TEST_USERS.md，可选）",
    )
    return p.parse_args()


def main() -> None:
    args = parse_args()
    if args.mode == "offline":
        accounts = _make_accounts_offline(
            args.count, args.start, args.password, args.unique_passwords
        )
    else:
        accounts = asyncio.run(
            _generate_accounts_supabase(
                args.count, args.start, args.password, args.unique_passwords
            )
        )
    write_markdown(accounts, args.md_output)
    test_users_md = args.update_test_users_md.strip()
    if test_users_md:
        update_test_users_md(test_users_md, accounts)
    print(f"已生成: {args.md_output} (共 {len(accounts)} 条)")


if __name__ == "__main__":
    main()
