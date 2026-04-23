#!/usr/bin/env python3
"""Real API multi-turn regression runner for Crushe.

Key features:
- reads config from docs/测试评估文档.md (Markdown + YAML block)
- runs state-driven API flow: onboarding -> main -> status -> plan -> guide -> feedback
- optional UI smoke probe via scripts/e2e_ui_smoke_probe.py
- writes Markdown + JSON reports under artifacts/e2e/real_eval
- retries full scenario once when configured
"""

from __future__ import annotations

import argparse
import copy
import json
import mimetypes
import re
import subprocess
import sys
import time
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

import requests
import yaml


PROJECT_ROOT = Path(__file__).resolve().parents[1]
REPORT_DIR = PROJECT_ROOT / "artifacts" / "e2e" / "real_eval"
DEFAULT_BASE_URL = "http://127.0.0.1:8000"


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def utc_stamp() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")


def _first_yaml_block(markdown_text: str) -> str:
    fence = re.search(r"```yaml\s*(.*?)```", markdown_text, flags=re.S | re.I)
    if fence:
        return fence.group(1).strip()

    frontmatter = re.match(r"^---\s*\n(.*?)\n---\s*", markdown_text, flags=re.S)
    if frontmatter:
        return frontmatter.group(1).strip()

    raise ValueError("No YAML block found in evaluation document.")


def load_eval_doc(path: Path) -> dict[str, Any]:
    raw = path.read_text(encoding="utf-8")
    yaml_text = _first_yaml_block(raw)
    parsed = yaml.safe_load(yaml_text) or {}
    if not isinstance(parsed, dict):
        raise ValueError("YAML root must be a mapping object.")
    return parsed


def _as_str(value: Any, default: str = "") -> str:
    if isinstance(value, str):
        return value
    if value is None:
        return default
    return str(value)


def _as_int(value: Any, default: int) -> int:
    try:
        return int(value)
    except Exception:
        return default


def _as_bool(value: Any, default: bool) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        lowered = value.strip().lower()
        if lowered in {"1", "true", "yes", "y", "on"}:
            return True
        if lowered in {"0", "false", "no", "n", "off"}:
            return False
    return default


def _slugify_username(value: str) -> str:
    cleaned = re.sub(r"[^a-zA-Z0-9_]+", "_", value or "").strip("_").lower()
    return cleaned or "real_eval_user"


def _normalize_image_items(value: Any) -> list[dict[str, Any]]:
    if not isinstance(value, list):
        return []

    items: list[dict[str, Any]] = []
    for item in value:
        if not isinstance(item, dict):
            continue
        path = _as_str(item.get("path"), "").strip()
        if not path:
            continue
        items.append(
            {
                "path": path,
                "screenshot_type": _as_str(item.get("screenshot_type"), "").strip(),
                "transcript": _as_str(item.get("transcript"), "").strip(),
                "note": _as_str(item.get("note"), "").strip(),
            }
        )
    return items


def normalize_config(raw: dict[str, Any]) -> dict[str, Any]:
    meta = raw.get("meta") if isinstance(raw.get("meta"), dict) else {}
    persona = raw.get("persona") if isinstance(raw.get("persona"), dict) else {}
    flow = raw.get("flow") if isinstance(raw.get("flow"), dict) else {}
    feedback = raw.get("feedback") if isinstance(raw.get("feedback"), dict) else {}
    ui_smoke = raw.get("ui_smoke") if isinstance(raw.get("ui_smoke"), dict) else {}
    image_upload = raw.get("image_upload") if isinstance(raw.get("image_upload"), dict) else {}
    limits = raw.get("limits") if isinstance(raw.get("limits"), dict) else {}

    case_id = _as_str(meta.get("case_id"), "real_api_regression_case").strip() or "real_api_regression_case"

    cfg = {
        "meta": {
            "case_id": case_id,
            "base_url": _as_str(meta.get("base_url"), DEFAULT_BASE_URL).strip() or DEFAULT_BASE_URL,
            "boot_mode": _as_str(meta.get("boot_mode"), "check").strip().lower() or "check",
            "start_cmd": _as_str(meta.get("start_cmd"), "").strip(),
            "timeout_seconds": _as_int(meta.get("timeout_seconds"), 180),
        },
        "persona": {
            "user_info": _as_str(persona.get("user_info"), ""),
            "crush_info": _as_str(persona.get("crush_info"), ""),
            "relationship_context": _as_str(persona.get("relationship_context"), ""),
            "goal": _as_str(persona.get("goal"), ""),
        },
        "flow": {
            "onboarding_seed": _as_str(flow.get("onboarding_seed"), ""),
            "main_prompt": _as_str(flow.get("main_prompt"), ""),
            "status_prompt": _as_str(flow.get("status_prompt"), ""),
            "plan_prompt": _as_str(flow.get("plan_prompt"), ""),
            "guide_prompt": _as_str(flow.get("guide_prompt"), ""),
        },
        "feedback": {
            "completion_status": _as_str(feedback.get("completion_status"), "partial"),
            "completion_detail": _as_str(feedback.get("completion_detail"), ""),
            "followup_answer": _as_str(feedback.get("followup_answer"), "我会继续补充执行细节。"),
        },
        "ui_smoke": {
            "enabled": _as_bool(ui_smoke.get("enabled"), False),
            "email": _as_str(ui_smoke.get("email"), "test01@example.com"),
            "password": _as_str(ui_smoke.get("password"), "password123"),
            "smoke_message": _as_str(
                ui_smoke.get("smoke_message"),
                "我想咨询一下感情推进问题，给我一个简短建议。",
            ),
            "timeout_seconds": _as_int(ui_smoke.get("timeout_seconds"), 60),
        },
        "image_upload": {
            "enabled": _as_bool(image_upload.get("enabled"), False),
            "detect_type": _as_bool(image_upload.get("detect_type"), True),
            "default_screenshot_type": _as_str(
                image_upload.get("default_screenshot_type"),
                "private_chat_screenshot",
            ).strip()
            or "private_chat_screenshot",
            "context": _as_str(image_upload.get("context"), "").strip(),
            "images": _normalize_image_items(image_upload.get("images")),
        },
        "limits": {
            "max_turns_per_stage": max(1, _as_int(limits.get("max_turns_per_stage"), 8)),
            "max_total_turns": max(6, _as_int(limits.get("max_total_turns"), 48)),
            "retry_once": _as_bool(limits.get("retry_once"), True),
            "stall_escalation_turns": max(1, _as_int(limits.get("stall_escalation_turns"), 2)),
        },
    }

    if cfg["meta"]["boot_mode"] not in {"check", "auto"}:
        cfg["meta"]["boot_mode"] = "check"

    return cfg


def mask_config_for_report(cfg: dict[str, Any]) -> dict[str, Any]:
    out = copy.deepcopy(cfg)
    if isinstance(out.get("ui_smoke"), dict):
        if out["ui_smoke"].get("password"):
            out["ui_smoke"]["password"] = "***"
    return out


def check_health(base_url: str, timeout_seconds: int = 6) -> tuple[bool, str]:
    base = base_url.rstrip("/")
    candidates = [
        (base + "/api/health", "api_health"),
        (base + "/health", "health"),
        (base + "/openapi.json", "openapi"),
    ]
    last_reason = "unknown"
    for url, label in candidates:
        try:
            resp = requests.get(url, timeout=timeout_seconds, allow_redirects=False)
            if resp.status_code == 200:
                return True, f"healthy:{label}"
            last_reason = f"{label}_status_{resp.status_code}"
        except Exception as exc:
            last_reason = f"{label}_error:{exc}"
    return False, last_reason


def wait_for_health(base_url: str, timeout_seconds: int, poll_seconds: float = 2.0) -> tuple[bool, str]:
    end = time.time() + timeout_seconds
    last_reason = "unknown"
    while time.time() < end:
        ok, reason = check_health(base_url, timeout_seconds=5)
        if ok:
            return True, "healthy"
        last_reason = reason
        time.sleep(poll_seconds)
    return False, last_reason


def ensure_authenticated_session(
    *,
    cfg: dict[str, Any],
    attempt_tag: str,
    timeout_seconds: int,
) -> tuple[requests.Session, dict[str, Any]]:
    base_url = cfg["meta"]["base_url"].rstrip("/")
    ui_cfg = cfg.get("ui_smoke") if isinstance(cfg.get("ui_smoke"), dict) else {}
    base_email = _as_str(ui_cfg.get("email"), "").strip()
    password = _as_str(ui_cfg.get("password"), "password123").strip() or "password123"
    if base_email:
        local, _, domain = base_email.partition("@")
        email = f"{local}+{attempt_tag}@{domain or 'example.com'}"
        username = _slugify_username(f"{local}_{attempt_tag}")
    else:
        email = f"real_eval_{attempt_tag}@example.com"
        username = _slugify_username(f"real_eval_{attempt_tag}")

    session = requests.Session()
    auth_info: dict[str, Any] = {
        "email": email,
        "username": username,
        "used_register": False,
        "used_login": False,
    }

    login_url = f"{base_url}/api/auth/login"
    register_url = f"{base_url}/api/auth/register"

    login_resp = session.post(
        login_url,
        json={"email": email, "password": password},
        timeout=timeout_seconds,
    )

    if login_resp.status_code == 401:
        register_resp = session.post(
            register_url,
            json={"email": email, "password": password, "username": username},
            timeout=timeout_seconds,
        )
        if register_resp.status_code >= 400:
            detail = register_resp.text[:300]
            raise RuntimeError(
                f"auth_bootstrap_failed: login=401 register={register_resp.status_code} detail={detail}"
            )
        register_payload = register_resp.json() if register_resp.content else {}
        token = _as_str(register_payload.get("token"), "").strip()
        if token:
            session.headers.update({"Authorization": f"Bearer {token}"})
        auth_info["used_register"] = True
        return session, auth_info

    login_resp.raise_for_status()
    login_payload = login_resp.json() if login_resp.content else {}
    token = _as_str(login_payload.get("token"), "").strip()
    if token:
        session.headers.update({"Authorization": f"Bearer {token}"})
    auth_info["used_login"] = True
    return session, auth_info


def ensure_service_ready(
    *,
    cfg: dict[str, Any],
    boot_mode_override: str | None,
    start_cmd_override: str | None,
    report_run_dir: Path,
) -> dict[str, Any]:
    meta = cfg["meta"]
    base_url = meta["base_url"]
    timeout_seconds = meta["timeout_seconds"]
    boot_mode = (boot_mode_override or meta["boot_mode"]).strip().lower()
    start_cmd = (start_cmd_override if start_cmd_override is not None else meta["start_cmd"]).strip()

    ok, reason = check_health(base_url, timeout_seconds=5)
    details: dict[str, Any] = {
        "boot_mode": boot_mode,
        "base_url": base_url,
        "start_cmd": start_cmd,
        "health_before": {"ok": ok, "reason": reason},
        "started_by_runner": False,
        "service_log": None,
        "service_start_error": None,
    }

    if ok:
        return details

    if boot_mode == "check":
        raise RuntimeError(f"Service unhealthy in check mode: {reason}")

    if not start_cmd:
        raise RuntimeError("boot_mode=auto but start_cmd is empty")

    log_path = report_run_dir / "service_start.log"
    log_file = log_path.open("w", encoding="utf-8")

    try:
        proc = subprocess.Popen(
            start_cmd,
            cwd=str(PROJECT_ROOT),
            shell=True,
            stdout=log_file,
            stderr=subprocess.STDOUT,
            start_new_session=True,
        )
    except Exception as exc:
        log_file.close()
        raise RuntimeError(f"Failed to execute start_cmd: {exc}") from exc

    details["started_by_runner"] = True
    details["service_log"] = str(log_path)
    details["service_pid"] = proc.pid
    details["_process"] = proc
    details["_log_handle"] = log_file

    ok_after, reason_after = wait_for_health(base_url, timeout_seconds=timeout_seconds)
    details["health_after"] = {"ok": ok_after, "reason": reason_after}

    if not ok_after:
        try:
            proc.terminate()
            proc.wait(timeout=8)
        except Exception:
            try:
                proc.kill()
            except Exception:
                pass
        try:
            log_file.close()
        except Exception:
            pass
        raise RuntimeError(f"Service failed to become healthy after start_cmd: {reason_after}")

    return details


def cleanup_service_boot(service_info: dict[str, Any]) -> None:
    proc = service_info.get("_process")
    log_handle = service_info.get("_log_handle")

    if proc is not None and service_info.get("started_by_runner"):
        try:
            proc.terminate()
            proc.wait(timeout=8)
        except Exception:
            try:
                proc.kill()
            except Exception:
                pass

    if log_handle is not None:
        try:
            log_handle.close()
        except Exception:
            pass


def _safe_get(d: dict[str, Any], keys: list[str], default: Any = None) -> Any:
    cur: Any = d
    for k in keys:
        if not isinstance(cur, dict):
            return default
        cur = cur.get(k)
    return cur if cur is not None else default


def get_guides(state: dict[str, Any]) -> list[dict[str, Any]]:
    layer2_guides = _safe_get(state, ["layer2_memory", "action_guides"], [])
    if isinstance(layer2_guides, list):
        return [g for g in layer2_guides if isinstance(g, dict)]
    top_guides = state.get("action_guides")
    if isinstance(top_guides, list):
        return [g for g in top_guides if isinstance(g, dict)]
    return []


def latest_guide_id(state: dict[str, Any]) -> str:
    guides = get_guides(state)
    if not guides:
        return ""
    for item in reversed(guides):
        gid = _as_str(item.get("id"), "").strip()
        if gid:
            return gid
    return ""


def tail_tool_names(state: dict[str, Any], tail: int = 40) -> list[str]:
    names: list[str] = []
    msgs = state.get("messages")
    if not isinstance(msgs, list):
        return names

    for msg in msgs[-tail:]:
        if not isinstance(msg, dict):
            continue

        if msg.get("role") == "tool" or msg.get("type") == "tool":
            nm = _as_str(msg.get("name"), "")
            if nm:
                names.append(nm)

        tool_calls = msg.get("tool_calls")
        if isinstance(tool_calls, list):
            for tc in tool_calls:
                if isinstance(tc, dict) and tc.get("name"):
                    names.append(_as_str(tc["name"], ""))
    return names


def wants_more_info(state: dict[str, Any]) -> bool:
    if state.get("next_action") == "ask_user":
        return True
    if state.get("pending_questions"):
        return True
    if state.get("inquiry_card"):
        return True
    return False


def needs_crushe_guide_completion(state: dict[str, Any]) -> bool:
    if state.get("pending_crushe_guide") is True:
        return True
    pending = state.get("pending_responses")
    if not isinstance(pending, list):
        return False
    for item in pending:
        if not isinstance(item, dict):
            continue
        if item.get("showGuideButton") is True:
            return True
        if _as_str(item.get("messageKey"), "") == "guide_gate":
            return True
        if _as_str(item.get("phase"), "") == "guide_gate":
            return True
    return False


def response_needs_crushe_guide_completion(resp: dict[str, Any], state: dict[str, Any]) -> bool:
    if needs_crushe_guide_completion(state):
        return True
    pending_candidates: list[dict[str, Any]] = []

    resp_pending = resp.get("pending_responses")
    if isinstance(resp_pending, list):
        pending_candidates.extend(item for item in resp_pending if isinstance(item, dict))

    state_pending = state.get("pending_responses")
    if isinstance(state_pending, list):
        pending_candidates.extend(item for item in state_pending if isinstance(item, dict))

    for item in pending_candidates:
        if item.get("showGuideButton") is True:
            return True
        if _as_str(item.get("messageKey"), "") == "guide_gate":
            return True
        if _as_str(item.get("phase"), "") == "guide_gate":
            return True

    response_text = _as_str(resp.get("response"), "")
    return "Crushe使用指南" in response_text and "完成阅读" in response_text


def has_displayable_response(resp: dict[str, Any], state: dict[str, Any]) -> bool:
    if isinstance(resp.get("response"), str) and resp.get("response", "").strip():
        return True

    pending_responses = resp.get("pending_responses")
    if isinstance(pending_responses, list):
        for item in pending_responses:
            if isinstance(item, dict) and _as_str(item.get("content"), "").strip():
                return True

    state_pending = state.get("pending_responses")
    if isinstance(state_pending, list):
        for item in state_pending:
            if isinstance(item, dict) and _as_str(item.get("content"), "").strip():
                return True

    if state.get("inquiry_card"):
        return True

    return False


def has_status_evidence(state: dict[str, Any], tool_names: list[str]) -> bool:
    layer2 = state.get("layer2_memory") if isinstance(state.get("layer2_memory"), dict) else {}
    return bool(
        "delegate_to_status" in tool_names
        or layer2.get("current_status_report")
        or state.get("status_report")
    )


def has_plan_evidence(state: dict[str, Any], tool_names: list[str]) -> bool:
    layer2 = state.get("layer2_memory") if isinstance(state.get("layer2_memory"), dict) else {}
    return bool(
        "delegate_to_plan" in tool_names
        or layer2.get("current_action_plan")
        or state.get("action_plan")
    )


def has_guide_evidence(state: dict[str, Any], tool_names: list[str]) -> bool:
    return bool("delegate_to_guide" in tool_names or get_guides(state))


def has_main_evidence(resp: dict[str, Any], state: dict[str, Any], tool_names: list[str]) -> bool:
    if any(name in tool_names for name in ("delegate_to_status", "delegate_to_plan", "delegate_to_guide")):
        return True
    return has_displayable_response(resp, state)


def build_persona_summary(cfg: dict[str, Any]) -> str:
    p = cfg["persona"]
    lines = [
        "[用户信息]",
        p["user_info"].strip(),
        "",
        "[Crush信息]",
        p["crush_info"].strip(),
        "",
        "[关系背景]",
        p["relationship_context"].strip(),
        "",
        "[目标]",
        p["goal"].strip(),
    ]
    return "\n".join(line for line in lines if line is not None)


def build_onboarding_seed(cfg: dict[str, Any]) -> str:
    seed = cfg["flow"]["onboarding_seed"].strip()
    if seed:
        return seed
    return (
        "我希望你作为恋爱军师帮我推进关系。\n"
        + build_persona_summary(cfg)
        + "\n\n请先完成 onboarding 信息采集流程。"
    )


def build_auto_answer(cfg: dict[str, Any], stage: str, strong: bool = False) -> str:
    summary = build_persona_summary(cfg)
    stage_hint = {
        "onboarding": "请继续 onboarding，直到信息足够进入主流程。",
        "status": "请基于以上信息继续现状分析流程。",
        "plan": "请基于以上信息继续行动规划流程。",
        "guide": "请基于以上信息继续行动指南流程。",
        "feedback": "请基于以上信息继续行动反馈流程。",
        "main": "请基于以上信息继续主流程。",
    }.get(stage, "请继续流程。")

    if strong:
        stage_hint += " 本轮请直接推进，不要停在泛泛提问。"

    return summary + "\n\n" + stage_hint


SCREENSHOT_QUESTION_TYPES = {
    "private_chat_screenshot",
    "group_chat_screenshot",
    "moments_screenshot",
    "other_social_media_screenshot",
    "universal_screenshot_analysis",
}


def _is_screenshot_question(question_type: Any) -> bool:
    return _as_str(question_type, "").strip() in SCREENSHOT_QUESTION_TYPES


def _build_uploaded_image_digest(upload_evidence: list[dict[str, Any]] | None) -> str:
    if not isinstance(upload_evidence, list):
        return ""

    blocks: list[str] = []
    for idx, item in enumerate(upload_evidence, 1):
        if not isinstance(item, dict):
            continue
        text = _as_str(item.get("transcript"), "").strip() or _as_str(item.get("ocr_text_preview"), "").strip()
        if not text:
            continue
        blocks.append(f"第{idx}张截图：\n{text}")
    return "\n\n".join(blocks)


def _guess_free_input_answer(question_text: str, cfg: dict[str, Any], stage: str, uploaded_image_digest: str) -> str:
    normalized = question_text.lower()
    persona = cfg.get("persona") if isinstance(cfg.get("persona"), dict) else {}
    relationship_context = _as_str(persona.get("relationship_context"), "").strip()

    if any(token in normalized for token in ("工作忙", "时间", "精力", "周末", "工作日晚上")):
        return "工作日白天比较忙，但我每周至少能稳定拿出 2 个工作日晚间和半天周末来经营关系；如果值得推进，也能安排 1-2 次线下见面。"

    if any(token in normalized for token in ("预算", "开销", "花费", "消费")):
        return "预算比较灵活，单次约会 300-800 元都能接受。我更在意体验自然、不铺张，也不希望让对方有压力。"

    if any(token in normalized for token in ("没明显进展", "1-2个月", "继续坚持", "调整目标", "怎么想")):
        return "我会先复盘策略并再尝试一轮更明确的推进；如果连续 1-2 个月仍然没有实质反馈，我会尊重现实，逐步降低投入，而不是无限硬追。"

    if any(token in normalized for token in ("聊天记录", "截图", "对话", "原文")) and uploaded_image_digest:
        return uploaded_image_digest

    if any(token in normalized for token in ("关系背景", "认识多久", "目前关系", "你们是什么关系")) and relationship_context:
        return relationship_context

    stage_hint = {
        "onboarding": "我愿意继续补充真实情况，方便你尽快进入正式分析。",
        "main": "请基于这些补充继续主流程判断。",
        "status": "请基于这些补充继续现状分析。",
        "plan": "请基于这些补充继续行动规划。",
        "guide": "请基于这些补充继续行动指南。",
        "feedback": "请基于这些补充继续行动反馈。",
    }.get(stage, "请基于这些补充继续流程。")
    return stage_hint


def build_inquiry_submission(
    *,
    state: dict[str, Any],
    cfg: dict[str, Any],
    stage: str,
    uploaded_image_digest: str = "",
) -> dict[str, Any] | None:
    card = state.get("inquiry_card") if isinstance(state.get("inquiry_card"), dict) else None
    questions = card.get("questions") if isinstance(card, dict) else None
    if not isinstance(questions, list) or not questions:
        return None

    answers: dict[str, Any] = {}
    details: list[dict[str, str]] = []
    backend_parts: list[str] = []

    for idx, raw_question in enumerate(questions, 1):
        if not isinstance(raw_question, dict):
            continue

        question_text = _as_str(
            raw_question.get("question") or raw_question.get("title"),
            f"问题{idx}",
        ).strip() or f"问题{idx}"
        resume_key = _as_str(raw_question.get("id"), "").strip() or f"q{idx}"
        question_type = _as_str(raw_question.get("type"), "").strip()

        if _is_screenshot_question(question_type):
            answer_value = uploaded_image_digest or "已上传聊天截图，请直接结合前文 OCR/转写内容分析。"
            detail_value = "已提供聊天截图转写"
        else:
            answer_value = _guess_free_input_answer(question_text, cfg, stage, uploaded_image_digest)
            detail_value = answer_value

        answers[resume_key] = answer_value
        details.append({"label": question_text, "value": detail_value})
        backend_parts.append(f"{question_text}：{detail_value}")

    if not answers:
        return None

    task_key = _as_str(card.get("taskKey"), "").strip()
    return {
        "message": "\n\n".join(backend_parts) or "已提交问卷",
        "resume_payload": {"answers": answers},
        "inquiry_receipt_payload": {
            "taskKey": task_key,
            "summary": f"已提交问卷（{len(details)}项）",
            "details": details,
        },
    }


ALLOWED_SCREENSHOT_TYPES = {
    "private_chat_screenshot",
    "group_chat_screenshot",
    "moments_screenshot",
    "other_social_media_screenshot",
    "universal_screenshot_analysis",
}


def _guess_mime(path: Path) -> str:
    guessed, _ = mimetypes.guess_type(str(path))
    if guessed:
        return guessed
    return "application/octet-stream"


def _resolve_image_path(raw_path: str, eval_doc_dir: Path) -> Path:
    p = Path(raw_path)
    if p.is_absolute():
        return p
    return (eval_doc_dir / p).resolve()


def _looks_like_placeholder_ocr(text: str) -> bool:
    normalized = (text or "").strip()
    if not normalized:
        return False
    placeholder_markers = (
        "Placeholder chat screenshot",
        "占位符截图",
        "非真实微信聊天截图",
        "非真实聊天截图",
        "生成式占位",
        "Generated for e2e pipeline run",
    )
    return any(marker in normalized for marker in placeholder_markers)


def detect_screenshot_type(
    *,
    base_url: str,
    image_path: Path,
    timeout_seconds: int,
    session: requests.Session | None = None,
) -> str:
    url = base_url.rstrip("/") + "/api/upload/detect-type"
    client = session or requests
    with image_path.open("rb") as fh:
        files = {"file": (image_path.name, fh, _guess_mime(image_path))}
        resp = client.post(url, files=files, timeout=timeout_seconds)
    resp.raise_for_status()
    payload = resp.json() if resp.content else {}
    detected = _as_str(payload.get("screenshot_type"), "").strip()
    if detected in ALLOWED_SCREENSHOT_TYPES:
        return detected
    return "universal_screenshot_analysis"


def upload_screenshot_and_get_ocr(
    *,
    base_url: str,
    session_id: str,
    image_path: Path,
    screenshot_type: str,
    context: str,
    timeout_seconds: int,
    session: requests.Session | None = None,
) -> dict[str, Any]:
    url = base_url.rstrip("/") + "/api/upload/upload-screenshot"
    client = session or requests

    if screenshot_type not in ALLOWED_SCREENSHOT_TYPES:
        screenshot_type = "universal_screenshot_analysis"

    with image_path.open("rb") as fh:
        files = {"file": (image_path.name, fh, _guess_mime(image_path))}
        data = {
            "screenshot_type": screenshot_type,
            "session_id": session_id,
        }
        if context.strip():
            data["context"] = context.strip()
        resp = client.post(url, files=files, data=data, timeout=timeout_seconds)

    resp.raise_for_status()
    payload = resp.json() if resp.content else {}
    if not isinstance(payload, dict):
        raise RuntimeError("upload-screenshot response is not JSON object")
    return payload


def run_image_upload_stage(
    *,
    cfg: dict[str, Any],
    session_id: str,
    eval_doc_dir: Path,
    http_session: requests.Session | None = None,
) -> tuple[StageOutcome, list[dict[str, Any]], list[dict[str, Any]]]:
    image_cfg = cfg.get("image_upload") if isinstance(cfg.get("image_upload"), dict) else {}
    if not image_cfg.get("enabled"):
        return (
            StageOutcome(name="image_upload", passed=True, reason="skipped_disabled", evidence={}),
            [],
            [],
        )

    images = image_cfg.get("images") if isinstance(image_cfg.get("images"), list) else []
    if not images:
        return (
            StageOutcome(
                name="image_upload",
                passed=False,
                reason="enabled_but_no_images_configured",
                evidence={},
            ),
            [],
            [],
        )

    base_url = cfg["meta"]["base_url"]
    timeout_seconds = cfg["meta"]["timeout_seconds"]
    detect_type_enabled = bool(image_cfg.get("detect_type"))
    default_type = _as_str(image_cfg.get("default_screenshot_type"), "private_chat_screenshot")
    context = _as_str(image_cfg.get("context"), "")

    chat_images_payload: list[dict[str, Any]] = []
    upload_evidence: list[dict[str, Any]] = []

    for idx, item in enumerate(images, 1):
        raw_path = _as_str(item.get("path"), "").strip()
        screenshot_type = _as_str(item.get("screenshot_type"), "").strip() or default_type
        transcript = _as_str(item.get("transcript"), "").strip()
        note = _as_str(item.get("note"), "").strip()

        resolved = _resolve_image_path(raw_path, eval_doc_dir=eval_doc_dir)
        if not resolved.exists():
            return (
                StageOutcome(
                    name="image_upload",
                    passed=False,
                    reason=f"image_file_not_found:{resolved}",
                    evidence={"missing_path": str(resolved)},
                ),
                [],
                upload_evidence,
            )

        try:
            detected_type = screenshot_type
            if detect_type_enabled:
                detected_type = detect_screenshot_type(
                    base_url=base_url,
                    image_path=resolved,
                    timeout_seconds=timeout_seconds,
                    session=http_session,
                )

            upload_result = upload_screenshot_and_get_ocr(
                base_url=base_url,
                session_id=session_id,
                image_path=resolved,
                screenshot_type=detected_type,
                context=context,
                timeout_seconds=timeout_seconds,
                session=http_session,
            )

            if not upload_result.get("success"):
                err = _as_str(upload_result.get("error"), "upload_failed_unknown")
                return (
                    StageOutcome(
                        name="image_upload",
                        passed=False,
                        reason=f"upload_failed:{err}",
                        evidence={"failed_image": str(resolved)},
                    ),
                    [],
                    upload_evidence,
                )

            ocr_text = _as_str(upload_result.get("text"), "").strip()
            if transcript and (not ocr_text or _looks_like_placeholder_ocr(ocr_text)):
                # Placeholder eval images can yield non-empty OCR that is useless for relationship analysis.
                # Prefer the curated transcript from the eval doc in those cases.
                ocr_text = transcript
            final_type = _as_str(upload_result.get("screenshot_type"), detected_type) or detected_type

            chat_images_payload.append(
                {
                    "image_url": upload_result.get("image_url"),
                    "ocr_result": ocr_text,
                    "screenshot_type": final_type,
                }
            )

            upload_evidence.append(
                {
                    "index": idx,
                    "path": str(resolved),
                    "configured_screenshot_type": screenshot_type,
                    "detected_screenshot_type": detected_type,
                    "final_screenshot_type": final_type,
                    "ocr_text_len": len(ocr_text),
                    "ocr_text_preview": ocr_text[:240],
                    "note": note,
                    "transcript": transcript,
                    "image_url": upload_result.get("image_url"),
                }
            )

        except Exception as exc:
            return (
                StageOutcome(
                    name="image_upload",
                    passed=False,
                    reason=f"exception:{exc}",
                    evidence={"failed_image": str(resolved)},
                ),
                [],
                upload_evidence,
            )

    return (
        StageOutcome(
            name="image_upload",
            passed=True,
            reason="ok",
            evidence={
                "uploaded_count": len(upload_evidence),
                "images": upload_evidence,
            },
        ),
        chat_images_payload,
        upload_evidence,
    )


def post_chat(
    *,
    base_url: str,
    session_id: str,
    message: str,
    timeout_seconds: int,
    images: list[dict[str, Any]] | None = None,
    feedback_mode: dict[str, Any] | None = None,
    resume_payload: dict[str, Any] | None = None,
    inquiry_receipt_payload: dict[str, Any] | None = None,
    session: requests.Session | None = None,
) -> dict[str, Any]:
    url = base_url.rstrip("/") + "/api/chat"
    client = session or requests
    payload: dict[str, Any] = {"message": message, "session_id": session_id}
    if images is not None:
        payload["images"] = images
    if feedback_mode is not None:
        payload["feedback_mode"] = feedback_mode
    if resume_payload is not None:
        payload["resume_payload"] = resume_payload
        payload["message"] = ""
    if inquiry_receipt_payload is not None:
        payload["inquiry_receipt_payload"] = inquiry_receipt_payload

    resp = client.post(url, json=payload, timeout=timeout_seconds)
    resp.raise_for_status()
    body = resp.json()
    if not isinstance(body, dict):
        raise RuntimeError("/api/chat response is not JSON object")
    return body


def _guides_count(state: dict[str, Any]) -> int:
    layer2 = state.get("layer2_memory") if isinstance(state.get("layer2_memory"), dict) else {}
    guides = layer2.get("action_guides") if isinstance(layer2, dict) else []
    if isinstance(guides, list):
        return len(guides)
    return 0


def _inquiry_questions(state: dict[str, Any]) -> list[dict[str, Any]]:
    card = state.get("inquiry_card") if isinstance(state.get("inquiry_card"), dict) else None
    questions = card.get("questions") if isinstance(card, dict) else None
    if not isinstance(questions, list):
        return []
    return [item for item in questions if isinstance(item, dict)]


def _has_usable_inquiry_card(state: dict[str, Any]) -> bool:
    return bool(_inquiry_questions(state))


def _is_onboarding_like_state(state: dict[str, Any], stage: str | None = None) -> bool:
    if stage == "onboarding":
        return True
    route_to = _as_str(state.get("route_to"), "").strip()
    current_agent = _as_str(state.get("current_agent"), "").strip()
    return route_to == "onboarding" or current_agent == "onboarding"


def _needs_live_state_refresh(state: dict[str, Any], *, stage: str | None = None) -> bool:
    if not isinstance(state, dict):
        return True
    if state.get("onboarding_completed") is True:
        return False
    if _has_usable_inquiry_card(state):
        return False
    if needs_crushe_guide_completion(state):
        return False
    pending = state.get("pending_responses")
    if isinstance(pending, list) and pending:
        if _is_onboarding_like_state(state, stage=stage):
            # Onboarding can briefly expose only transitional copy or a placeholder inquiry_card
            # before the real interrupt-backed questionnaire is restored.
            return True
        return False
    if state.get("status_report") or state.get("action_plan"):
        return False
    if _guides_count(state) > 0:
        return False
    return True


def _fetch_live_thread_state(session_id: str) -> dict[str, Any] | None:
    try:
        agent_impl_root = PROJECT_ROOT / "agent_impl"
        agent_impl_root_str = str(agent_impl_root)
        if agent_impl_root_str not in sys.path:
            sys.path.insert(0, agent_impl_root_str)
        from api.sdk_client import get_thread_state, session_to_thread_id

        return get_thread_state(session_to_thread_id(session_id))
    except Exception:
        return None


@dataclass
class StageOutcome:
    name: str
    passed: bool
    reason: str
    evidence: dict[str, Any] = field(default_factory=dict)


class AttemptContext:
    def __init__(
        self,
        *,
        cfg: dict[str, Any],
        session_id: str,
        http_session: requests.Session | None = None,
        uploaded_image_digest: str = "",
    ):
        self.cfg = cfg
        self.session_id = session_id
        self.http_session = http_session
        self.uploaded_image_digest = uploaded_image_digest
        self.max_total_turns = cfg["limits"]["max_total_turns"]
        self.timeout_seconds = cfg["meta"]["timeout_seconds"]
        self.total_turns = 0
        self.turn_logs: list[dict[str, Any]] = []
        self._thread_state_poll_seconds = 12
        self._onboarding_state_poll_seconds = 24

    def _snapshot(self, state: dict[str, Any], tool_names: list[str], resp: dict[str, Any]) -> dict[str, Any]:
        layer2 = state.get("layer2_memory") if isinstance(state.get("layer2_memory"), dict) else {}
        return {
            "onboarding_completed": bool(state.get("onboarding_completed")),
            "next_action": _as_str(state.get("next_action"), ""),
            "route_to": _as_str(state.get("route_to"), ""),
            "current_agent": _as_str(state.get("current_agent"), ""),
            "inquiry_card": bool(state.get("inquiry_card")),
            "feedback_status": _as_str(resp.get("feedback_status") or state.get("feedback_status"), ""),
            "guides_count": len(get_guides(state)),
            "has_status_report": bool(layer2.get("current_status_report") or state.get("status_report")),
            "has_action_plan": bool(layer2.get("current_action_plan") or state.get("action_plan")),
            "tool_names_tail": tool_names[-8:],
        }

    def send(
        self,
        *,
        stage: str,
        message: str,
        note: str,
        images: list[dict[str, Any]] | None = None,
        feedback_mode: dict[str, Any] | None = None,
        resume_payload: dict[str, Any] | None = None,
        inquiry_receipt_payload: dict[str, Any] | None = None,
    ) -> tuple[dict[str, Any], dict[str, Any], list[str]]:
        if self.total_turns >= self.max_total_turns:
            raise RuntimeError(f"max_total_turns exceeded ({self.max_total_turns})")

        effective_timeout = self.timeout_seconds
        if resume_payload is not None:
            effective_timeout = max(effective_timeout, 420)
        elif stage == "feedback":
            effective_timeout = max(effective_timeout, 600)
        elif stage in {"main", "status", "plan", "guide"}:
            effective_timeout = max(effective_timeout, 300)

        resp = post_chat(
            base_url=self.cfg["meta"]["base_url"],
            session_id=self.session_id,
            message=message,
            timeout_seconds=effective_timeout,
            images=images,
            feedback_mode=feedback_mode,
            resume_payload=resume_payload,
            inquiry_receipt_payload=inquiry_receipt_payload,
            session=self.http_session,
        )
        state = resp.get("state") if isinstance(resp.get("state"), dict) else {}
        if _needs_live_state_refresh(state, stage=stage):
            poll_budget = self._onboarding_state_poll_seconds if stage == "onboarding" else self._thread_state_poll_seconds
            deadline = time.time() + poll_budget
            while time.time() < deadline:
                live_state = _fetch_live_thread_state(self.session_id)
                if isinstance(live_state, dict) and not _needs_live_state_refresh(live_state, stage=stage):
                    state = live_state
                    break
                time.sleep(1.0)
        tool_names = tail_tool_names(state)

        self.total_turns += 1
        self.turn_logs.append(
            {
                "turn": self.total_turns,
                "stage": stage,
                "note": note,
                "message_preview": (message or "[resume]")[:240],
                "has_images": bool(images),
                "used_resume_payload": bool(resume_payload),
                "snapshot": self._snapshot(state, tool_names, resp),
            }
        )
        return resp, state, tool_names


def run_onboarding(
    ctx: AttemptContext,
    first_turn_images: list[dict[str, Any]] | None = None,
) -> tuple[StageOutcome, dict[str, Any]]:
    max_turns = ctx.cfg["limits"]["max_turns_per_stage"]
    escalate_turn = ctx.cfg["limits"]["stall_escalation_turns"]

    last_state: dict[str, Any] = {}
    should_send_guide_done = False
    for idx in range(max_turns):
        inquiry_submit = None
        if idx == 0:
            msg = build_onboarding_seed(ctx.cfg)
            note = "onboarding_seed"
        elif should_send_guide_done or needs_crushe_guide_completion(last_state):
            msg = "[SYS:CRUSHE_GUIDE_DONE]"
            note = "onboarding_guide_done"
            should_send_guide_done = False
        else:
            strong = idx >= escalate_turn
            inquiry_submit = build_inquiry_submission(
                state=last_state,
                cfg=ctx.cfg,
                stage="onboarding",
                uploaded_image_digest=ctx.uploaded_image_digest,
            )
            if inquiry_submit:
                msg = inquiry_submit["message"]
                note = "onboarding_inquiry_resume"
            elif wants_more_info(last_state):
                msg = build_auto_answer(ctx.cfg, "onboarding", strong=strong)
                note = "onboarding_auto_answer"
            else:
                msg = "请继续 onboarding，直到可以进入主流程。"
                if strong:
                    msg += " 本轮请务必推进到可进入主流程。"
                note = "onboarding_nudge"

        images = first_turn_images if idx == 0 and first_turn_images else None
        resp, state, tool_names = ctx.send(
            stage="onboarding",
            message=msg,
            note=note,
            images=images,
            resume_payload=inquiry_submit["resume_payload"] if inquiry_submit else None,
            inquiry_receipt_payload=inquiry_submit["inquiry_receipt_payload"] if inquiry_submit else None,
        )
        last_state = state
        should_send_guide_done = response_needs_crushe_guide_completion(resp, state)

        if state.get("onboarding_completed") is True:
            return (
                StageOutcome(
                    name="onboarding",
                    passed=True,
                    reason="ok",
                    evidence={
                        "onboarding_completed": True,
                        "tool_names_tail": tool_names[-8:],
                    },
                ),
                state,
            )

    return (
        StageOutcome(
            name="onboarding",
            passed=False,
            reason=f"stage_timeout_after_{max_turns}_turns",
            evidence={
                "onboarding_completed": bool(last_state.get("onboarding_completed")),
                "last_next_action": _as_str(last_state.get("next_action"), ""),
            },
        ),
        last_state,
    )


def run_stage_with_prompts(
    *,
    ctx: AttemptContext,
    stage_name: str,
    natural_prompt: str,
    strong_prompt: str,
    detector: Callable[[dict[str, Any], list[str], dict[str, Any]], bool],
    stage_hint: str,
    initial_state: dict[str, Any] | None = None,
) -> tuple[StageOutcome, dict[str, Any]]:
    max_turns = ctx.cfg["limits"]["max_turns_per_stage"]
    escalate_turn = ctx.cfg["limits"]["stall_escalation_turns"]

    last_state: dict[str, Any] = initial_state if isinstance(initial_state, dict) else {}
    for idx in range(max_turns):
        strong = idx >= escalate_turn
        inquiry_submit = build_inquiry_submission(
            state=last_state,
            cfg=ctx.cfg,
            stage=stage_name,
            uploaded_image_digest=ctx.uploaded_image_digest,
        )
        if inquiry_submit:
            msg = inquiry_submit["message"]
            note = f"{stage_name}_inquiry_resume"
        elif idx == 0:
            msg = natural_prompt
            note = f"{stage_name}_prompt"
        else:
            if wants_more_info(last_state):
                msg = build_auto_answer(ctx.cfg, stage_name, strong=strong)
                note = f"{stage_name}_auto_answer"
            else:
                if strong:
                    msg = strong_prompt
                    note = f"{stage_name}_strong_nudge"
                else:
                    msg = f"请继续{stage_hint}，并给出可执行输出。"
                    note = f"{stage_name}_nudge"

        resp, state, tool_names = ctx.send(
            stage=stage_name,
            message=msg,
            note=note,
            resume_payload=inquiry_submit["resume_payload"] if inquiry_submit else None,
            inquiry_receipt_payload=inquiry_submit["inquiry_receipt_payload"] if inquiry_submit else None,
        )
        last_state = state

        if detector(state, tool_names, resp):
            return (
                StageOutcome(
                    name=stage_name,
                    passed=True,
                    reason="ok",
                    evidence={
                        "tool_names_tail": tool_names[-8:],
                        "snapshot": ctx.turn_logs[-1]["snapshot"],
                    },
                ),
                state,
            )

    return (
        StageOutcome(
            name=stage_name,
            passed=False,
            reason=f"stage_timeout_after_{max_turns}_turns",
            evidence={"last_snapshot": ctx.turn_logs[-1]["snapshot"] if ctx.turn_logs else {}},
        ),
        last_state,
    )


def run_feedback(ctx: AttemptContext, state_before_feedback: dict[str, Any]) -> tuple[StageOutcome, dict[str, Any]]:
    guide_id = latest_guide_id(state_before_feedback)
    if not guide_id:
        return (
            StageOutcome(
                name="feedback",
                passed=False,
                reason="no_guide_id_found",
                evidence={"guides_count": len(get_guides(state_before_feedback))},
            ),
            state_before_feedback,
        )

    fb = ctx.cfg["feedback"]
    completion_status = fb["completion_status"] or "partial"
    completion_detail = fb["completion_detail"] or "执行后补充反馈"
    followup = fb["followup_answer"] or "补充：我会继续执行并反馈。"

    first_message = (
        f"[行动反馈] guide_id={guide_id}\n"
        f"完成状态：{completion_status}\n"
        f"完成详情：{completion_detail}"
    )

    first_resp, first_state, _ = ctx.send(
        stage="feedback",
        message=first_message,
        note="feedback_submit",
        feedback_mode={
            "guide_id": guide_id,
            "completion_status": completion_status,
            "completion_detail": completion_detail,
        },
    )

    current_resp = first_resp
    current_state = first_state
    feedback_status = _as_str(current_resp.get("feedback_status") or current_state.get("feedback_status"), "")
    max_followups = max(1, min(6, int(ctx.cfg["limits"].get("max_turns_per_stage") or 4) - 1))
    followup_round = 0

    while feedback_status == "asking" and followup_round < max_followups:
        followup_round += 1
        feedback_question = _as_str(
            current_resp.get("feedback_question") or current_state.get("feedback_question"),
            "",
        ).strip()
        next_message = followup
        if feedback_question:
            next_message = f"{followup}\n\n补充回应你的问题：{feedback_question}"

        current_resp, current_state, _ = ctx.send(
            stage="feedback",
            message=next_message,
            note=f"feedback_followup_{followup_round}",
            feedback_mode={"guide_id": guide_id},
        )
        feedback_status = _as_str(
            current_resp.get("feedback_status") or current_state.get("feedback_status"),
            "",
        )

    if feedback_status == "asking":
        return (
            StageOutcome(
                name="feedback",
                passed=False,
                reason="feedback_still_asking_after_followups",
                evidence={"guide_id": guide_id, "followup_rounds": followup_round},
            ),
            current_state,
        )

    return (
        StageOutcome(
            name="feedback",
            passed=True,
            reason="ok",
            evidence={
                "guide_id": guide_id,
                "feedback_status": feedback_status or "completed_or_none",
                "followup_rounds": followup_round,
            },
        ),
        current_state,
    )


def run_ui_smoke_probe(
    cfg: dict[str, Any],
    attempt_dir: Path,
    *,
    email_override: str = "",
    password_override: str = "",
) -> dict[str, Any]:
    ui_cfg = cfg["ui_smoke"]
    output_json = attempt_dir / "ui_smoke_result.json"
    email = email_override.strip() or ui_cfg["email"]
    password = password_override.strip() or ui_cfg["password"]

    cmd = [
        sys.executable,
        str(PROJECT_ROOT / "scripts" / "e2e_ui_smoke_probe.py"),
        "--base-url",
        cfg["meta"]["base_url"],
        "--email",
        email,
        "--password",
        password,
        "--smoke-message",
        ui_cfg["smoke_message"],
        "--timeout-seconds",
        str(ui_cfg["timeout_seconds"]),
        "--output-dir",
        str(attempt_dir),
        "--output-json",
        str(output_json),
    ]

    proc = subprocess.run(cmd, cwd=str(PROJECT_ROOT), capture_output=True, text=True)

    result: dict[str, Any] = {
        "ok": proc.returncode == 0,
        "exit_code": proc.returncode,
        "stdout_tail": (proc.stdout or "")[-3000:],
        "stderr_tail": (proc.stderr or "")[-3000:],
        "result_json_path": str(output_json),
    }

    if output_json.exists():
        try:
            result["probe"] = json.loads(output_json.read_text(encoding="utf-8"))
            result["ok"] = bool(result["probe"].get("ok"))
        except Exception as exc:
            result["ok"] = False
            result["parse_error"] = str(exc)

    return result


def default_main_prompt(cfg: dict[str, Any]) -> str:
    prompt = cfg["flow"]["main_prompt"].strip()
    if prompt:
        return prompt
    return "请先做一个总览判断：我当前最该优先处理的问题是什么？"


def default_status_prompt(cfg: dict[str, Any]) -> str:
    prompt = cfg["flow"]["status_prompt"].strip()
    if prompt:
        return prompt
    return "请做现状分析，明确关系阶段、证据和风险。"


def default_plan_prompt(cfg: dict[str, Any]) -> str:
    prompt = cfg["flow"]["plan_prompt"].strip()
    if prompt:
        return prompt
    return "请给出行动规划，包含阶段目标、优先级和执行路径。"


def default_guide_prompt(cfg: dict[str, Any]) -> str:
    prompt = cfg["flow"]["guide_prompt"].strip()
    if prompt:
        return prompt
    return "请直接给我行动指南（SOP+话术），不要只讲原则。"


def run_single_attempt(cfg: dict[str, Any], attempt_index: int, run_ui_smoke: bool, run_root: Path) -> dict[str, Any]:
    session_id = f"{cfg['meta']['case_id']}_{utc_stamp()}_{attempt_index}_{uuid.uuid4().hex[:6]}"
    eval_doc_dir = Path(_as_str(cfg["meta"].get("eval_doc_dir"), str(PROJECT_ROOT))).resolve()

    attempt_dir = run_root / f"attempt_{attempt_index}"
    attempt_dir.mkdir(parents=True, exist_ok=True)

    auth_info: dict[str, Any] = {}
    try:
        http_session, auth_info = ensure_authenticated_session(
            cfg=cfg,
            attempt_tag=f"{attempt_index}_{uuid.uuid4().hex[:6]}",
            timeout_seconds=cfg["meta"]["timeout_seconds"],
        )
    except Exception as exc:
        return {
            "attempt_index": attempt_index,
            "session_id": session_id,
            "passed": False,
            "stages": [],
            "ui_smoke": None,
            "total_turns": 0,
            "turn_logs": [],
            "auth": auth_info,
            "error": str(exc),
            "attempt_dir": str(attempt_dir),
        }

    ctx: AttemptContext | None = None
    stages: list[dict[str, Any]] = []
    final_state: dict[str, Any] = {}

    def append_stage(outcome: StageOutcome) -> None:
        stages.append(
            {
                "name": outcome.name,
                "passed": outcome.passed,
                "reason": outcome.reason,
                "evidence": outcome.evidence,
            }
        )

    try:
        chat_images_payload: list[dict[str, Any]] = []
        upload_stage, chat_images_payload, upload_evidence = run_image_upload_stage(
            cfg=cfg,
            session_id=session_id,
            eval_doc_dir=eval_doc_dir,
            http_session=http_session,
        )
        ctx = AttemptContext(
            cfg=cfg,
            session_id=session_id,
            http_session=http_session,
            uploaded_image_digest=_build_uploaded_image_digest(upload_evidence),
        )
        append_stage(upload_stage)
        if upload_evidence:
            (attempt_dir / "uploaded_images.json").write_text(
                json.dumps(upload_evidence, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
        if not upload_stage.passed:
            raise RuntimeError(f"image_upload_failed:{upload_stage.reason}")

        onb, state = run_onboarding(ctx, first_turn_images=chat_images_payload)
        append_stage(onb)
        final_state = state
        if not onb.passed:
            raise RuntimeError(f"onboarding_failed:{onb.reason}")

        main_outcome, state = run_stage_with_prompts(
            ctx=ctx,
            stage_name="main",
            natural_prompt=default_main_prompt(cfg),
            strong_prompt="请直接给出主流程判断，并推进后续分析，不要停在泛泛问候。",
            detector=lambda s, t, r: has_main_evidence(r, s, t),
            stage_hint="主流程判断",
            initial_state=state,
        )
        append_stage(main_outcome)
        final_state = state
        if not main_outcome.passed:
            raise RuntimeError(f"main_failed:{main_outcome.reason}")

        status_outcome, state = run_stage_with_prompts(
            ctx=ctx,
            stage_name="status",
            natural_prompt=default_status_prompt(cfg),
            strong_prompt=(
                "系统验收要求：请触发或完成现状分析子流程，确保产出 status report。"
            ),
            detector=lambda s, t, r: has_status_evidence(s, t),
            stage_hint="现状分析",
            initial_state=state,
        )
        append_stage(status_outcome)
        final_state = state
        if not status_outcome.passed:
            raise RuntimeError(f"status_failed:{status_outcome.reason}")

        plan_outcome, state = run_stage_with_prompts(
            ctx=ctx,
            stage_name="plan",
            natural_prompt=default_plan_prompt(cfg),
            strong_prompt=(
                "系统验收要求：请触发或完成行动规划子流程，确保产出 action plan。"
            ),
            detector=lambda s, t, r: has_plan_evidence(s, t),
            stage_hint="行动规划",
            initial_state=state,
        )
        append_stage(plan_outcome)
        final_state = state
        if not plan_outcome.passed:
            raise RuntimeError(f"plan_failed:{plan_outcome.reason}")

        guide_outcome, state = run_stage_with_prompts(
            ctx=ctx,
            stage_name="guide",
            natural_prompt=default_guide_prompt(cfg),
            strong_prompt=(
                "系统验收要求：请触发或完成行动指南子流程，确保至少产出一条 action guide。"
            ),
            detector=lambda s, t, r: has_guide_evidence(s, t),
            stage_hint="行动指南",
            initial_state=state,
        )
        append_stage(guide_outcome)
        final_state = state
        if not guide_outcome.passed:
            raise RuntimeError(f"guide_failed:{guide_outcome.reason}")

        feedback_outcome, state = run_feedback(ctx, final_state)
        append_stage(feedback_outcome)
        final_state = state
        if not feedback_outcome.passed:
            raise RuntimeError(f"feedback_failed:{feedback_outcome.reason}")

        ui_result = None
        if run_ui_smoke:
            ui_result = run_ui_smoke_probe(
                cfg,
                attempt_dir=attempt_dir,
                email_override=_as_str(auth_info.get("email"), ""),
                password_override=cfg["ui_smoke"]["password"],
            )
            if not ui_result.get("ok"):
                raise RuntimeError("ui_smoke_failed")

        passed = all(stage["passed"] for stage in stages) and (ui_result is None or ui_result.get("ok"))
        return {
            "attempt_index": attempt_index,
            "session_id": session_id,
            "passed": passed,
            "stages": stages,
            "ui_smoke": ui_result,
            "total_turns": ctx.total_turns,
            "turn_logs": ctx.turn_logs,
            "auth": auth_info,
            "attempt_dir": str(attempt_dir),
        }

    except Exception as exc:
        return {
            "attempt_index": attempt_index,
            "session_id": session_id,
            "passed": False,
            "stages": stages,
            "ui_smoke": None,
            "total_turns": ctx.total_turns if ctx else 0,
            "turn_logs": ctx.turn_logs if ctx else [],
            "auth": auth_info,
            "error": str(exc),
            "attempt_dir": str(attempt_dir),
        }


def to_markdown(report: dict[str, Any]) -> str:
    lines: list[str] = []
    lines.append("# Real API Regression Report")
    lines.append("")
    lines.append(f"- Case ID: `{report['case_id']}`")
    lines.append(f"- Generated At (UTC): `{report['generated_at']}`")
    lines.append(f"- Base URL: `{report['base_url']}`")
    lines.append(f"- Final Result: `{'PASS' if report['passed'] else 'FAIL'}`")
    lines.append("")

    lines.append("## Attempt Summary")
    lines.append("")
    lines.append("| Attempt | Session ID | Pass | Total Turns | Error |")
    lines.append("| --- | --- | --- | --- | --- |")
    for attempt in report["attempts"]:
        lines.append(
            "| {idx} | `{sid}` | {ok} | {turns} | {err} |".format(
                idx=attempt.get("attempt_index"),
                sid=attempt.get("session_id", ""),
                ok="YES" if attempt.get("passed") else "NO",
                turns=attempt.get("total_turns", 0),
                err=_as_str(attempt.get("error"), "-").replace("|", "/"),
            )
        )
    lines.append("")

    for attempt in report["attempts"]:
        lines.append(f"## Attempt {attempt.get('attempt_index')} Details")
        lines.append("")
        lines.append(f"- Session ID: `{attempt.get('session_id', '')}`")
        lines.append(f"- Attempt Dir: `{attempt.get('attempt_dir', '')}`")
        lines.append("")
        lines.append("| Stage | Pass | Reason |")
        lines.append("| --- | --- | --- |")
        for stage in attempt.get("stages", []):
            lines.append(
                "| {name} | {ok} | {reason} |".format(
                    name=_as_str(stage.get("name"), ""),
                    ok="YES" if stage.get("passed") else "NO",
                    reason=_as_str(stage.get("reason"), "-").replace("|", "/"),
                )
            )
        lines.append("")

        image_stage = next(
            (
                s
                for s in attempt.get("stages", [])
                if _as_str(s.get("name"), "") == "image_upload"
            ),
            None,
        )
        if isinstance(image_stage, dict):
            evidence = image_stage.get("evidence") if isinstance(image_stage.get("evidence"), dict) else {}
            uploaded_count = evidence.get("uploaded_count")
            if uploaded_count is not None:
                lines.append("### Image Upload")
                lines.append("")
                lines.append(f"- Uploaded Images: `{uploaded_count}`")
                lines.append("")

        ui = attempt.get("ui_smoke")
        if ui is not None:
            lines.append("### UI Smoke")
            lines.append("")
            lines.append(f"- Result: `{'PASS' if ui.get('ok') else 'FAIL'}`")
            probe = ui.get("probe") if isinstance(ui.get("probe"), dict) else {}
            if probe.get("screenshot"):
                lines.append(f"- Screenshot: `{probe.get('screenshot')}`")
            if ui.get("result_json_path"):
                lines.append(f"- Probe JSON: `{ui.get('result_json_path')}`")
            lines.append("")

    lines.append("## Config Snapshot (masked)")
    lines.append("")
    lines.append("```json")
    lines.append(json.dumps(report.get("config", {}), ensure_ascii=False, indent=2))
    lines.append("```")
    lines.append("")

    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(description="Run real API multi-turn regression.")
    parser.add_argument("--eval-doc", required=True, help="Path to docs/测试评估文档.md")
    parser.add_argument("--boot-mode", choices=["check", "auto"], default=None)
    parser.add_argument("--start-cmd", default=None)
    parser.add_argument("--with-ui-smoke", action="store_true")
    parser.add_argument("--retry-once", action="store_true")
    parser.add_argument("--validate-only", action="store_true")

    args = parser.parse_args()

    eval_doc = Path(args.eval_doc).resolve()
    if not eval_doc.exists():
        raise SystemExit(f"eval doc not found: {eval_doc}")

    raw_cfg = load_eval_doc(eval_doc)
    cfg = normalize_config(raw_cfg)
    cfg["meta"]["eval_doc_dir"] = str(eval_doc.parent.resolve())

    if args.boot_mode is not None:
        cfg["meta"]["boot_mode"] = args.boot_mode
    if args.start_cmd is not None:
        cfg["meta"]["start_cmd"] = args.start_cmd
    if args.retry_once:
        cfg["limits"]["retry_once"] = True
    if args.with_ui_smoke:
        cfg["ui_smoke"]["enabled"] = True

    if args.validate_only:
        print(json.dumps(mask_config_for_report(cfg), ensure_ascii=False, indent=2))
        return 0

    REPORT_DIR.mkdir(parents=True, exist_ok=True)
    run_stamp = utc_stamp()
    run_root = REPORT_DIR / f"{cfg['meta']['case_id']}_{run_stamp}"
    run_root.mkdir(parents=True, exist_ok=True)

    service_info: dict[str, Any] = {}

    try:
        service_info = ensure_service_ready(
            cfg=cfg,
            boot_mode_override=args.boot_mode,
            start_cmd_override=args.start_cmd,
            report_run_dir=run_root,
        )

        attempts: list[dict[str, Any]] = []
        run_ui_smoke = bool(cfg["ui_smoke"].get("enabled"))

        first = run_single_attempt(cfg, attempt_index=1, run_ui_smoke=run_ui_smoke, run_root=run_root)
        attempts.append(first)

        if (not first.get("passed")) and cfg["limits"]["retry_once"]:
            second = run_single_attempt(cfg, attempt_index=2, run_ui_smoke=run_ui_smoke, run_root=run_root)
            attempts.append(second)

        final_passed = any(a.get("passed") for a in attempts)

        report = {
            "case_id": cfg["meta"]["case_id"],
            "generated_at": now_iso(),
            "base_url": cfg["meta"]["base_url"],
            "passed": final_passed,
            "service": {
                k: v for k, v in service_info.items() if not k.startswith("_")
            },
            "config": mask_config_for_report(cfg),
            "attempts": attempts,
        }

        json_path = run_root / f"{cfg['meta']['case_id']}_{run_stamp}.json"
        md_path = run_root / f"{cfg['meta']['case_id']}_{run_stamp}.md"

        json_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
        md_path.write_text(to_markdown(report), encoding="utf-8")

        print(json.dumps({
            "passed": final_passed,
            "json_report": str(json_path),
            "md_report": str(md_path),
            "run_dir": str(run_root),
        }, ensure_ascii=False, indent=2))

        return 0 if final_passed else 2

    finally:
        cleanup_service_boot(service_info)


if __name__ == "__main__":
    raise SystemExit(main())
