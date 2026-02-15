# 图片识别功能用户体验改造规划

## Context（背景）

当前图片识别功能存在两个用户体验问题：

1. **发送等待��验差**：用户发送图片后，需要等待 OCR 识别完成才能看到消息出现在聊天区域，期间只能看到图片上的转圈 loading
2. **识别结果展示不直观**：OCR 结果被格式化为纯文本（如 `【私聊截图分析结果】 OCR识别文本: ...`）显示在聊天气泡中，用户看不到原图

**期望效果**：
- 点击发送后，消息（含图片缩略图 + 文本）立即出现在聊天区域
- 后台异步进行图片识别，识别完成后 AI 回复
- 用户消息显示为：图片缩略图 + 用户输入的文本

---

## 实现方案

### 一、前端消息结构改造

**文件**: `agent_impl/frontend/index.html`

#### 1.1 扩展消息数据结构

当前消息格式只有 `{ role, content }`，需要扩展为：

```javascript
{
    role: 'user',
    content: string,           // 用户输入的文本
    images: [                  // 新增：图片数组
        {
            id: string,
            preview: string,   // 本地预览 URL (blob URL)
            imageUrl: string,  // Supabase 存储 URL（OCR 完成后填充）
            ocrResult: string, // OCR 识别结果（OCR 完成后填充）
            type: string,      // 截图类型
            status: 'pending' | 'processing' | 'done' | 'error'
        }
    ],
    imageProcessingStatus: 'pending' | 'processing' | 'done' | 'error'
}
```

#### 1.2 修改消息模板（第916-934行）

将当前的纯文本显示：
```html
<div v-else>{{ msg.content }}</div>
```

改为支持图片 + 文本：
```html
<div v-else>
    <!-- 图片缩略图区域 -->
    <div v-if="msg.images && msg.images.length > 0" class="mb-2">
        <div class="flex flex-wrap gap-2">
            <div
                v-for="(img, idx) in msg.images"
                :key="idx"
                class="relative w-20 h-20 rounded-lg overflow-hidden bg-gray-100"
            >
                <img :src="img.preview || img.imageUrl" class="w-full h-full object-cover">
                <!-- 处理中状态 -->
                <div v-if="img.status === 'processing'" class="absolute inset-0 bg-black/30 flex items-center justify-center">
                    <div class="w-4 h-4 border-2 border-white border-t-transparent rounded-full animate-spin"></div>
                </div>
            </div>
        </div>
    </div>
    <!-- 文本内容 -->
    <div v-if="msg.content">{{ msg.content }}</div>
</div>
```

### 二、发送流程改造

**文件**: `agent_impl/frontend/index.html` 第2247-2291行

#### 2.1 重构 sendMessageWithImages 函数

**改造后流程**：
1. 点击发送 → 立即将消息（含图片预览）添加到聊天列表
2. 清空输入框和待发送图片预览区
3. 显示 AI 思考中的 loading
4. 后台异步处理图片（类型检测 + OCR）
5. 图片处理完成后，调用 /api/chat 发送消息
6. AI 回复

```javascript
const sendMessageWithImages = async () => {
    const textContent = inputMessage.value.trim();
    const hasImages = pendingImages.value.length > 0;

    if (!textContent && !hasImages) return;
    if (isLoading.value) return;

    // 1. 立即构造消息并添加到聊天列表
    const userMessage = {
        id: Date.now().toString(),
        role: 'user',
        content: textContent,
        images: hasImages ? pendingImages.value.map(img => ({
            id: Date.now().toString() + Math.random(),
            preview: img.preview,
            imageUrl: null,
            ocrResult: null,
            type: 'universal_screenshot_analysis',
            status: 'pending'
        })) : [],
        imageProcessingStatus: hasImages ? 'processing' : 'done'
    };

    messages.value.push(userMessage);

    // 2. 清空输入区
    const imagesToProcess = [...pendingImages.value];
    inputMessage.value = '';
    clearPendingImages();

    // 3. 显示 loading
    isLoading.value = true;
    await scrollToBottom();

    // 4. 后台处理图片
    if (imagesToProcess.length > 0) {
        await processImagesForMessage(userMessage, imagesToProcess);
    }

    // 5. 发送到后端
    await sendMessageToBackend(userMessage);
};
```

#### 2.2 新增 processImagesForMessage 函数

```javascript
const processImagesForMessage = async (userMessage, imagesToProcess) => {
    const processPromises = imagesToProcess.map(async (imgItem, index) => {
        const msgImage = userMessage.images[index];
        msgImage.status = 'processing';

        try {
            // 类型检测
            const typeFormData = new FormData();
            typeFormData.append('file', imgItem.file);

            let detectedType = 'universal_screenshot_analysis';
            try {
                const typeResponse = await fetch('/api/upload/detect-type', {
                    method: 'POST',
                    headers: { 'Authorization': `Bearer ${getToken()}` },
                    body: typeFormData
                });
                const typeResult = await typeResponse.json();
                if (typeResponse.ok && typeResult.success) {
                    detectedType = typeResult.screenshot_type;
                }
            } catch (e) {
                console.warn('Type detection failed:', e);
            }

            // OCR 处理
            const ocrFormData = new FormData();
            ocrFormData.append('file', imgItem.file);
            ocrFormData.append('screenshot_type', detectedType);
            ocrFormData.append('session_id', sessionId.value);

            const ocrResponse = await fetch('/api/upload/upload-screenshot', {
                method: 'POST',
                headers: { 'Authorization': `Bearer ${getToken()}` },
                body: ocrFormData
            });

            const ocrResult = await ocrResponse.json();

            if (ocrResponse.ok && ocrResult.success) {
                msgImage.ocrResult = ocrResult.text;
                msgImage.imageUrl = ocrResult.image_url;
                msgImage.type = detectedType;
                msgImage.status = 'done';
            } else {
                throw new Error(ocrResult.error || 'OCR failed');
            }
        } catch (error) {
            msgImage.status = 'error';
            msgImage.ocrResult = `[处理失败: ${error.message}]`;
        }
    });

    await Promise.all(processPromises);
    userMessage.imageProcessingStatus =
        userMessage.images.every(img => img.status === 'done') ? 'done' : 'error';
};
```

#### 2.3 新增 sendMessageToBackend 函数

```javascript
const sendMessageToBackend = async (userMessage) => {
    try {
        const requestBody = {
            message: userMessage.content,
            session_id: sessionId.value
        };

        // 如果有图片，添加图片信息
        if (userMessage.images && userMessage.images.length > 0) {
            requestBody.images = userMessage.images
                .filter(img => img.status === 'done')
                .map(img => ({
                    image_url: img.imageUrl,
                    ocr_result: img.ocrResult,
                    screenshot_type: img.type
                }));
        }

        const response = await fetch('/api/chat', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
                'Authorization': `Bearer ${getToken()}`
            },
            body: JSON.stringify(requestBody)
        });

        // 处理响应（复用现有 sendMessage 的响应处理逻辑）
        // ...
    } finally {
        isLoading.value = false;
    }
};
```

### 三、后端 API 改造

**文件**: `agent_impl/api/chat.py`

#### 3.1 扩展请求模型

在文件开头的模型定义区域添加：

```python
class ImageInfo(BaseModel):
    image_url: Optional[str] = None
    ocr_result: Optional[str] = None
    screenshot_type: Optional[str] = None

class ChatRequest(BaseModel):
    message: str
    session_id: str
    feedback_mode: Optional[FeedbackModeInput] = None
    images: Optional[List[ImageInfo]] = None  # 新增
```

#### 3.2 修改 chat 函数

在构造 `state["user_message"]` 之前，添加图片信息处理逻辑：

```python
# 构造增强消息
final_message = request.message
if request.images:
    image_parts = []
    for img in request.images:
        if img.ocr_result:
            type_label = _get_screenshot_label(img.screenshot_type)
            image_parts.append(f"【{type_label}分析结果】\n{img.ocr_result}")

    if image_parts:
        final_message = "\n\n---\n\n".join(image_parts)
        if request.message:
            final_message += f"\n\n---\n\n用户补充说明：{request.message}"

state["user_message"] = final_message
```

#### 3.3 添加辅助函数

```python
def _get_screenshot_label(screenshot_type: str) -> str:
    """获取截图类型的中文标签"""
    labels = {
        'private_chat_screenshot': '私聊截图',
        'group_chat_screenshot': '群聊截图',
        'moments_screenshot': '朋友圈截图',
        'other_social_media_screenshot': '其他社媒截图',
        'universal_screenshot_analysis': '通用截图'
    }
    return labels.get(screenshot_type, '截图')
```

---

## 需要修改的文件清单

| 文件 | 修改内容 | 优先级 |
|------|---------|--------|
| `agent_impl/frontend/index.html` | 消息模板、发送流程、新增函数 | 高 |
| `agent_impl/api/chat.py` | 扩展请求模型、处理图片信息 | 高 |

**无需修改的文件**：
- `agent_impl/api/upload.py` - 现有 API 可复用
- `agent_impl/utils/image_processor.py` - 现有处理器可复用
- `agent_impl/graph/state.py` - 暂不需要持久化图片信息

---

## 验证方法

### 功能测试

1. **基本流程**：
   - 选择图片 + 输入文本 "这咋办"
   - 点击发送
   - 验证：消息立即出现（图片缩略图 + 文本）
   - 验证：图片上显示处理中状态
   - 验证：AI 正常回复

2. **边界情况**：
   - 只发送图片，不输入文本
   - 发送多张图片
   - 图片处理失败时的错误提示

### 启动服务

```bash
python3 .trae/skills/service-manager/scripts/start_services.py --mode dev
# 访问 http://localhost:8000
```

---

## 实现步骤

1. **Step 1**: 修改前端消息模板，支持显示图片缩略图
2. **Step 2**: 重构 `sendMessageWithImages` 函数，实现立即显示消息
3. **Step 3**: 新增 `processImagesForMessage` 和 `sendMessageToBackend` 函数
4. **Step 4**: 修改后端 `ChatRequest` 模型和 `chat` 函数
5. **Step 5**: 测试验证
