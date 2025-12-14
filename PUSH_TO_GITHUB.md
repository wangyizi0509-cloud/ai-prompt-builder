# 推送代码到 GitHub

## 方法一：使用终端（推荐）

在终端执行以下命令：

```bash
cd "/Users/ant/Desktop/Crushe/模型策略"
git push -u origin main
```

如果提示输入用户名和密码：
- **用户名**：`wangyizi0509-cloud`
- **密码**：使用 GitHub Personal Access Token（不是账号密码）

### 如何获取 Personal Access Token：
1. 访问：https://github.com/settings/tokens
2. 点击 `Generate new token` → `Generate new token (classic)`
3. 勾选 `repo` 权限
4. 点击 `Generate token`
5. 复制生成的 token（只显示一次，请保存好）
6. 推送时，密码处粘贴这个 token

---

## 方法二：使用 GitHub Desktop（最简单）

1. 下载 GitHub Desktop：https://desktop.github.com
2. 安装后登录你的 GitHub 账号
3. 点击 `File` → `Add Local Repository`
4. 选择文件夹：`/Users/ant/Desktop/Crushe/模型策略`
5. 点击 `Publish repository` 按钮
6. 确认仓库名是 `ai-prompt-builder`
7. 点击 `Publish repository`

---

## 方法三：网页上传（如果命令行不行）

1. 在 GitHub 仓库页面，点击 `uploading an existing file`
2. 把 `index.html` 文件拖进去
3. 点击 `Commit changes`

---

推送成功后，继续下一步：启用 GitHub Pages



