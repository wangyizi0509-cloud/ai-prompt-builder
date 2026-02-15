# 图片识别功能实现方案

## 一、背景

### 1.1 项目概述
Crushe AI Agent 是一个情感咨询 AI 智能体系统。用户在咨询过程中经常需要上传聊天截图（与暗恋对象的私聊、群聊、朋友圈等），系统需要识别截图内容并理解上下文。

### 1.2 当前状态
- **已有**: 豆包 Vision API 集成、截图上传 API、Supabase 存储、5 种截图类型定义、前端 Inquiry Modal 中的截图上传 UI
- **缺失**: 主聊天输入框不支持图片、无图片类型自动识别、无多图支持

### 1.3 目标
让用户可以在主聊天输入框直接发送图片（可与文本一起��，系统自动识别图片类型、调用豆包 OCR、将识别结果拼接到消息中发送给 Agent。

---

## 二、整体方案

### 2.1 数据流

```
用户选择图片 + 输入文本
        ↓
前端：图片类型自动识别（调用后端 API）
        ↓
前端：调用豆包 OCR（按识别出的类型，批量处理多图）
        ↓
前端：将 OCR 结果拼接到用户文本消息中
        ↓
前端：调用 /api/chat 发送拼接后的纯文本消息
        ↓
后端：正常处理文本消息（无需改动）
```

### 2.2 关键设计决策

1. **图片处理完全在前端完成**：后端 `/api/chat` 不需要改动，收到的始终是纯文本
2. **图片类型自动识别**：新增后端 API，用豆包 Vision 判断截图类型
3. **多图支持**：按上传顺序依次调用 OCR API，结果按顺序拼接
4. **消息格式**：OCR 结果以特定格式（如 `【私聊截图分析】\n...`）拼接到用户消息前面

---

## 三、需要改动的文件

### 3.1 后端改动

#### 文件 1: `agent_impl/api/upload.py`

**改动内容**: 新增图片类型自动识别 API

**新增端点**: `POST /api/upload/detect-type`

```python
@router.post("/detect-type")
async def detect_screenshot_type(
    file: UploadFile = File(...),
    current_user = Depends(get_optional_user)
):
    """
    自动识别截图类型

    Returns:
        {
            "success": bool,
            "screenshot_type": str,  # 识别出的类型
            "confidence": str,       # high/medium/low
            "error": str | None
        }
    """
```

**实现逻辑**:
1. 读取图片 bytes
2. 调用 `ImageProcessor.detect_type()` 方法（新增）
3. 返回识别结果

---

#### 文件 2: `agent_impl/utils/image_processor.py`

**改动内容**: 新增图片类型自动识别方法

**新增方法**: `detect_type()`

```python
async def detect_type(self, image_bytes: bytes) -> dict:
    """
    自动识别截图类型

    Returns:
        {
            "success": bool,
            "screenshot_type": str,
            "confidence": str,
            "error": str | None
        }
    """
```

**实现逻辑**:
1. 使用专门的类型识别 prompt（见下方）
2. 调用豆包 Vision API
3. 解析返回结果，提取类型和置信度
4. 如果无法识别，返回 `universal_screenshot_analysis`

**类型识别 Prompt** (新建文件 `agent_impl/prompts/screenshots/type_detection.md`):

```markdown
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
```

---

#### 文件 3: `agent_impl/prompts/screenshots/type_detection.md`

**改动内容**: 新建文件，内容见上方

---

### 3.2 前端改动

#### 文件 4: `agent_impl/frontend/index.html`

**改动内容**: 主聊天输入框支持图片上传

##### 4.1 新增响应式变量

在 `setup()` 函数中新增：

```javascript
// 图片上传相关
const pendingImages = ref([]);  // 待发送的图片列表 [{file, preview, status, ocrResult, type}]
const isProcessingImages = ref(false);  // 是否正在处理图片
```

##### 4.2 修改输入区域 UI

将原来的纯文本输入框改为支持图片的输入区域：

**原代码位置**: 约 947-968 行

**改为**:

```html
<!-- Input Area -->
<div class="p-3 border-t bg-white">
    <!-- 图片预览区 -->
    <div v-if="pendingImages.length > 0" class="flex flex-wrap gap-2 mb-2 p-2 bg-gray-50 rounded-lg">
        <div
            v-for="(img, index) in pendingImages"
            :key="index"
            class="relative w-16 h-16 rounded-lg overflow-hidden border"
            :class="{
                'border-gray-300': img.status === 'pending',
                'border-blue-400 animate-pulse': img.status === 'processing',
                'border-green-400': img.status === 'done',
                'border-red-400': img.status === 'error'
            }"
        >
            <img :src="img.preview" class="w-full h-full object-cover">
            <!-- 处理中遮罩 -->
            <div v-if="img.status === 'processing'" class="absolute inset-0 bg-black/50 flex items-center justify-center">
                <div class="w-4 h-4 border-2 border-white border-t-transparent rounded-full animate-spin"></div>
            </div>
            <!-- 删除按钮 -->
            <button
                v-if="img.status !== 'processing'"
                @click="removeImage(index)"
                class="absolute -top-1 -right-1 w-5 h-5 bg-red-500 text-white rounded-full text-xs flex items-center justify-center hover:bg-red-600"
            >×</button>
            <!-- 错误提示 -->
            <div v-if="img.status === 'error'" class="absolute inset-0 bg-red-500/80 flex items-center justify-center">
                <span class="text-white text-xs">失败</span>
            </div>
        </div>
    </div>

    <!-- 输入行 -->
    <div class="flex items-center space-x-2">
        <!-- 图片上传按钮 -->
        <button
            @click="triggerImageUpload"
            :disabled="isLoading || isProcessingImages"
            class="text-gray-400 hover:text-violet-500 disabled:opacity-50 p-2"
            title="上传图片"
        >
            <svg xmlns="http://www.w3.org/2000/svg" class="h-6 w-6" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M4 16l4.586-4.586a2 2 0 012.828 0L16 16m-2-2l1.586-1.586a2 2 0 012.828 0L20 14m-6-6h.01M6 20h12a2 2 0 002-2V6a2 2 0 00-2-2H6a2 2 0 00-2 2v12a2 2 0 002 2z" />
            </svg>
        </button>
        <input
            type="file"
            ref="mainImageInput"
            accept="image/*"
            multiple
            @change="handleMainImageSelect"
            class="hidden"
        >

        <!-- 文本输入框 -->
        <input
            v-model="inputMessage"
            @keyup.enter="sendMessageWithImages"
            @paste="handlePaste"
            type="text"
            placeholder="请输入您的情感问题..."
            data-testid="chat-input"
            class="flex-1 bg-gray-100 border-0 rounded-full px-4 py-2.5 text-sm focus:ring-2 focus:ring-violet-500 focus:outline-none"
            :disabled="isLoading || isProcessingImages"
        >

        <!-- 发送按钮 -->
        <button
            @click="sendMessageWithImages"
            :disabled="(!inputMessage.trim() && pendingImages.length === 0) || isLoading || isProcessingImages"
            data-testid="chat-send-btn"
            class="bg-violet-600 text-white w-10 h-10 rounded-full flex items-center justify-center hover:bg-violet-700 disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
        >
            <svg v-if="!isProcessingImages" xmlns="http://www.w3.org/2000/svg" class="h-5 w-5" viewBox="0 0 20 20" fill="currentColor">
                <path d="M10.894 2.553a1 1 0 00-1.788 0l-7 14a1 1 0 001.169 1.409l5-1.429A1 1 0 009 15.571V11a1 1 0 112 0v4.571a1 1 0 00.725.962l5 1.428a1 1 0 001.17-1.408l-7-14z" />
            </svg>
            <div v-else class="w-5 h-5 border-2 border-white border-t-transparent rounded-full animate-spin"></div>
        </button>
    </div>
</div>
```

##### 4.3 新增图片处理函数

```javascript
// 触发图片选择
const mainImageInput = ref(null);
const triggerImageUpload = () => {
    mainImageInput.value?.click();
};

// 处理图片选择
const handleMainImageSelect = async (event) => {
    const files = Array.from(event.target.files || []);
    await addImages(files);
    event.target.value = ''; // 清空 input 以便重复选择同一文件
};

// 处理粘贴图片
const handlePaste = async (event) => {
    const items = event.clipboardData?.items;
    if (!items) return;

    const imageFiles = [];
    for (const item of items) {
        if (item.type.startsWith('image/')) {
            const file = item.getAsFile();
            if (file) imageFiles.push(file);
        }
    }

    if (imageFiles.length > 0) {
        event.preventDefault();
        await addImages(imageFiles);
    }
};

// 添加图片到待发送列表
const addImages = async (files) => {
    for (const file of files) {
        // 创建预览
        const preview = URL.createObjectURL(file);
        pendingImages.value.push({
            file,
            preview,
            status: 'pending',  // pending -> processing -> done/error
            ocrResult: null,
            type: null
        });
    }
};

// 移除图片
const removeImage = (index) => {
    const img = pendingImages.value[index];
    if (img.preview) {
        URL.revokeObjectURL(img.preview);
    }
    pendingImages.value.splice(index, 1);
};

// 处理单张图片（类型识别 + OCR）
const processImage = async (imageItem) => {
    imageItem.status = 'processing';

    try {
        // 1. 自动识别类型
        const typeFormData = new FormData();
        typeFormData.append('file', imageItem.file);

        const typeResponse = await fetch('/api/upload/detect-type', {
            method: 'POST',
            headers: {
                'Authorization': `Bearer ${getToken()}`
            },
            body: typeFormData
        });

        const typeResult = await typeResponse.json();

        if (!typeResult.success) {
            throw new Error(typeResult.error || '类型识别失败');
        }

        imageItem.type = typeResult.screenshot_type;

        // 2. 调用 OCR
        const ocrFormData = new FormData();
        ocrFormData.append('file', imageItem.file);
        ocrFormData.append('screenshot_type', imageItem.type);
        ocrFormData.append('session_id', sessionId.value);

        const ocrResponse = await fetch('/api/upload-screenshot', {
            method: 'POST',
            headers: {
                'Authorization': `Bearer ${getToken()}`
            },
            body: ocrFormData
        });

        const ocrResult = await ocrResponse.json();

        if (!ocrResult.success) {
            throw new Error(ocrResult.error || 'OCR 失败');
        }

        imageItem.ocrResult = ocrResult.text;
        imageItem.status = 'done';

    } catch (error) {
        console.error('Image processing error:', error);
        imageItem.status = 'error';
        imageItem.ocrResult = `[图片处理失败: ${error.message}]`;
    }
};

// 批量处理所有待发送图片
const processAllImages = async () => {
    const pendingItems = pendingImages.value.filter(img => img.status === 'pending');

    // 按顺序处理（不并行，避免 API 压力）
    for (const item of pendingItems) {
        await processImage(item);
    }
};

// 发送消息（带图片）
const sendMessageWithImages = async () => {
    const textContent = inputMessage.value.trim();
    const hasImages = pendingImages.value.length > 0;

    if (!textContent && !hasImages) return;
    if (isLoading.value || isProcessingImages.value) return;

    // 如果有图片，先处理图片
    if (hasImages) {
        isProcessingImages.value = true;

        try {
            await processAllImages();

            // 检查是否有处理失败的图片
            const failedImages = pendingImages.value.filter(img => img.status === 'error');
            if (failedImages.length > 0 && failedImages.length === pendingImages.value.length) {
                // 全部失败，提示用户
                alert('所有图片处理失败，请重试');
                isProcessingImages.value = false;
                return;
            }

            // 拼接消息
            const imageParts = pendingImages.value
                .filter(img => img.status === 'done' && img.ocrResult)
                .map(img => {
                    const typeLabel = getScreenshotLabel(img.type);
                    return `【${typeLabel}分析结果】\n${img.ocrResult}`;
                });

            // 组合最终消息：图片分析结果在前，用户文本在后
            let finalMessage = '';
            if (imageParts.length > 0) {
                finalMessage = imageParts.join('\n\n---\n\n');
                if (textContent) {
                    finalMessage += '\n\n---\n\n' + textContent;
                }
            } else {
                finalMessage = textContent;
            }

            // 清空图片列表
            pendingImages.value.forEach(img => {
                if (img.preview) URL.revokeObjectURL(img.preview);
            });
            pendingImages.value = [];

            // 设置消息并发送
            inputMessage.value = finalMessage;

        } finally {
            isProcessingImages.value = false;
        }
    }

    // 调用原有的 sendMessage
    await sendMessage();
};
```

##### 4.4 复用已有的 `getScreenshotLabel` 函数

该函数已存在（约 1976 行），无需修改：

```javascript
const getScreenshotLabel = (type) => {
    const labels = {
        'private_chat_screenshot': '私聊截图',
        'group_chat_screenshot': '群聊截图',
        'moments_screenshot': '朋友圈截图',
        'other_social_media_screenshot': '社媒截图',
        'universal_screenshot_analysis': '截图',
    };
    return labels[type] || '截图';
};
```

---

## 四、API 接口规范

### 4.1 图片类型识别 API

**端点**: `POST /api/upload/detect-type`

**请求**:
- Content-Type: `multipart/form-data`
- Body:
  - `file`: 图片文件 (required)

**响应**:
```json
{
    "success": true,
    "screenshot_type": "private_chat_screenshot",
    "confidence": "high",
    "reason": "检测到两人对话界面，有头像和消息气泡",
    "error": null
}
```

**错误响应**:
```json
{
    "success": false,
    "screenshot_type": "universal_screenshot_analysis",
    "confidence": "low",
    "reason": null,
    "error": "API 请求失败: 500"
}
```

### 4.2 截图 OCR API（已有，无需修改）

**端点**: `POST /api/upload-screenshot`

**请求**:
- Content-Type: `multipart/form-data`
- Body:
  - `file`: 图片文件 (required)
  - `screenshot_type`: 截图类型 (required)
  - `session_id`: 会话 ID (required)
  - `context`: 额外上下文 (optional)

**响应**:
```json
{
    "success": true,
    "text": "OCR 提取的文本内容...",
    "screenshot_type": "private_chat_screenshot",
    "image_url": "https://...",
    "storage_path": "...",
    "error": null
}
```

---

## 五、消息格式规范

### 5.1 单图 + 文本

```
【私聊截图分析结果】
[OCR 提取的聊天内容]

---

[用户输入的文本]
```

### 5.2 多图 + 文本

```
【私聊截图分析结果】
[第一张图的 OCR 结果]

---

【群聊截图分析结果】
[第二张图的 OCR 结果]

---

[用户输入的文本]
```

### 5.3 纯图片（无文本）

```
【私聊截图分析结果】
[OCR 提取的聊天内容]
```

---

## 六、实现步骤

### Step 1: 后端 - 新增类型识别 Prompt
1. 创建 `agent_impl/prompts/screenshots/type_detection.md`
2. 填入类型识别 prompt 内容

### Step 2: 后端 - ImageProcessor 新增 detect_type 方法
1. 在 `agent_impl/utils/image_processor.py` 中新增 `detect_type()` 方法
2. 加载 `type_detection.md` prompt
3. 调用豆包 API 并解析 JSON 响应

### Step 3: 后端 - 新增类型识别 API
1. 在 `agent_impl/api/upload.py` 中新增 `/detect-type` 端点
2. 调用 `ImageProcessor.detect_type()`

### Step 4: 前端 - 新增图片上传 UI
1. 添加响应式变量 `pendingImages`, `isProcessingImages`
2. 修改输入区域 HTML，添加图片预览和上传按钮
3. 添加 `mainImageInput` ref

### Step 5: 前端 - 实现图片处理逻辑
1. 实现 `triggerImageUpload`, `handleMainImageSelect`, `handlePaste`
2. 实现 `addImages`, `removeImage`
3. 实现 `processImage`, `processAllImages`
4. 实现 `sendMessageWithImages`

### Step 6: 测试
1. 测试单图上传 + 类型识别 + OCR
2. 测试多图上传（按顺序处理）
3. 测试图片 + 文本混合发送
4. 测试粘贴图片
5. 测试错误处理（OCR 失败、网络错误）

---

## 七、注意事项

### 7.1 错误处理
- 类型识别失败时，fallback 到 `universal_screenshot_analysis`
- OCR 失败时，在消息中标注 `[图片处理失败: 原因]`
- 部分图片失败时，仍发送成功的部分

### 7.2 性能考虑
- 多图按顺序处理，不并行（避免 API 限流）
- 图片预览使用 `URL.createObjectURL`，发送后及时释放

### 7.3 用户体验
- 处理中显示 loading 状态
- 支持删除待发送的图片
- 支持粘贴图片（Ctrl+V）

### 7.4 不需要改动的部分
- `/api/chat` 端点：收到的始终是纯文本
- `AgentState`：不需要支持多模态
- 后端 Agent 逻辑：不需要改动

---

## 八、文件清单

| 文件路径 | 改动类型 | 说明 |
|---------|---------|------|
| `agent_impl/prompts/screenshots/type_detection.md` | 新建 | 类型识别 prompt |
| `agent_impl/utils/image_processor.py` | 修改 | 新增 `detect_type()` 方法 |
| `agent_impl/api/upload.py` | 修改 | 新增 `/detect-type` 端点 |
| `agent_impl/frontend/index.html` | 修改 | 主聊天输入框支持图片 |

---

## 九、依赖

无新增依赖，使用现有的：
- `httpx`: HTTP 客户端（已有）
- 豆包 Vision API（已配置）
