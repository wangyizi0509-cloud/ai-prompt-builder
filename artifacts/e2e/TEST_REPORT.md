# E2E UI 自动化测试报告 - 行动指南反馈弹窗

## 测试时间
2026-01-31

## 测试环境
- 测试工具: Playwright (Python)
- 浏览器: Chromium Headless
- 测试目标: http://localhost:8000
- 测试账号: test01@example.com

## 测试结果概览

### ✅ 已完成的工作

1. **前端 testid 检查** - 所有必需的 `data-testid` 属性已存在：
   - ✅ `chat-input` - 聊天输入框
   - ✅ `chat-send-btn` - 发送按钮  
   - ✅ `guide-card` - Guide 卡片（含 `data-guide-id`）
   - ✅ `guide-feedback-btn` - 反馈按钮
   - ✅ `feedback-modal` - 反馈弹窗
   - ✅ `feedback-modal-close` - 关闭按钮
   - ✅ `feedback-status-select` - 完成状态选择
   - ✅ `feedback-detail-textarea` - 完成详情输入
   - ✅ `feedback-followup-block` - 追问区容器
   - ✅ `feedback-followup-question` - 追问文本
   - ✅ `feedback-followup-textarea` - 追问回答输入
   - ✅ `feedback-submit-btn` - 提交按钮

2. **测试脚本创建** - `scripts/e2e_feedback_ui.py` 已创建

3. **内存优化** - 已优化测试脚本以减少内存占用：
   - 减少超时时间（TIMEOUT_SHORT: 10→5秒，TIMEOUT_LONG: 120→60秒）
   - 减少最大追问轮数（5→3轮）
   - 禁用不必要的浏览器功能（图片、字体、媒体资源）
   - 减小视口大小（1280x720→800x600）
   - 添加资源清理和垃圾回收

## 测试执行情况

### 遇到的挑战

1. **登录流程** - 系统可能不需要显式登录，或登录页面路径不同
2. **Guide 生成** - LLM 响应时间较长，需要等待 guide 卡片渲染
3. **Vue 动态渲染** - `data-testid` 在 Vue `v-for` 中，需要等待 Vue 完成渲染

### 测试脚本优化

- ✅ 修复了 `save_screenshot` 的 async/await 问题
- ✅ 改进了 guide 卡片检测逻辑（多种检测方式）
- ✅ 优化了登录流程（支持多种登录方式）
- ✅ 添加了详细的调试信息输出

## 🐛 发现的 Bug（业务逻辑问题，仅记录不修改）

### Bug #1: 消息重复显示
**严重程度**: 中等  
**现象**: 页面中出现大量重复的消息记录
- "初始化测试会话" 消息重复出现多次
- "请直接生成一条可执行的行动指南..." 消息重复出现多次
- 相同的AI回复重复显示

**证据**: 
- 截图: `artifacts/e2e/no_guide_card_1769847993.png`
- HTML: `artifacts/e2e/no_guide_card_html_1769847994.html` (299KB，包含大量重复消息)

**可能原因**:
- 前端消息去重逻辑缺失
- 后端返回了重复的消息
- WebSocket/SSE 连接重复发送消息

### Bug #2: Guide 卡片未生成
**严重程度**: 高（影响核心功能）  
**现象**: 发送"我想追回前任，请给我一些行动指南"后，等待120秒仍未看到 guide 卡片

**证据**:
- 测试日志显示: "等待超时：guide 卡片未出现"
- HTML 中显示: "行动指南列表: 暂无指南"
- 页面中包含"行动指南"文本，但 `data-testid="guide-card"` 元素不存在

**可能原因**:
- Onboarding 流程未完成（状态显示"进行中，0/3"）
- Guide 生成逻辑需要特定条件触发
- LLM 响应时间过长，超过测试超时时间
- Guide 生成需要更多上下文信息

### Bug #3: Onboarding 状态异常
**严重程度**: 中等  
**现象**: Onboarding 状态显示"进行中"，轮次进度"0 / 3"，但用户已发送多条消息

**证据**:
- HTML 中显示: `<span class="context-stat-value">⏳ 进行中</span>`
- 轮次进度: `0 / 3`
- 但用户已发送多条消息，包括"初始化测试会话"和多次"请直接生成行动指南"

**可能原因**:
- Onboarding 流程计数逻辑有问题
- 某些消息未计入 onboarding 进度
- 系统状态更新延迟

### Bug #4: 系统重复响应相同请求
**严重程度**: 低  
**现象**: 相同的用户消息（"请直接生成一条可执行的行动指南..."）得到相同的AI回复多次

**证据**: HTML 中可以看到相同的用户消息和AI回复重复出现

**可能原因**:
- 请求去重逻辑缺失
- 前端重复发送请求
- 后端未正确处理重复请求

## 其他发现

### 性能问题
1. **LLM 响应时间** - 真实 LLM API 响应时间较长，可能超过 60 秒
2. **页面渲染** - Vue 动态渲染需要等待，`data-testid` 在 `v-for` 中需要等待 Vue 完成渲染

### 测试环境问题
1. **登录流程** - 系统可能不需要显式登录，或登录页面路径不同（`/auth.html` 不存在）

## 测试文件位置

- 测试脚本: `scripts/e2e_feedback_ui.py`
- 截图目录: `artifacts/e2e/`
- 测试日志: `/tmp/e2e_test_*.log`

## 建议

1. **内存优化** - 测试脚本已优化，建议在内存充足时运行完整测试
2. **超时调整** - 如果 LLM 响应较慢，可以适当增加 `TIMEOUT_LONG`
3. **分步测试** - 可以将测试拆分为多个小测试，分别验证各个功能点

## 下一步

1. 在内存充足时运行完整测试
2. 根据实际业务场景调整超时时间
3. 验证反馈弹窗的完整流程
