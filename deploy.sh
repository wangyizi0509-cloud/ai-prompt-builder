#!/bin/bash
# GitHub Pages 部署脚本

echo "🚀 开始部署到 GitHub Pages..."
echo ""

# 检查是否已初始化 git
if [ ! -d ".git" ]; then
    echo "📦 初始化 Git 仓库..."
    git init
    git branch -M main
fi

# 更新 index.html
echo "📝 更新 index.html..."
cp prompt_builder.html index.html

# 添加文件
echo "➕ 添加文件到 Git..."
git add index.html .gitignore

# 检查是否有更改
if git diff --staged --quiet; then
    echo "✅ 没有需要提交的更改"
else
    echo "💾 提交更改..."
    git commit -m "Update prompt builder"
fi

echo ""
echo "✅ 本地准备完成！"
echo ""
echo "📋 接下来的步骤："
echo "1. 在 GitHub 上创建新仓库（如果还没有）"
echo "2. 复制下面的命令并执行（替换 YOUR_USERNAME 和 REPO_NAME）："
echo ""
echo "   git remote add origin https://github.com/YOUR_USERNAME/REPO_NAME.git"
echo "   git push -u origin main"
echo ""
echo "3. 在 GitHub 仓库设置中启用 Pages："
echo "   Settings → Pages → Source: main branch → Save"
echo ""



