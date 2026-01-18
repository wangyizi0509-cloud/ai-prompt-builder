"""
手动运行上下文规格验证输出
"""

from __future__ import annotations

from graph.context_builder import build_context_dict
from graph.state import create_initial_state

from tests.test_context_spec_validation import (
    create_test_layer1_memory,
    create_test_layer2_memory,
    create_test_layer3_memory,
    create_test_messages,
    print_full_context,
)


def main() -> None:
    state = create_initial_state("上下文规格验证")
    state["onboarding_completed"] = True
    state["layer1_memory"] = create_test_layer1_memory()
    state["layer2_memory"] = create_test_layer2_memory()
    state["layer3_memory"] = create_test_layer3_memory()
    state["messages"] = create_test_messages()

    context_dict = build_context_dict(state)
    print_full_context(context_dict)


if __name__ == "__main__":
    main()
