"""
E2E 测试脚本：Task-bound Action Guide Detail（按 PRD 流程多轮推进）

特性：
- 固定 session_id，确保跨轮次状态
- 自动推进 Onboarding / Status / Plan 的提问（用统一的“长回答”回填）
- 一旦产出 layer2_memory.all_action_guides，执行 bind_action_guide_detail 并校验：
  - 写入 active task.bound_action_guides
  - 重复绑定去重覆盖
  - create_task 切换隔离
  - K=3 FIFO 淘汰（尽力生成 >=4 guides，不够则标记为 blocked）

用法：
  cd agent_impl
  python3 scripts/run_case_bind_action_guide_e2e.py
"""

from __future__ import annotations

import json
import time
from dataclasses import dataclass
from typing import Any

import httpx


BASE = "http://127.0.0.1:8000"
TIMEOUT = httpx.Timeout(600.0, connect=10.0)

# 统一回填文本（来自 PRD 文档，适当去掉表情/复杂引号，避免脚本解析问题）
LONG_CONTEXT = """\
我和他是打排球认识的。最开始我没和他一起打，后来他自己来找我打，然后我俩就两个人单打。
最开始他扣球不扣我，要不让别人扣我，但是刚开始打排球的人他都扣。
最开始打完了，他自己很快就走了，现在除了教我动作以外，都会在我周围，不近不远的跟着。
因为我们这里是东北，所以晚上打球的时候就已经零下了，我说我冷，他就要把手套给我。
我俩打球的时候啥都聊，处对象啊，学习啊，这些都聊。
我俩都是不处对象那种人，所以我会经常拿他和帝总（也是男生）处对象开玩笑。
前天他突然和我说他想处对象，不是和帝总的那种。
今天我给他做了一个圣诞帽的头像，我俩聊了挺多的，前面都挺开心的，但最后好像聊崩了。

聊天记录（表格原样复述）：
- 用户：圣诞帽你真的不戴吗（1）
- crush：看看（2）
- 用户：行，你傲娇（3）
- crush：一会俗晚宁戴个套（4）
- 用户：啥玩意（5）
- 用户：说啥呢（6）
- crush：头套吗？（7）
- 用户：哦（8）
- crush：？（9）
- crush：想啥呢？（10）
- 用户：我还以为你前天说相处对象，今天就有了呢（11）
- crush：…（12）
- crush：6（13）
- 用户：低调低调（14）
- crush：你怕不是看多了（15）
- 用户：你之前不说你脑子里都是打码的嘛（16）
- crush：……（17）
- crush：打码的是（图片）（18）
- 用户：你不是说相处对象，不是机帝总的吗（19）
- 用户：你咋这样呢（20）
- crush：拒绝回答（21）
- 用户：好好好（22）
- crush：到此为止了（23）
- 用户：嗯（24）
- 用户：不堆了不堆了（25）

昨天聊完就没了。
除了打球，你们平时线上聊天多吗？主要是谁主动找谁？我俩差不多。
"""


ASK_GUIDES_STRONG = "我现在要行动指南（SOP+话术），请直接产出 3 条行动指南。"
ASK_MORE_GUIDES_STRONG = "请继续直接新增行动指南（SOP+话术），不要提问。请确保新增的每条行动指南都有不同的 guide_id。"


def _safe_get(d: dict, path: list[str], default=None):
    cur: Any = d
    for k in path:
        if not isinstance(cur, dict):
            return default
        cur = cur.get(k)
    return cur if cur is not None else default


def get_guides(state: dict) -> list[dict]:
    guides = _safe_get(state, ["layer2_memory", "all_action_guides"], default=[])
    return guides if isinstance(guides, list) else []


def get_tasks(state: dict, agent: str = "main_agent") -> list[dict]:
    tasks = _safe_get(state, ["layer3_memory", "task_registry", agent], default=[])
    return tasks if isinstance(tasks, list) else []


def get_active_task(tasks: list[dict]) -> dict | None:
    for t in tasks:
        if isinstance(t, dict) and (t.get("is_active") is True or t.get("status") == "active"):
            return t
    return None


def state_snippet(state: dict) -> dict:
    guides = get_guides(state)
    tasks = get_tasks(state)
    active = get_active_task(tasks)
    return {
        "onboarding_completed": state.get("onboarding_completed"),
        "next_action": state.get("next_action"),
        "route_to": state.get("route_to"),
        "current_agent": state.get("current_agent"),
        "guides_count": len(guides),
        "guide_ids_preview": [g.get("id") for g in guides[:5] if isinstance(g, dict)],
        "tasks_count(main_agent)": len(tasks),
        "active_task_id": active.get("task_id") if isinstance(active, dict) else None,
        "active_bound_ids": (
            [bg.get("guide_id") for bg in (active.get("bound_action_guides") or []) if isinstance(bg, dict)]
            if isinstance(active, dict)
            else []
        ),
    }


@dataclass
class CaseResult:
    case: str
    passed: bool
    details: dict


def post_chat(client: httpx.Client, session_id: str, message: str) -> tuple[dict, dict]:
    r = client.post(f"{BASE}/api/chat", json={"message": message, "session_id": session_id})
    r.raise_for_status()
    data = r.json()
    state = data.get("state") or {}
    return data, state


def wants_more_info(state: dict) -> bool:
    # 兼容 ask_user 与子 agent 的 inquiry_card
    if state.get("next_action") == "ask_user":
        return True
    if state.get("pending_questions"):
        return True
    if state.get("inquiry_card"):
        return True
    return False


def advance_until_guides(
    client: httpx.Client,
    session_id: str,
    *,
    max_turns: int = 18,
) -> tuple[dict, list[dict]]:
    """
    多轮推进直到产出 guides 或达到 max_turns。
    返回 (最后 state, turn_log)
    """
    turn_log: list[dict] = []
    state: dict = {}

    # 先给完整背景 + 强约束要指南
    _, state = post_chat(client, session_id, LONG_CONTEXT + "\n\n" + ASK_GUIDES_STRONG)
    turn_log.append({"turn": 1, "message": "LONG_CONTEXT + ASK_GUIDES_STRONG", "snippet": state_snippet(state)})

    for i in range(2, max_turns + 1):
        if get_guides(state):
            break

        # 如果系统在问问题，用统一长文本回填（并再次强调要指南）
        if wants_more_info(state):
            msg = LONG_CONTEXT + "\n\n" + ASK_GUIDES_STRONG
            label = "AUTO_ANSWER(LONG_CONTEXT)+ASK_GUIDES_STRONG"
        else:
            # 正常推进：继续强约束要指南
            msg = ASK_GUIDES_STRONG
            label = "ASK_GUIDES_STRONG"

        _, state = post_chat(client, session_id, msg)
        turn_log.append({"turn": i, "message": label, "snippet": state_snippet(state)})

    return state, turn_log


def ensure_min_guides(
    client: httpx.Client,
    session_id: str,
    *,
    min_count: int,
    max_turns: int = 18,
) -> tuple[dict, list[dict]]:
    """
    在同一个 session 内，尽力把 guides 数量推进到 >= min_count。
    返回 (最后 state, turn_log)
    """
    turn_log: list[dict] = []
    state: dict = {}

    # 用一个轻量触发：先要 3 条（如果系统此时会走 status/plan/guide 流程，也可被后续轮次推进）
    _, state = post_chat(client, session_id, ASK_GUIDES_STRONG)
    turn_log.append({"turn": 1, "message": "ASK_GUIDES_STRONG", "snippet": state_snippet(state)})

    prev_count = len(get_guides(state))

    for i in range(2, max_turns + 1):
        guides = get_guides(state)
        if len(guides) >= min_count:
            break

        # 如果系统在问问题，用统一长文本回填并继续要更多指南
        if wants_more_info(state):
            msg = LONG_CONTEXT + "\n\n" + ASK_MORE_GUIDES_STRONG
            label = "AUTO_ANSWER(LONG_CONTEXT)+ASK_MORE_GUIDES_STRONG"
        else:
            msg = ASK_MORE_GUIDES_STRONG
            label = "ASK_MORE_GUIDES_STRONG"

        _, state = post_chat(client, session_id, msg)

        curr_count = len(get_guides(state))
        # 若连续多轮没有新增，穿插一次更强的“数量约束”
        if curr_count == prev_count and i % 4 == 0:
            _, state = post_chat(
                client,
                session_id,
                f"{ASK_MORE_GUIDES_STRONG}\n\n强约束：你必须在本轮新增至少 {max(1, min_count - curr_count)} 条行动指南。",
            )
            label = "ASK_MORE_GUIDES_STRONG+COUNT_CONSTRAINT"
            curr_count = len(get_guides(state))

        prev_count = curr_count
        turn_log.append({"turn": i, "message": label, "snippet": state_snippet(state)})

    return state, turn_log


def main():
    session_id = f"case-bind-{int(time.time())}"
    report: dict[str, Any] = {"session_id": session_id, "cases": []}

    with httpx.Client(timeout=TIMEOUT, trust_env=False) as client:
        # Case0
        try:
            r = client.get(f"{BASE}/docs")
            report["cases"].append(CaseResult("Case0:/docs", r.status_code == 200, {"http_status": r.status_code}).__dict__)
        except Exception as e:
            report["cases"].append(CaseResult("Case0:/docs", False, {"error": str(e)}).__dict__)

        # Case1：多轮推进到产出 guides
        state, turns = advance_until_guides(client, session_id)
        guides = get_guides(state)
        guide_id = None
        if guides and isinstance(guides[0], dict):
            guide_id = str(guides[0].get("id") or "") or None

        report["cases"].append(
            CaseResult(
                "Case1:产出>=1条ActionGuide并拿到guide_id",
                bool(guide_id),
                {
                    "guide_id": guide_id,
                    "turns": turns,
                    "final_state_snippet": state_snippet(state),
                },
            ).__dict__
        )

        if not guide_id:
            # 无法继续：输出报告并退出
            print(json.dumps(report, ensure_ascii=False, indent=2))
            return

        # Case2：绑定到当前活跃任务
        _, state2 = post_chat(
            client,
            session_id,
            f"请调用工具 bind_action_guide_detail(guide_id='{guide_id}') 绑定这条行动指南，并继续给我下一步建议。",
        )
        active2 = get_active_task(get_tasks(state2)) or {}
        bound2 = active2.get("bound_action_guides") or []
        bound_ids2 = [bg.get("guide_id") for bg in bound2 if isinstance(bg, dict)]
        report["cases"].append(
            CaseResult(
                "Case2:绑定guide_id到active task",
                guide_id in bound_ids2,
                {"state_snippet": state_snippet(state2)},
            ).__dict__
        )

        # Case3：重复绑定去重覆盖（数量仍为1）
        _, state3 = post_chat(
            client,
            session_id,
            f"再次调用 bind_action_guide_detail(guide_id='{guide_id}') 刷新快照",
        )
        active3 = get_active_task(get_tasks(state3)) or {}
        bound3 = active3.get("bound_action_guides") or []
        same3 = [bg for bg in bound3 if isinstance(bg, dict) and bg.get("guide_id") == guide_id]
        report["cases"].append(
            CaseResult(
                "Case3:重复绑定同guide_id去重覆盖",
                len(same3) == 1,
                {"state_snippet": state_snippet(state3)},
            ).__dict__
        )

        # Case4：任务隔离（创建 taskB_case 并设活跃）
        _, state4 = post_chat(
            client,
            session_id,
            "请调用 create_task(task_id='taskB_case', summary='测试任务隔离') 并设为活跃。",
        )
        tasks4 = get_tasks(state4)
        active4 = get_active_task(tasks4) or {}
        old_task = next((t for t in tasks4 if isinstance(t, dict) and t.get("task_id") != active4.get("task_id") and (t.get("bound_action_guides") or [])), None)
        ok4 = (
            active4.get("task_id") == "taskB_case"
            and (active4.get("bound_action_guides") == [] or active4.get("bound_action_guides") is None)
            and (old_task is not None)
        )
        report["cases"].append(
            CaseResult(
                "Case4:切任务隔离",
                ok4,
                {"state_snippet": state_snippet(state4), "old_task_id_with_bound": (old_task or {}).get("task_id")},
            ).__dict__
        )

        # Case5：K=3 FIFO（尽力：需要至少4条 guide_id）
        # 先尽力把 guides 推进到 >=4（因为 FIFO 验证需要 4 个不同 guide_id）
        state5, turns5 = ensure_min_guides(client, session_id, min_count=4, max_turns=18)
        guides5 = get_guides(state5)
        gids: list[str] = []
        for g in guides5:
            if isinstance(g, dict) and g.get("id"):
                gid = str(g.get("id"))
                if gid and gid not in gids:
                    gids.append(gid)
            if len(gids) >= 4:
                break

        if len(gids) < 4:
            report["cases"].append(
                CaseResult(
                    "Case5:K=3 FIFO 淘汰最早绑定",
                    False,
                    {
                        "blocked": True,
                        "reason": f"layer2_memory.all_action_guides < 4（当前={len(gids)}）",
                        "turns": turns5,
                        "state_snippet": state_snippet(state5),
                    },
                ).__dict__
            )
            print(json.dumps(report, ensure_ascii=False, indent=2))
            return

        # 依次绑定 4 条到当前活跃任务，预期淘汰第 1 条
        for gid in gids[:4]:
            _, state5 = post_chat(client, session_id, f"你必须调用 bind_action_guide_detail(guide_id='{gid}') 绑定到当前活跃任务。")

        active5 = get_active_task(get_tasks(state5)) or {}
        bound5 = active5.get("bound_action_guides") or []
        bound_ids5 = [bg.get("guide_id") for bg in bound5 if isinstance(bg, dict)]
        ok5 = (len(bound_ids5) == 3 and gids[0] not in bound_ids5 and bound_ids5 == gids[1:4])
        report["cases"].append(
            CaseResult(
                "Case5:K=3 FIFO 淘汰最早绑定",
                ok5,
                {"bound_ids": bound_ids5, "expected_bound_ids": gids[1:4], "state_snippet": state_snippet(state5)},
            ).__dict__
        )

    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()

