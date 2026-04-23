"""
Onboarding v2 · 前端 JSON 导出脚本

功能:
1. 把 `question_bank.py` 和 `hooks.py` 里的常量序列化成一个
   前端直接 fetch 的 JSON 文件:`question_bank.frontend.json`。
2. 导出是**确定性**的(固定 key 顺序、使用 ensure_ascii=False),
   CI 可以跑它对比输出字节是否与仓库里的 JSON 一致,以此保证
   .py 与 .json 永远同步。

用法:
    cd agent_impl/onboarding_v2
    python export_frontend_json.py

如果 JSON 需要更新,就提交 `question_bank.frontend.json` 的 diff
到 git。

注意:
- 本脚本**只读** question_bank.py / hooks.py,不读其他文件
- 输出文件里保留所有字段(包括 rewrite_mapping),前端如果想只用一部分
  可以自己在 fetch 后裁剪,但文件本身是全量
"""

from __future__ import annotations

import json
from pathlib import Path

from hooks import HOOKS
from question_bank import QUESTION_BANK

OUTPUT = Path(__file__).resolve().parent / "question_bank.frontend.json"


def build_payload() -> dict:
    """组装前端 JSON 的完整结构。"""

    return {
        "schema_version": 1,
        "question_bank": QUESTION_BANK,
        "hooks": HOOKS,
    }


def serialize(payload: dict) -> str:
    """把 payload 序列化成确定性的 JSON 字符串。

    - `ensure_ascii=False`:保留中文可读
    - `indent=2`:可读的缩进
    - `sort_keys=False`:按写入顺序(保留题号 A1/A2/... 的顺序)
    - 末尾加换行:文件末尾留一个 newline,符合 Unix 规范
    """

    return json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=False) + "\n"


def main() -> None:
    payload = build_payload()
    text = serialize(payload)
    OUTPUT.write_text(text, encoding="utf-8")
    print(f"exported {OUTPUT.relative_to(Path(__file__).resolve().parent.parent.parent)} "
          f"({len(text):,} bytes)")


if __name__ == "__main__":
    main()
