from typing import Optional, Any
from typing_extensions import TypedDict


class OnboardingHandoff(TypedDict, total=False):
    """
    Onboarding 完成时交给主流程的摘要数据。
    - collected_context: 结构化的用户/Crush/问题信息
    - recommendation: 对主 Agent 的文字建议
    - suggested_action: 建议的下一步动作（供主 Agent 参考）
    - reason: 产生建议的简单理由，便于日志和可视化
    """
    collected_context: dict
    recommendation: str
    # 给主 Agent 的建议：自然语言即可（工程不做枚举约束）
    suggested_action: str
    reason: str


class OnboardingState(TypedDict, total=False):
    """
    Onboarding 子图在全局 AgentState 上使用的字段。
    这些字段与主状态共用，不会影响其他 Agent 的兼容性。
    """
    onboarding_completed: bool
    pending_crushe_guide: bool
    onboarding_turn_count: int
    onboarding_last_answer_fingerprint: Optional[str]
    onboarding_max_turns: int
    onboarding_handoff: Optional[OnboardingHandoff]
    collected_info: dict
    last_onboarding_question: Optional[str]
    preliminary_assessment: Optional[dict]


def get_default_onboarding_config() -> dict[str, Any]:
    """
    提供 Onboarding 相关的默认配置，便于在创建初始状态时复用。
    """
    return {
        "onboarding_completed": False,
        "pending_crushe_guide": False,
        "onboarding_turn_count": 0,
        "onboarding_last_answer_fingerprint": None,
        "onboarding_max_turns": 3,
        "onboarding_handoff": None,
        "collected_info": {},
        "last_onboarding_question": None,
    }
