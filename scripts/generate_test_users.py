import requests
import datetime
import os

BASE_URL = "http://127.0.0.1:8000"
TEST_USERS_FILE = "TEST_USERS.md"

def generate_users(count=10):
    new_users = []
    
    print(f"Start generating {count} test users...")
    
    for i in range(1, count + 1):
        # 使用规范的命名: test01, test02...
        username_en = f"test{i:02d}"
        username_cn = f"测试用户{i:02d}"
        email = f"{username_en}@example.com"
        password = "password123"
        
        payload = {
            "email": email,
            "password": password,
            "username": username_cn
        }
        
        try:
            # 先尝试注册
            resp = requests.post(f"{BASE_URL}/api/auth/register", json=payload)
            data = resp.json()
            
            if resp.status_code == 200 and data.get("success"):
                user = data.get("user", {})
                user_id = user.get("id", "unknown")
                created_at = user.get("created_at", datetime.datetime.now().isoformat())
                if "T" in created_at:
                    created_at = created_at.split("T")[0]
                
                new_users.append({
                    "email": email,
                    "password": password,
                    "username": username_cn,
                    "user_id": user_id,
                    "created_at": created_at
                })
                print(f"[{i}/{count}] Created: {username_cn} ({email})")
            elif resp.status_code == 409:
                 # 如果已存在，尝试登录获取 ID
                 print(f"[{i}/{count}] User {email} already exists, trying login...")
                 login_resp = requests.post(f"{BASE_URL}/api/auth/login", json={"email": email, "password": password})
                 login_data = login_resp.json()
                 if login_resp.status_code == 200 and login_data.get("success"):
                     user = login_data.get("user", {})
                     user_id = user.get("id", "unknown")
                     created_at = user.get("created_at", datetime.datetime.now().isoformat())
                     if "T" in created_at:
                        created_at = created_at.split("T")[0]
                     
                     new_users.append({
                        "email": email,
                        "password": password,
                        "username": username_cn,
                        "user_id": user_id,
                        "created_at": created_at
                     })
                     print(f"[{i}/{count}] Retrieved: {username_cn} ({email})")
                 else:
                     print(f"[{i}/{count}] Failed to login {email}")
            else:
                print(f"[{i}/{count}] Failed to register {email}: {data.get('error')}")
                
        except Exception as e:
            print(f"[{i}/{count}] Exception: {e}")

    return new_users

def format_table_row(row_data, widths):
    """格式化表格行，使其对齐"""
    row = "|"
    for i, col in enumerate(row_data):
        # 中文字符宽度处理比较复杂，这里简单处理，假设中文字符占2个宽度（在编辑器中）
        # 但在 python 字符串长度中只占1。
        # 为了简单起见，我们直接用足够长的 padding，或者使用简单的 ljust
        # 这里为了 markdown 源码好看，我们尽量对齐
        cell = str(col)
        padding = widths[i] - len(cell.encode('gbk', errors='ignore')) # 粗略估计显示宽度
        if padding < 0: padding = 0
        row += f" {cell}{' ' * padding} |"
    return row + "\n"

def update_markdown_file(new_users):
    if not new_users:
        print("No users to add.")
        return

    # 定义表头
    headers = ["邮箱", "密码", "用户名", "用户 ID", "创建时间"]
    
    # 计算每列最大宽度
    widths = [len(h.encode('gbk', errors='ignore')) for h in headers]
    
    for user in new_users:
        vals = [user['email'], user['password'], user['username'], user['user_id'], user['created_at']]
        for i, v in enumerate(vals):
            w = len(str(v).encode('gbk', errors='ignore'))
            if w > widths[i]:
                widths[i] = w
    
    # 增加一点 padding
    widths = [w + 2 for w in widths]

    if not os.path.exists(TEST_USERS_FILE):
        print(f"File {TEST_USERS_FILE} not found.")
        return

    with open(TEST_USERS_FILE, 'r', encoding='utf-8') as f:
        lines = f.readlines()

    # 找到表格位置
    start_index = -1
    end_index = -1
    for i, line in enumerate(lines):
        if line.strip().startswith("| 邮箱"):
            start_index = i
        elif start_index != -1 and not line.strip().startswith("|"):
            end_index = i
            break
    
    if end_index == -1:
        end_index = len(lines)

    # 生成新表格
    new_table = []
    
    # 表头
    header_row = "|"
    separator_row = "|"
    for i, h in enumerate(headers):
        padding = widths[i] - len(h.encode('gbk', errors='ignore'))
        header_row += f" {h}{' ' * padding} |"
        separator_row += f"-{'-' * widths[i]}-|"
    
    new_table.append(header_row + "\n")
    new_table.append(separator_row + "\n")
    
    # 数据行
    for user in new_users:
        row_data = [user['email'], user['password'], user['username'], user['user_id'], user['created_at']]
        new_table.append(format_table_row(row_data, widths))

    # 替换旧表格
    if start_index != -1:
        lines[start_index:end_index] = new_table
    else:
        # 如果没找到表格，就在 "## 用户列表" 后添加
        insert_idx = -1
        for i, line in enumerate(lines):
            if "## 用户列表" in line:
                insert_idx = i + 1
                break
        if insert_idx != -1:
            lines[insert_idx:insert_idx] = ["\n"] + new_table
        else:
            lines.extend(["\n## 用户列表\n\n"] + new_table)

    with open(TEST_USERS_FILE, 'w', encoding='utf-8') as f:
        f.writelines(lines)
    
    print(f"Successfully updated {TEST_USERS_FILE} with formatted table.")

if __name__ == "__main__":
    users = generate_users(10)
    update_markdown_file(users)
