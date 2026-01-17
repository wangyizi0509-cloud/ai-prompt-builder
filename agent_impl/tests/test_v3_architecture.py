
import sys
import os
import json
from datetime import datetime

# 添加项目根目录到 Python 路径
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from graph.state import create_initial_state
from graph.context_types import (
    create_empty_layer3_memory,
    start_layer_processing,
    finish_layer_processing,
    is_layer_processing,
    create_status_report_item,
    create_action_guide_item,
    Layer2Memory,
    Layer2ExtractionConfig
)
from graph.context_builder import extract_layer3, extract_layer2, extract_layer1
from graph.archive_manager import check_layer3_compression_needed

def print_section(title):
    print(f"\n{'='*50}")
    print(f"TEST: {title}")
    print(f"{'='*50}")

def print_pass(msg):
    print(f"✅ PASS: {msg}")

def print_fail(msg):
    print(f"❌ FAIL: {msg}")

def test_initialization():
    print_section("分层结构初始化")
    state = create_initial_state("你好")
    
    checks = [
        ("layer1_memory" in state, "Layer 1 memory exists"),
        ("layer2_memory" in state, "Layer 2 memory exists"),
        ("layer3_memory" in state, "Layer 3 memory exists"),
        (state["layer1_memory"].get("version") == 1, "Layer 1 version is 1"),
        (len(state["layer3_memory"]["all_messages"]) == 1, "Layer 3 has initial message"),
    ]
    
    for cond, msg in checks:
        if cond:
            print_pass(msg)
        else:
            print_fail(msg)

def test_concurrency_fallback():
    print_section("并发处理与降级策略")
    
    # 1. 准备数据
    state = create_initial_state("初始消息")
    layer3 = state["layer3_memory"]
    
    # 添加一些测试消息
    messages = [{"role": "user", "content": f"消息 {i}"} for i in range(10)]
    layer3["all_messages"] = messages
    
    # 2. 正常提取
    print("--- 正常状态 ---")
    output_normal = extract_layer3(state)
    if "⚠️" not in output_normal:
        print_pass("正常状态无警告提示")
    
    # 3. 模拟开始处理（加锁）
    print("--- 模拟压缩进行中 ---")
    fallback_data = {"all_messages": messages[:5]} # 假设快照里只有前5条
    layer3 = start_layer_processing(layer3, "compression", fallback_data)
    state["layer3_memory"] = layer3
    
    if is_layer_processing(layer3):
        print_pass("状态已标记为 processing")
    
    # 4. 降级提取
    output_fallback = extract_layer3(state)
    
    if "⚠️ 历史对话正在整理中" in output_fallback:
        print_pass("检测到警告提示")
    else:
        print_fail("未检测到警告提示")
        
    if "消息 4" in output_fallback and "消息 6" not in output_fallback:
        print_pass("正确使用了 Fallback 数据 (包含消息4，不含消息6)")
    else:
        print_fail("Fallback 数据使用不正确")

    # 5. 完成处理（解锁）
    print("--- 模拟压缩完成 ---")
    layer3 = finish_layer_processing(layer3)
    state["layer3_memory"] = layer3
    
    if not is_layer_processing(layer3):
        print_pass("状态已清除 processing")
        
    if layer3["version"] == 2:
        print_pass("版本号已递增")

def test_compression_trigger():
    print_section("压缩触发逻辑")
    
    state = create_initial_state("init")
    layer3 = state["layer3_memory"]
    
    # 场景 1: 25条消息 (阈值是 30) -> 不触发
    layer3["all_messages"] = [{"role": "user", "content": "msg"}] * 25
    if not check_layer3_compression_needed(state):
        print_pass("25条消息不触发压缩")
    else:
        print_fail("25条消息错误触发了压缩")
        
    # 场景 2: 30条消息 (阈值边界) -> 不触发
    layer3["all_messages"] = [{"role": "user", "content": "msg"}] * 30
    if not check_layer3_compression_needed(state):
        print_pass("30条消息不触发压缩")
    else:
        print_fail("30条消息错误触发了压缩")

    # 场景 3: 35条消息 (30 + 5) -> 触发!
    layer3["all_messages"] = [{"role": "user", "content": "msg"}] * 35
    if check_layer3_compression_needed(state):
        print_pass("35条消息正确触发压缩 (超出 5 条)")
    else:
        print_fail("35条消息未能触发压缩")

    # 场景 4: 36条消息 -> 不触发 (必须是 batch_size 倍数)
    layer3["all_messages"] = [{"role": "user", "content": "msg"}] * 36
    if not check_layer3_compression_needed(state):
        print_pass("36条消息不触发压缩 (等待凑齐 5 条)")
    else:
        print_fail("36条消息错误触发了压缩")

def test_layer2_extraction():
    print_section("Layer 2 上下文提取")
    
    # 构造 Mock 数据
    current_report = create_status_report_item(
        report_content="当前报告内容...",
        report_id=2
    )
    history_report = create_status_report_item(
        report_content="历史报告内容...",
        report_id=1
    )
    history_report["summary"] = "这是历史报告的摘要"
    
    active_guide = create_action_guide_item(
        guide={"current_task": "当前任务"},
        status="in_progress",
        guide_id=1
    )
    
    layer2 = Layer2Memory(
        current_status_report=current_report,
        status_report_history=[history_report],
        current_action_plan=None,
        action_plan_history=[],
        action_guides=[active_guide],
        extraction_config=Layer2ExtractionConfig(recent_summary_count=2, max_one_liner_count=10, include_active_guides=True),
        last_updated=datetime.now().isoformat()
    )
    
    state = {"layer2_memory": layer2}
    
    output = extract_layer2(state)
    
    # 验证
    if "【报告2】" in output and "当前报告内容" in output:
        print_pass("当前报告完整提取")
    else:
        print_fail("当前报告提取失败")
        
    if "这是历史报告的摘要" in output and "历史报告内容" not in output:
        print_pass("历史报告仅提取摘要")
    else:
        print_fail("历史报告提取逻辑错误")
        
    if "当前任务" in output:
        print_pass("未完成指南提取成功")

if __name__ == "__main__":
    print("开始执行 V3 架构测试...")
    test_initialization()
    test_concurrency_fallback()
    test_compression_trigger()
    test_layer2_extraction()
    print("\n所有测试执行完毕。")

