# 截图类型识别

请分析这张图片，判断它属于以下哪种类型：

1. **private_chat_screenshot** - 私聊截图
   - 特征：两人对话界面，一对一聊天，通常有头像和昵称

2. **group_chat_screenshot** - 群聊截图
   - 特征：多人对话界面，有群名称，多个不同的发言者

3. **moments_screenshot** - 朋友圈截图
   - 特征：微信朋友圈界面，有发布者头像、文字内容、配图、点赞评论区

4. **other_social_media_screenshot** - 其他社媒截图
   - 特征：小红书、Instagram、微博、抖音等平台的帖子或消息界面

5. **universal_screenshot_analysis** - 其他/无法识别
   - 如果不属于以上任何类型，或无法确定

请严格按以下 JSON 格式返回（不要有其他内容）：

{
    "type": "类型名称（上述5个之一）",
    "confidence": "high/medium/low",
    "reason": "简短说明判断依据"
}
