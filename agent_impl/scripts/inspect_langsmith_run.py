#!/usr/bin/env python3
"""
用 LangSmith API 查看指定 run 的详情和子 runs，用于排查 handoff 等路由问题。
用法: python scripts/inspect_langsmith_run.py <run_id>
"""
import os
import sys
import json

# 加载 .env
def load_env():
    env_path = os.path.join(os.path.dirname(__file__), "..", ".env")
    if os.path.isfile(env_path):
        with open(env_path) as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith("#") and "=" in line:
                    k, v = line.split("=", 1)
                    os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))


def main():
    load_env()
    run_id = (sys.argv[1] or "").strip() if len(sys.argv) > 1 else None
    if not run_id:
        print("用法: python scripts/inspect_langsmith_run.py <run_id>")
        sys.exit(1)

    try:
        from langsmith import Client
    except ImportError:
        print("请安装: pip install langsmith")
        sys.exit(1)

    api_key = os.environ.get("LANGSMITH_API_KEY")
    if not api_key:
        print("请设置 LANGSMITH_API_KEY（或在 agent_impl/.env 中配置）")
        sys.exit(1)

    client = Client(api_key=api_key)

    # 可能传入的是 trace_id（根 run）或任意 run_id
    print(f"正在拉取 run_id = {run_id} ...")
    run = client.read_run(run_id=run_id, load_child_runs=True)
    if not run:
        print("未找到该 run")
        sys.exit(1)

    # 若该 run 有 trace_id，拉取整条 trace 的所有 runs（便于看 main_agent -> skill_tools -> route 顺序）
    trace_id = getattr(run, "trace_id", None) or getattr(run, "draft_id", None) or run.id
    project_name = os.environ.get("LANGSMITH_PROJECT", "crushe-agent-debug")
    all_runs = list(client.list_runs(project_name=project_name, trace_id=trace_id))
    # 按开始时间排序
    all_runs.sort(key=lambda r: (getattr(r, "start_time") or getattr(r, "start_time_iso", "") or ""))
    print(f"\n同一 trace 共 {len(all_runs)} 个 runs (trace_id={trace_id}):")
    for i, r in enumerate(all_runs):
        name = getattr(r, "name", None) or "(no name)"
        rt = getattr(r, "run_type", None)
        rid = getattr(r, "id", None)
        parent_id = getattr(r, "parent_run_id", None)
        print(f"  {i+1}. [{rt}] {name}  id={rid}  parent={parent_id}")

    def ser(obj):
        if obj is None:
            return None
        if hasattr(obj, "model_dump"):
            return obj.model_dump()
        if isinstance(obj, dict):
            return {k: ser(v) for k, v in obj.items()}
        if isinstance(obj, (list, tuple)):
            return [ser(x) for x in obj]
        return obj

    def print_run(r, indent=0):
        pref = "  " * indent
        name = getattr(r, "name", None) or r.id
        run_type = getattr(r, "run_type", None)
        print(f"{pref}[{run_type}] {name} (id={r.id})")
        if indent == 0:
            if getattr(r, "inputs", None):
                inp = ser(r.inputs)
                if isinstance(inp, dict) and inp:
                    # 只打印和路由相关的状态
                    for k in ("_handoff_target", "_pending_action", "_return_to_main", "_reply_skill_complete",
                              "current_agent", "feedback_mode", "inquiry_card", "pending_questions",
                              "agent_resume_point", "_end_turn", "_iteration_count"):
                        if k in inp and inp[k] is not None:
                            print(f"{pref}  inputs.{k} = {repr(inp[k])}")
            if getattr(r, "outputs", None):
                out = ser(r.outputs)
                if isinstance(out, dict) and out:
                    for k in ("_handoff_target", "current_agent", "messages"):
                        if k in out:
                            v = out[k]
                            if k == "messages" and isinstance(v, list):
                                print(f"{pref}  outputs.{k} = list(len={len(v)})")
                            else:
                                print(f"{pref}  outputs.{k} = {repr(v)[:200]}")
        if getattr(r, "child_runs", None) and r.child_runs:
            for c in r.child_runs:
                print_run(c, indent + 1)

    print_run(run)

    # 再按 run_type 找 skill_tools 和 route 相关
    def collect_by_type(r, acc):
        rt = getattr(r, "run_type", None)
        if rt:
            acc.setdefault(rt, []).append(r)
        for c in getattr(r, "child_runs", None) or []:
            collect_by_type(c, acc)

    by_type = {}
    collect_by_type(run, by_type)
    print("\n--- 按 run_type 汇总 ---")
    for t, runs in sorted(by_type.items()):
        print(f"  {t}: {len(runs)} 个")

    # 重点：chain 类型的子 run 通常对应节点；找 name 含 skill_tools 或 route 的
    print("\n--- 与 skill_tools / route 相关的 runs ---")
    def find_routes(r, depth=0):
        name = (getattr(r, "name", None) or "").lower()
        rid = getattr(r, "id", None)
        if "skill_tools" in name or "route" in name or "main_agent" in name or "status_agent" in name:
            pref = "  " * depth
            print(f"{pref}name={getattr(r,'name',None)} id={rid} run_type={getattr(r,'run_type',None)}")
            if getattr(r, "inputs", None):
                inp = ser(r.inputs)
                if isinstance(inp, dict):
                    for k in ("_handoff_target", "_pending_action", "_return_to_main", "_reply_skill_complete",
                              "current_agent", "feedback_mode", "inquiry_card", "agent_resume_point", "_end_turn"):
                        if k in inp:
                            print(f"{pref}  in.{k} = {repr(inp[k])}")
            if getattr(r, "outputs", None):
                out = ser(r.outputs)
                if isinstance(out, dict):
                    for k in ("_handoff_target", "current_agent"):
                        if k in out:
                            print(f"{pref}  out.{k} = {repr(out[k])}")
        for c in getattr(r, "child_runs", None) or []:
            find_routes(c, depth + 1)

    find_routes(run)

    # 重点：读取 skill_tools 和 route_after_skill_tools 的输入输出
    skill_tools_id = route_after_st_id = None
    for r in all_runs:
        n = getattr(r, "name", None) or ""
        if n == "skill_tools":
            skill_tools_id = str(r.id)
        elif n == "route_after_skill_tools":
            route_after_st_id = str(r.id)
    if skill_tools_id:
        st_run = client.read_run(run_id=skill_tools_id)
        print("\n========== skill_tools 节点 ==========")
        if getattr(st_run, "inputs", None):
            inp = ser(st_run.inputs)
            if isinstance(inp, dict):
                for k in ("_handoff_target", "_pending_action", "current_agent", "messages"):
                    if k in inp:
                        v = inp[k]
                        if k == "messages" and isinstance(v, list):
                            print(f"  inputs.{k}: len={len(v)}")
                            for i, m in enumerate(v):
                                role = m.get("role") if isinstance(m, dict) else getattr(m, "type", "")
                                tc = m.get("tool_calls") if isinstance(m, dict) else getattr(m, "tool_calls", None)
                                if tc:
                                    names = [t.get("name") if isinstance(t, dict) else getattr(t, "get", lambda x: None) and t.get("name") for t in (tc or [])]
                                    print(f"    msg[{i}] role={role} tool_calls={names}")
                        else:
                            print(f"  inputs.{k} = {repr(v)}")
        if getattr(st_run, "outputs", None):
            out = ser(st_run.outputs)
            if isinstance(out, dict):
                for k in ("_handoff_target", "current_agent"):
                    if k in out:
                        print(f"  outputs.{k} = {repr(out[k])}")
    if route_after_st_id:
        rt_run = client.read_run(run_id=route_after_st_id)
        print("\n========== route_after_skill_tools 节点 ==========")
        if getattr(rt_run, "inputs", None):
            inp = ser(rt_run.inputs)
            if isinstance(inp, dict):
                for k in ("_handoff_target", "_pending_action", "_return_to_main", "_reply_skill_complete",
                          "current_agent", "feedback_mode", "inquiry_card", "agent_resume_point", "_end_turn", "_iteration_count"):
                    if k in inp:
                        print(f"  inputs.{k} = {repr(inp[k])}")
        if getattr(rt_run, "outputs", None):
            print(f"  outputs (路由结果) = {repr(rt_run.outputs)}")


if __name__ == "__main__":
    main()
