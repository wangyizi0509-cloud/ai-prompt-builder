#!/usr/bin/env python3
"""Onboarding Opening Hook 策略真 LLM 基准测试。

用法：
  cd agent_impl
  python3 scripts/benchmark_hook_strategy.py                # 跑全部 case
  python3 scripts/benchmark_hook_strategy.py --case case_01 # 只跑指定 case
  python3 scripts/benchmark_hook_strategy.py --out path.json # 指定输出路径

目的：
  用真实 LLM 验证 `onboarding_v2.nodes.analyze.run_analyze` 的 FirstHook 输出饱满度。
  不走 HTTP（免登录、免启服务），直接 import 跑 async 函数。

输入：
  5 个精选 case（见 CASES 常量）。每个 case 包含 free_text + ocr_texts（image_urls 留空
  以保证 DeepSeek/OpenAI 纯文本 provider 也能跑通；若日后要验证 vision，把 image_urls
  填进去再切 LLM_PROVIDER=doubao）。

输出：
  控制台打印每个 case 的 FirstHook 全文 + 字段长度统计。
  同时写 JSON 到 `output/hook_benchmark_<ts>.jsonl`（或 --out 指定路径），方便
  粘贴到迭代日志 hook_strategy_iteration.md。
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
import time
from pathlib import Path

# ---- 路径准备（允许从 agent_impl/ 下直接 `python3 scripts/xxx.py`） ----
HERE = Path(__file__).resolve()
AGENT_IMPL_ROOT = HERE.parent.parent  # agent_impl/
if str(AGENT_IMPL_ROOT) not in sys.path:
    sys.path.insert(0, str(AGENT_IMPL_ROOT))

# 加载 .env
try:
    from dotenv import load_dotenv

    # 仓库根目录的 .env
    load_dotenv(AGENT_IMPL_ROOT.parent / ".env")
    load_dotenv(AGENT_IMPL_ROOT / ".env", override=False)
except Exception:  # noqa: BLE001
    pass

# 默认关闭 LangSmith 追踪（基准测试不需要上报）。
os.environ.setdefault("LANGSMITH_TRACING", "false")
os.environ.setdefault("LANGCHAIN_TRACING_V2", "false")
# 拉长 analyze 超时（结构化输出比单句输出慢不少）。
os.environ.setdefault("ONBOARDING_ANALYZE_TIMEOUT", "150")

from onboarding_v2.nodes.analyze import run_analyze  # noqa: E402
from onboarding_v2.schemas import AnalyzeRequest  # noqa: E402


# ============================================================
# 评估集：5 个精心挑选的 case（覆盖不同信息密度 + 情感类型）
# ============================================================

CASES: list[dict[str, object]] = [
    # --- Case 01：原版评估集（排球 + 圣诞帽 + 聊崩，信息最密） ---
    {
        "id": "case_01_volleyball_christmas_hat",
        "title": "排球认识 + 圣诞帽玩笑聊崩",
        "free_text": (
            "我和他是打排球认识的 最开始我没和他一起打，后来他自己来找我打，然后我俩就两个人单打 "
            "最开始他扣球不扣我，要不让别人扣我，但是刚开始打排球的人他都扣 "
            "最开始打完了，他自己很快就走了，现在除了教我动作以外，都会在我周围，不近不远的跟着 "
            "因为我们这里是东北，所以晚上打球的时候就已经零下了，我说我冷，他就要把手套给我 "
            "我俩打球的时候啥都聊，处对象啊，学习啊，这些都聊 "
            "我俩都是不处对象那种人，所以我会经常拿他和帝总（也是男生）处对象开玩笑 "
            "前天他突然和我说他想处对象，不是和帝总的那种 "
            "今天我给他做了一个圣诞帽的头像，我俩聊了挺多的，前面都挺开心的，但最后好像聊崩了，还有希望吗？"
        ),
        "ocr_texts": [
            (
                "| 发送者 | 内容 | 时间戳 | 文本序号 |\n"
                "| --- | --- | --- | --- |\n"
                "| 用户 | 圣诞帽你真的不戴吗😲 | - | 1 |\n"
                "| crush | 看看 | - | 2 |\n"
                "| 用户 | 行，你傲娇 | - | 3 |\n"
                "| crush | 一会俗晚宁戴个套 | - | 4 |\n"
                "| 用户 | 啥玩意 | - | 5 |\n"
                "| 用户 | 说啥呢 | - | 6 |\n"
                "| crush | 头套吗？ | - | 7 |\n"
                "| 用户 | 哦 | - | 8 |\n"
                "| crush | ？ | - | 9 |\n"
                "| crush | 想啥呢？ | 17:53 | 10 |\n"
                "| 用户 | 我还以为你前天说相处对象，今天就有了呢 | 17:53 | 11 |\n"
                "| crush | … | - | 12 |\n"
                "| crush | 6 | - | 13 |\n"
                "| 用户 | 低调低调 | - | 14 |\n"
                "| crush | 你怕不是看多了 | - | 15 |\n"
                "| 用户 | 你之前不说你脑子里都是打码的嘛 | - | 16 |\n"
                "| crush | …… | - | 17 |\n"
                "| crush | 打码的是（图片） | - | 18 |\n"
                "| 用户 | 你不是说相处对象，不是机帝总的吗 | - | 19 |\n"
                "| 用户 | 你咋这样呢 | - | 20 |\n"
                "| crush | 拒绝回答 | - | 21 |\n"
                "| 用户 | 好好好 | - | 22 |\n"
                "| crush | 到此为止了 | - | 23 |\n"
                "| 用户 | 嗯 | - | 24 |\n"
                "| 用户 | 不堆了不堆了 | - | 25 |\n"
            )
        ],
        "image_urls": [],
    },
    # --- Case 02：同事场景 + 已表白被委婉拒绝 ---
    {
        "id": "case_02_coworker_soft_reject",
        "title": "同事 6 个月已表白被委婉拒绝",
        "free_text": (
            "我喜欢上了公司一个女同事，我们在一个部门，认识半年多。"
            "之前一起出差过两次，聊得还挺好的，她会跟我分享她家里的事，也会问我周末干嘛。"
            "上个月我发消息跟她表白了，她回复「你是个很好的人，但我现在不想谈恋爱」。"
            "表白之后她回复明显变慢了，以前秒回的，现在经常半天不回。"
            "但是公司里见到还是会打招呼，上周还叫我一起吃了午饭。"
            "我现在不知道她是真的不想谈恋爱，还是在委婉拒绝我。我该继续还是放下？"
        ),
        "ocr_texts": [
            (
                "| 发送者 | 内容 | 时间戳 |\n"
                "| --- | --- | --- |\n"
                "| 用户 | 在吗，想跟你说件事 | 22:03 |\n"
                "| 用户 | 其实跟你出差那两次我就挺喜欢你的 | 22:04 |\n"
                "| 用户 | 你愿意试着跟我处一下吗 | 22:04 |\n"
                "| crush | ... | 22:47 |\n"
                "| crush | 谢谢你跟我说 | 22:48 |\n"
                "| crush | 你是个很好的人 | 22:48 |\n"
                "| crush | 但我现在不想谈恋爱 | 22:48 |\n"
                "| crush | 我们还是朋友可以吗 | 22:49 |\n"
                "| 用户 | 好的 没事的 | 22:50 |\n"
                "| crush | 🙏 | 22:51 |\n"
            )
        ],
        "image_urls": [],
    },
    # --- Case 03：网恋 + 已读不回（信号清晰 但情感不同） ---
    {
        "id": "case_03_online_ghosting",
        "title": "网上认识 3 个月，突然已读不回",
        "free_text": (
            "我和她是在 App 上认识的，刷到彼此互相喜欢就聊起来了。聊了大概三个月，每天都聊。"
            "她主动说要跟我视频，我们视频过两次，我觉得感觉还不错。"
            "上周开始她回复明显变慢，从秒回变成几小时一回，再后来就是一天一回。"
            "前天开始她不回我消息了，已读不回。我发了两次「在吗」「怎么了」都没回。"
            "她朋友圈还在更新，看得见最近有发出去玩的照片。我不知道我哪里做错了。"
        ),
        "ocr_texts": [
            (
                "| 发送者 | 内容 | 时间戳 |\n"
                "| --- | --- | --- |\n"
                "| 用户 | 在干嘛 | 周一 19:00 |\n"
                "| crush | 刚下班 好累 | 周一 22:10 |\n"
                "| 用户 | 多喝热水 | 周一 22:11 |\n"
                "| 用户 | 周末想你了 要不要视频 | 周三 20:00 |\n"
                "| crush | 这两天有点忙 改天吧 | 周四 11:30 |\n"
                "| 用户 | 好 你忙 | 周四 11:31 |\n"
                "| 用户 | 在吗 | 周六 10:00 |\n"
                "| 用户 | 怎么了 | 周日 21:00 |\n"
                "| crush | （已读不回） | - |\n"
            )
        ],
        "image_urls": [],
    },
    # --- Case 04：信息密度低（纯文字 < 80 字，无截图） ---
    {
        "id": "case_04_low_density",
        "title": "低信息密度 · 几句话描述 + 无截图",
        "free_text": (
            "我喜欢一个学姐 比我大一届 平时在社团活动碰到过几次 但我们不太熟 "
            "上次活动结束她主动加我微信 问我有没有空一起吃饭 我不知道这算不算有好感。"
        ),
        "ocr_texts": [],
        "image_urls": [],
    },
    # --- Case 05：朋友圈 + 冷暴力（截然不同的情绪场景） ---
    {
        "id": "case_05_silent_treatment",
        "title": "处了半年的男朋友 突然冷暴力",
        "free_text": (
            "我和我男朋友在一起 6 个月了，最近两周他开始冷暴力我。"
            "上上周我们因为一件小事吵架，我说话是重了点但也不算过分。"
            "从那之后他就开始变得奇怪，消息从秒回变成不回，我问他怎么了，他就说『没怎么』。"
            "我们本来这周末要一起去他同学的婚礼，他昨天跟我说让我别去了，他自己去就行。"
            "我翻他朋友圈，他还在正常发和朋友的合照，就是屏蔽了我。我不知道是不是要分手了。"
        ),
        "ocr_texts": [
            (
                "| 发送者 | 内容 | 时间戳 |\n"
                "| --- | --- | --- |\n"
                "| 用户 | 宝 在吗 | 昨晚 20:00 |\n"
                "| 用户 | 周末婚礼我几点到 | 昨晚 20:01 |\n"
                "| crush | 你别去了 | 今早 09:42 |\n"
                "| crush | 我自己去就行 | 今早 09:42 |\n"
                "| 用户 | 为啥啊 | 今早 09:43 |\n"
                "| 用户 | 是不是还在生气 | 今早 09:43 |\n"
                "| crush | 没 | 今早 10:05 |\n"
                "| crush | 就是我自己去方便 | 今早 10:05 |\n"
                "| 用户 | 宝 我们能好好聊聊吗 | 今早 10:06 |\n"
                "| crush | （已读不回） | - |\n"
            )
        ],
        "image_urls": [],
    },
]


# ============================================================
# 跑测逻辑
# ============================================================


def _count_chars(text: str) -> int:
    """数中文字符 + 英文单词（粗略字数）。"""
    return len(text) if text else 0


async def _run_one_case(case: dict) -> dict:
    """跑一个 case，返回 {case, result, stats, duration}."""
    req = AnalyzeRequest(
        session_id=f"benchmark-{case['id']}",
        free_text=str(case["free_text"]),
        image_urls=list(case.get("image_urls") or []),
        ocr_texts=list(case.get("ocr_texts") or []),
    )
    t0 = time.time()
    try:
        resp = await run_analyze(req)
        ok = True
        err = None
        resp_dump = resp.model_dump()
    except Exception as exc:  # noqa: BLE001
        ok = False
        err = repr(exc)
        resp_dump = None
    duration_s = round(time.time() - t0, 2)

    stats: dict = {"duration_s": duration_s, "ok": ok}
    if ok and resp_dump:
        fh = resp_dump["first_hook"]
        if isinstance(fh, dict):
            stats.update(
                {
                    "title_len": _count_chars(fh.get("title", "")),
                    "body_len": _count_chars(fh.get("body", "")),
                    "highlights_n": len(fh.get("highlights") or []),
                    "evidences_n": len(fh.get("evidences") or []),
                    "evidence_lens": [
                        _count_chars(e) for e in (fh.get("evidences") or [])
                    ],
                    "cta_len": _count_chars(fh.get("call_to_action", "")),
                    "total_len": (
                        _count_chars(fh.get("title", ""))
                        + _count_chars(fh.get("body", ""))
                        + sum(_count_chars(e) for e in (fh.get("evidences") or []))
                        + _count_chars(fh.get("call_to_action", ""))
                    ),
                }
            )
        else:
            # 降级为旧 str 形式（理论上不会出现，说明契约没真的改）
            stats["legacy_str_hook"] = True
    if err:
        stats["error"] = err

    return {
        "case_id": case["id"],
        "case_title": case["title"],
        "response": resp_dump,
        "stats": stats,
    }


def _print_case_result(entry: dict) -> None:
    print()
    print("=" * 80)
    print(f"[{entry['case_id']}] {entry['case_title']}")
    print(f"  duration: {entry['stats'].get('duration_s')}s  ok: {entry['stats'].get('ok')}")
    if entry["stats"].get("error"):
        print(f"  ERROR: {entry['stats']['error']}")
        return

    resp = entry.get("response") or {}
    fh = resp.get("first_hook")
    if not isinstance(fh, dict):
        print("  [WARN] first_hook 不是 object:", fh)
        return

    print()
    print(f"  tag:       [{fh.get('verdict_tag')}]  color: {fh.get('verdict_color')}")
    print(f"  title  ({entry['stats'].get('title_len')}字):")
    print(f"    {fh.get('title')}")
    print(f"  body   ({entry['stats'].get('body_len')}字):")
    print(f"    {fh.get('body')}")
    print(f"  highlights ({entry['stats'].get('highlights_n')}个):")
    for h in fh.get("highlights") or []:
        print(f"    · {h}")
    print(f"  evidences  ({entry['stats'].get('evidences_n')}条，长度 {entry['stats'].get('evidence_lens')}):")
    for i, e in enumerate(fh.get("evidences") or [], 1):
        print(f"    #{i}  {e}")
    print(f"  call_to_action ({entry['stats'].get('cta_len')}字):")
    print(f"    {fh.get('call_to_action')}")
    print(f"  >> 总字数: {entry['stats'].get('total_len')}")

    # 打印 skip_rules 摘要
    skip_rules = resp.get("skip_rules") or {}
    hits = [k for k, v in skip_rules.items() if v.get("skip")]
    preselects = {
        k: v.get("preselect")
        for k, v in skip_rules.items()
        if v.get("preselect")
    }
    print(f"  skip_rules: skipped={hits}; preselects={preselects}")


async def _main(selected_ids: list[str] | None, out_path: Path) -> None:
    cases = CASES if not selected_ids else [c for c in CASES if c["id"] in selected_ids]
    if not cases:
        print(f"[ERROR] 没有匹配的 case: {selected_ids}")
        sys.exit(1)

    provider = os.getenv("LLM_PROVIDER", "(unset)")
    print(f"[benchmark] LLM_PROVIDER={provider}; 跑 {len(cases)} 个 case …")

    # 串行跑（模拟线上真实调用节奏；并行会触发 BigModel 的并发降级，导致空 tool_calls）
    all_entries: list[dict] = []
    for case in cases:
        entry = await _run_one_case(case)
        _print_case_result(entry)
        all_entries.append(entry)

    # 写 JSONL
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with out_path.open("w", encoding="utf-8") as f:
        for entry in all_entries:
            f.write(json.dumps(entry, ensure_ascii=False) + "\n")
    print()
    print(f"[benchmark] 结果写入: {out_path}")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--case",
        action="append",
        default=None,
        help="指定 case id（可多次），默认跑全部。例如 --case case_01_volleyball_christmas_hat",
    )
    parser.add_argument(
        "--out",
        default=None,
        help="输出 JSONL 路径，默认 output/hook_benchmark_<ts>.jsonl",
    )
    args = parser.parse_args()

    out_path = (
        Path(args.out).expanduser().resolve()
        if args.out
        else AGENT_IMPL_ROOT.parent / "output" / f"hook_benchmark_{int(time.time())}.jsonl"
    )

    asyncio.run(_main(args.case, out_path))


if __name__ == "__main__":
    main()
