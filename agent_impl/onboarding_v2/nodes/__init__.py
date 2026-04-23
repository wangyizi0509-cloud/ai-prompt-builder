"""Onboarding v2 · LLM 节点包

- `analyze`(Agent B 产出): 合一 vision LLM 节点,同时输出筛题决策（SkipRule）+ 第一个钩子（first_hook）
- `report`（Agent C 产出）: 诊断报告 LLM 节点

两个节点的加载都使用 try/except,避免任何一方未完成时连锁阻塞另一方的 import。
"""

__all__: list[str] = []

try:  # pragma: no cover - 纯 import 兜底
    from onboarding_v2.nodes.analyze import run_analyze  # noqa: F401

    __all__.append("run_analyze")
except Exception:  # noqa: BLE001 - Agent B 还未产出时不要阻塞 report 加载
    pass

try:  # pragma: no cover - 纯 import 兜底
    from onboarding_v2.nodes.report import run_report  # noqa: F401

    __all__.append("run_report")
except Exception:  # noqa: BLE001 - 防御性:允许单独 import 子模块
    pass
