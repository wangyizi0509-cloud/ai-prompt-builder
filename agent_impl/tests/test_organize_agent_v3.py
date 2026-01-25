"""
测试 Organize Agent v3 优化效果

测试目标：
1. 废话过滤
2. Layer 1 / 动态情报分流
3. 来源判断准确性
4. 代码改动正确性
5. 摘要质量
"""

import sys
import os
from pathlib import Path

# 添加项目根目录与 agent_impl 到 path
project_root = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(project_root))
sys.path.insert(0, str(project_root / "agent_impl"))

from graph.nodes.organize_agent import (
    organize_and_archive,
    archive_conversation_batch,
)
from graph.context_types import UserContext


def create_empty_context() -> UserContext:
    """创建空的用户上下文"""
    return UserContext(
        user_info={"user_provide": [], "fact": [], "ai_provide": []},
        crush_info={"crush_name": "", "user_provide": [], "fact": [], "ai_provide": []},
        both_info={"user_provide": [], "fact": [], "ai_provide": []},
    )


def test_waste_filter():
    """测试 1：废话过滤"""
    print("\n" + "=" * 60)
    print("测试 1：废话过滤")
    print("=" * 60)

    messages = [
        {"role": "user", "content": "她今天又已读不回我了，唉烦死了"},
        {"role": "assistant", "content": "能理解你的感受。她最近是不是比较忙？"},
        {"role": "user", "content": "她说这周要加班，但我也不确定是不是真的"},
        {"role": "assistant", "content": "你们现在主要通过什么方式联系？"},
        {"role": "user", "content": "微信吧，她朋友圈不怎么发"},
        {"role": "assistant", "content": "明白了。她平时是什么性格？主动还是比较被动？"},
        {"role": "user", "content": "挺被动的，基本都是我主动找她"},
        {"role": "assistant", "content": "嗯嗯，这种模式可能需要调整一下"},
        {"role": "user", "content": "哈哈哈你说的太对了，就是这种感觉"},
    ]

    context = create_empty_context()
    result = archive_conversation_batch(messages, context)

    print("\n📦 返回结果结构：", list(result.keys()))
    print("\n📝 摘要：", result["conversation_archive"].get("summary", ""))
    print("\n🏷️ 关键话题：", result["conversation_archive"].get("key_topics", []))

    # 检查 Layer 1 提取结果
    print("\n📊 Layer 1 提取结果：")
    extracted = result["conversation_archive"].get("extracted_info", {})
    for dimension in ["user_info", "crush_info", "both_info"]:
        dim_data = extracted.get(dimension, {})
        for source in ["user_provide", "fact", "ai_provide"]:
            items = dim_data.get(source, [])
            if items:
                print(f"  {dimension}.{source}:")
                for item in items:
                    print(f"    - {item}")

    # 检查动态情报
    print("\n📅 动态情报：")
    for intel in result.get("dynamic_intels", []):
        print(
            f"  - [{intel.get('category')}][{intel.get('subject')}] "
            f"{intel.get('content')} (置信度: {intel.get('confidence')})"
        )

    # 验证废话没有被记录
    all_content = str(extracted) + str(result.get("dynamic_intels", []))
    waste_words = ["唉烦死了", "我也不确定", "微信吧", "哈哈哈", "就是这种感觉"]

    print("\n✅ 废话过滤检查：")
    for word in waste_words:
        if word in all_content:
            print(f"  ❌ 废话 '{word}' 被错误记录！")
        else:
            print(f"  ✅ 废话 '{word}' 已被正确过滤")


def test_layer_separation():
    """测试 2：Layer 1 / 动态情报分流"""
    print("\n" + "=" * 60)
    print("测试 2：Layer 1 / 动态情报分流")
    print("=" * 60)

    messages = [
        {"role": "user", "content": "她是设计师，在一家广告公司上班"},
        {"role": "assistant", "content": "了解了，你们是怎么认识的？"},
        {"role": "user", "content": "朋友聚会上认识的，已经认识两个月了"},
        {"role": "assistant", "content": "最近有没有什么互动？"},
        {"role": "user", "content": "她说下周要去上海出差，让我别找她"},
        {"role": "assistant", "content": "她最近心情怎么样？"},
        {"role": "user", "content": "她说最近项目压力大，心情不太好"},
    ]

    context = create_empty_context()
    result = archive_conversation_batch(messages, context)

    extracted = result["conversation_archive"].get("extracted_info", {})
    dynamic_intels = result.get("dynamic_intels", [])

    print("\n📊 Layer 1（长期信息）：")
    for dimension in ["user_info", "crush_info", "both_info"]:
        dim_data = extracted.get(dimension, {})
        for source in ["user_provide", "fact", "ai_provide"]:
            items = dim_data.get(source, [])
            if items:
                print(f"  {dimension}.{source}:")
                for item in items:
                    print(f"    - {item}")

    print("\n📅 动态情报（短期信息）：")
    for intel in dynamic_intels:
        print(f"  - [{intel.get('category')}][{intel.get('subject')}] {intel.get('content')}")

    # 验证分流正确
    print("\n✅ 分流检查：")

    # 检查长期信息是否在 Layer 1
    layer1_content = str(extracted)
    if "设计师" in layer1_content:
        print("  ✅ '设计师' 在 Layer 1")
    else:
        print("  ❌ '设计师' 应该在 Layer 1")

    if "朋友聚会" in layer1_content or "认识" in layer1_content:
        print("  ✅ 认识方式在 Layer 1")
    else:
        print("  ❌ 认识方式应该在 Layer 1")

    # 检查短期信息是否在动态情报
    intel_content = str(dynamic_intels)
    if "上海" in intel_content or "出差" in intel_content:
        print("  ✅ '上海出差' 在动态情报")
    else:
        print("  ❌ '上海出差' 应该在动态情报")

    if "压力" in intel_content or "心情" in intel_content:
        print("  ✅ '心情不好' 在动态情报")
    else:
        print("  ❌ '心情不好' 应该在动态情报")


def test_source_classification():
    """测试 3：来源判断准确性"""
    print("\n" + "=" * 60)
    print("测试 3：来源判断准确性")
    print("=" * 60)

    messages = [
        {"role": "user", "content": "她跟我说她有男朋友了"},
        {"role": "assistant", "content": "她是在什么情况下说的？"},
        {"role": "user", "content": "就在微信里直接说的，我截图给你看"},
        {
            "role": "assistant",
            "content": "好的，我看到了截图，Crush 说'我有男朋友了，我们还是做朋友吧'",
        },
        {"role": "user", "content": "她已读不回我 3 天了"},
        {"role": "user", "content": "我感觉她可能还是对我有点意思"},
    ]

    context = create_empty_context()
    result = archive_conversation_batch(messages, context)

    extracted = result["conversation_archive"].get("extracted_info", {})

    print("\n📊 来源分类结果：")
    for dimension in ["user_info", "crush_info", "both_info"]:
        dim_data = extracted.get(dimension, {})
        for source in ["user_provide", "fact", "ai_provide"]:
            items = dim_data.get(source, [])
            if items:
                print(f"  {dimension}.{source}:")
                for item in items:
                    print(f"    - {item}")

    print("\n✅ 来源判断检查：")
    extracted_text = str(extracted)
    checks = [
        ("用户转述：Crush表示自己有男朋友", "user_provide"),
        ("Crush在聊天中说：", "fact"),
        ("Crush已读不回", "fact"),
        ("用户感觉：Crush可能对自己有好感", "user_provide"),
    ]
    for snippet, _ in checks:
        if snippet in extracted_text:
            print(f"  ✅ 命中：{snippet}")
        else:
            print(f"  ❌ 未命中：{snippet}")
    print("  （置信度区间仍需人工核对）")


def main():
    """运行所有测试"""
    print("🚀 开始测试 Organize Agent v3 优化效果")
    print(
        "🔍 LLM 环境："
        f"provider={os.getenv('LLM_PROVIDER') or 'deepseek'} "
        f"has_deepseek_key={bool(os.getenv('DEEPSEEK_API_KEY'))} "
        f"has_openai_key={bool(os.getenv('OPENAI_API_KEY'))} "
        f"has_anthropic_key={bool(os.getenv('ANTHROPIC_API_KEY'))}"
    )

    test_waste_filter()
    test_layer_separation()
    test_source_classification()

    print("\n" + "=" * 60)
    print("✅ 测试完成！请检查上述输出是否符合预期。")
    print("=" * 60)


if __name__ == "__main__":
    main()
