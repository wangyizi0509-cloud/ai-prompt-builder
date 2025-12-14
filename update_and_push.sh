#!/bin/bash
# 一键更新并推送到 GitHub

echo "🚀 开始更新并推送..."

# 1. 更新 index.html
echo "📝 更新 index.html..."
cp prompt_builder.html index.html

# 2. 检查是否有更改
if git diff --quiet index.html 2>/dev/null; then
    echo "✅ 没有需要更新的内容"
    exit 0
fi

# 3. 添加并提交
echo "💾 提交更改..."
git add index.html
git commit -m "Update prompt templates - $(date '+%Y-%m-%d %H:%M:%S')"

# 4. 推送到 GitHub（已配置 token，无需输入密码）
echo "📤 推送到 GitHub..."
git push origin main

if [ $? -eq 0 ]; then
    echo ""
    echo "✅ 更新成功！"
    echo "🌐 网站链接: https://wangyizi0509-cloud.github.io/ai-prompt-builder/"
    echo ""
    echo "💡 其他人可以点击网站上的 '🔄 检查更新' 按钮获取最新版本"
else
    echo ""
    echo "❌ 推送失败，请检查网络连接"
fi
