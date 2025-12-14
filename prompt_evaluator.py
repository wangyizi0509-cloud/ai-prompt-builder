"""
Prompt 批量评估工具
===================
功能：
1. 导入评估集（Excel）
2. 自动识别 prompt 中的 {{占位符}}，映射到评估集字段
3. 批量拼接 prompt 并调用模型 API
4. 输出结果到 Excel

使用方法：
    streamlit run prompt_evaluator.py

依赖安装：
    pip install streamlit pandas openpyxl openai
"""

import streamlit as st
import pandas as pd
import re
import json
import time
import os
from datetime import datetime
from io import BytesIO
from pathlib import Path
from openai import OpenAI
from concurrent.futures import ThreadPoolExecutor, as_completed


# ============== 配置管理 ==============

CONFIG_FILE = Path(__file__).parent / "model_configs.json"

def load_model_configs() -> dict:
    """加载模型配置"""
    if CONFIG_FILE.exists():
        with open(CONFIG_FILE, 'r', encoding='utf-8') as f:
            return json.load(f)
    return {"models": {}, "default": None}

def save_model_configs(configs: dict):
    """保存模型配置"""
    with open(CONFIG_FILE, 'w', encoding='utf-8') as f:
        json.dump(configs, f, ensure_ascii=False, indent=2)

def get_model_list() -> list[str]:
    """获取所有模型名称列表"""
    configs = load_model_configs()
    return list(configs.get("models", {}).keys())

def get_model_config(model_key: str) -> dict:
    """获取指定模型的配置"""
    configs = load_model_configs()
    return configs.get("models", {}).get(model_key, {})

def add_model_config(name: str, api_base: str, api_key: str, model_name: str, description: str = ""):
    """添加新的模型配置"""
    configs = load_model_configs()
    configs["models"][name] = {
        "api_base": api_base,
        "api_key": api_key,
        "model_name": model_name,
        "description": description
    }
    if not configs.get("default"):
        configs["default"] = name
    save_model_configs(configs)

def delete_model_config(name: str):
    """删除模型配置"""
    configs = load_model_configs()
    if name in configs.get("models", {}):
        del configs["models"][name]
        if configs.get("default") == name:
            configs["default"] = list(configs["models"].keys())[0] if configs["models"] else None
        save_model_configs(configs)


# ============== 工具函数 ==============

def extract_placeholders(prompt_template: str) -> list[str]:
    """从 prompt 模板中提取所有 {{xxx}} 占位符"""
    pattern = r'\{\{([^}]+)\}\}'
    matches = re.findall(pattern, prompt_template)
    # 去重并保持顺序
    seen = set()
    unique = []
    for m in matches:
        if m not in seen:
            seen.add(m)
            unique.append(m)
    return unique


def fill_prompt(template: str, mapping: dict, row: pd.Series) -> str:
    """根据映射关系，用评估集数据填充 prompt 模板"""
    filled = template
    for placeholder, excel_field in mapping.items():
        if excel_field and excel_field in row.index:
            value = str(row[excel_field]) if pd.notna(row[excel_field]) else ""
            filled = filled.replace(f"{{{{{placeholder}}}}}", value)
    return filled


def call_llm(client: OpenAI, model: str, prompt: str, system_prompt: str = None, 
             temperature: float = 0.7, max_tokens: int = 2000) -> tuple[str, float]:
    """调用 LLM API，返回 (响应内容, 耗时秒数)"""
    messages = []
    if system_prompt:
        messages.append({"role": "system", "content": system_prompt})
    messages.append({"role": "user", "content": prompt})
    
    start_time = time.time()
    try:
        response = client.chat.completions.create(
            model=model,
            messages=messages,
            temperature=temperature,
            max_tokens=max_tokens
        )
        elapsed = time.time() - start_time
        return response.choices[0].message.content, elapsed
    except Exception as e:
        elapsed = time.time() - start_time
        return f"[ERROR] {str(e)}", elapsed


def batch_evaluate(prompts: list[str], client: OpenAI, model: str, 
                   system_prompt: str, temperature: float, max_tokens: int,
                   max_workers: int = 3, progress_callback=None) -> list[dict]:
    """批量调用 LLM，返回结果列表"""
    results = [None] * len(prompts)
    
    def process_one(idx: int, prompt: str):
        response, elapsed = call_llm(client, model, prompt, system_prompt, temperature, max_tokens)
        return idx, response, elapsed
    
    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        futures = {executor.submit(process_one, i, p): i for i, p in enumerate(prompts)}
        completed = 0
        for future in as_completed(futures):
            idx, response, elapsed = future.result()
            results[idx] = {"response": response, "time": elapsed}
            completed += 1
            if progress_callback:
                progress_callback(completed / len(prompts))
    
    return results


# ============== Streamlit UI ==============

def main():
    st.set_page_config(
        page_title="Prompt 批量评估工具",
        page_icon="🧪",
        layout="wide"
    )
    
    st.title("🧪 Prompt 批量评估工具")
    st.caption("导入评估集 → 映射字段 → 批量推理 → 导出结果")
    
    # 初始化 session state
    if "prompts_generated" not in st.session_state:
        st.session_state.prompts_generated = []
    if "results" not in st.session_state:
        st.session_state.results = []
    
    # ===== 侧边栏：API 配置 =====
    with st.sidebar:
        st.header("⚙️ 模型选择")
        
        # 加载配置
        configs = load_model_configs()
        model_list = get_model_list()
        
        if model_list:
            # 下拉选择模型
            default_idx = 0
            if configs.get("default") in model_list:
                default_idx = model_list.index(configs["default"])
            
            selected_model_key = st.selectbox(
                "选择模型",
                model_list,
                index=default_idx,
                help="从已配置的模型中选择"
            )
            
            # 获取选中模型的配置
            model_config = get_model_config(selected_model_key)
            api_base = model_config.get("api_base", "")
            api_key = model_config.get("api_key", "")
            model_name = model_config.get("model_name", "")
            
            # 显示当前配置信息
            with st.expander("📋 当前模型配置", expanded=False):
                st.text(f"API Base: {api_base}")
                st.text(f"模型: {model_name}")
                if model_config.get("description"):
                    st.caption(model_config["description"])
        else:
            st.warning("暂无模型配置，请添加")
            api_base = ""
            api_key = ""
            model_name = ""
        
        st.divider()
        
        # 添加/管理模型配置
        with st.expander("➕ 添加新模型", expanded=not model_list):
            new_name = st.text_input("配置名称", placeholder="如: GPT-4o、Claude-3.5")
            new_api_base = st.text_input("API Base URL", placeholder="https://api.openai.com/v1")
            new_api_key = st.text_input("API Key", type="password", placeholder="sk-xxx")
            new_model_name = st.text_input("模型名称", placeholder="gpt-4o")
            new_description = st.text_input("备注 (可选)", placeholder="用途描述")
            
            if st.button("💾 保存配置", use_container_width=True):
                if new_name and new_api_base and new_api_key and new_model_name:
                    add_model_config(new_name, new_api_base, new_api_key, new_model_name, new_description)
                    st.success(f"✅ 已添加 {new_name}")
                    st.rerun()
                else:
                    st.error("请填写完整信息")
        
        # 删除模型
        if model_list:
            with st.expander("🗑️ 删除模型"):
                delete_target = st.selectbox("选择要删除的模型", model_list, key="delete_select")
                if st.button("确认删除", type="secondary"):
                    delete_model_config(delete_target)
                    st.success(f"已删除 {delete_target}")
                    st.rerun()
        
        st.divider()
        st.subheader("推理参数")
        temperature = st.slider("Temperature", 0.0, 2.0, 0.7, 0.1)
        max_tokens = st.number_input("Max Tokens", 100, 8000, 2000, 100)
        max_workers = st.slider("并发数", 1, 10, 3, help="同时调用 API 的线程数")
    
    # ===== 主界面 =====
    tab1, tab2, tab3 = st.tabs(["📝 Step 1: 配置 Prompt", "🔗 Step 2: 映射字段", "🚀 Step 3: 批量评估"])
    
    # ----- Tab 1: Prompt 配置 -----
    with tab1:
        col1, col2 = st.columns([1, 1])
        
        with col1:
            st.subheader("System Prompt (可选)")
            system_prompt = st.text_area(
                "系统提示词",
                height=150,
                placeholder="输入系统级指令，如角色设定等...",
                key="system_prompt"
            )
        
        with col2:
            st.subheader("User Prompt 模板")
            prompt_template = st.text_area(
                "用户提示词模板",
                height=150,
                placeholder="使用 {{字段名}} 作为占位符，如：\n\n分析以下聊天记录：\n{{chat_input}}\n\n用户背景：{{user_info}}",
                key="prompt_template"
            )
        
        # 识别占位符
        if prompt_template:
            placeholders = extract_placeholders(prompt_template)
            if placeholders:
                st.success(f"✅ 识别到 {len(placeholders)} 个占位符：`{'`, `'.join(placeholders)}`")
            else:
                st.warning("⚠️ 未识别到 {{}} 格式的占位符")
    
    # ----- Tab 2: 字段映射 -----
    with tab2:
        st.subheader("上传评估集")
        uploaded_file = st.file_uploader(
            "选择评估集文件",
            type=["xlsx", "xls", "csv"],
            help="支持 Excel (.xlsx/.xls) 和 CSV (.csv) 格式"
        )
        
        if uploaded_file:
            try:
                # 根据文件类型选择读取方式
                file_name = uploaded_file.name.lower()
                if file_name.endswith('.csv'):
                    df = pd.read_csv(uploaded_file)
                else:
                    df = pd.read_excel(uploaded_file)
                st.success(f"✅ 成功加载 {len(df)} 条数据")
                
                # 预览数据
                with st.expander("📊 预览评估集数据", expanded=True):
                    st.dataframe(df.head(10), use_container_width=True)
                
                # 字段映射
                prompt_template = st.session_state.get("prompt_template", "")
                placeholders = extract_placeholders(prompt_template)
                
                if placeholders:
                    st.subheader("🔗 字段映射")
                    st.caption("将 Prompt 中的占位符映射到评估集的字段")
                    
                    excel_columns = ["(不映射)"] + list(df.columns)
                    mapping = {}
                    
                    cols = st.columns(min(len(placeholders), 3))
                    for i, placeholder in enumerate(placeholders):
                        with cols[i % 3]:
                            selected = st.selectbox(
                                f"`{{{{{placeholder}}}}}`",
                                excel_columns,
                                key=f"map_{placeholder}"
                            )
                            if selected != "(不映射)":
                                mapping[placeholder] = selected
                    
                    # 保存映射到 session
                    st.session_state.mapping = mapping
                    st.session_state.df = df
                    
                    # 预览拼接后的 prompt
                    if mapping and len(df) > 0:
                        st.subheader("👀 预览拼接效果")
                        preview_idx = st.slider("选择预览行", 0, len(df)-1, 0)
                        preview_prompt = fill_prompt(prompt_template, mapping, df.iloc[preview_idx])
                        st.text_area("拼接后的 Prompt", preview_prompt, height=200, disabled=True)
                else:
                    st.warning("⚠️ 请先在 Step 1 中设置包含 {{}} 占位符的 Prompt 模板")
            
            except Exception as e:
                st.error(f"❌ 读取文件失败：{e}")
    
    # ----- Tab 3: 批量评估 -----
    with tab3:
        st.subheader("批量推理")
        
        # 检查前置条件
        ready = True
        if not api_key or not api_base:
            st.warning("⚠️ 请在侧边栏选择或添加模型配置")
            ready = False
        if not st.session_state.get("prompt_template"):
            st.warning("⚠️ 请在 Step 1 配置 Prompt 模板")
            ready = False
        if "df" not in st.session_state:
            st.warning("⚠️ 请在 Step 2 上传评估集")
            ready = False
        
        if ready:
            df = st.session_state.df
            mapping = st.session_state.get("mapping", {})
            prompt_template = st.session_state.prompt_template
            system_prompt = st.session_state.get("system_prompt", "")
            
            st.info(f"📊 评估集共 {len(df)} 条数据，已映射 {len(mapping)} 个字段")
            st.success(f"🤖 当前模型: **{model_name}** ({api_base})")
            
            # 选择评估范围
            col1, col2 = st.columns(2)
            with col1:
                start_idx = st.number_input("起始行", 0, len(df)-1, 0)
            with col2:
                end_idx = st.number_input("结束行", start_idx, len(df)-1, min(start_idx + 9, len(df)-1))
            
            eval_count = end_idx - start_idx + 1
            st.caption(f"将评估第 {start_idx} 到 {end_idx} 行，共 {eval_count} 条")
            
            # 开始评估按钮
            if st.button("🚀 开始批量评估", type="primary", use_container_width=True):
                # 生成所有 prompt
                prompts = []
                for i in range(start_idx, end_idx + 1):
                    filled = fill_prompt(prompt_template, mapping, df.iloc[i])
                    prompts.append(filled)
                
                st.session_state.prompts_generated = prompts
                
                # 调用 API
                client = OpenAI(base_url=api_base, api_key=api_key)
                
                progress_bar = st.progress(0, text="正在评估...")
                
                def update_progress(p):
                    progress_bar.progress(p, text=f"进度: {int(p*100)}%")
                
                with st.spinner("正在批量调用 API..."):
                    results = batch_evaluate(
                        prompts, client, model_name,
                        system_prompt if system_prompt else None,
                        temperature, max_tokens, max_workers,
                        progress_callback=update_progress
                    )
                
                st.session_state.results = results
                progress_bar.progress(1.0, text="✅ 完成!")
                st.success(f"✅ 评估完成！共处理 {len(results)} 条")
        
        # 展示结果
        if st.session_state.results:
            st.subheader("📋 评估结果")
            
            results = st.session_state.results
            df = st.session_state.df
            start_idx = int(st.session_state.get("start_idx", 0))
            
            # 构建结果 DataFrame
            result_data = []
            for i, res in enumerate(results):
                row_idx = start_idx + i
                row_data = {
                    "序号": row_idx,
                    "模型响应": res["response"],
                    "耗时(秒)": round(res["time"], 2)
                }
                # 添加原始数据字段
                if row_idx < len(df):
                    for col in df.columns:
                        row_data[f"[原]{col}"] = df.iloc[row_idx][col]
                result_data.append(row_data)
            
            result_df = pd.DataFrame(result_data)
            
            # 展示结果表格
            st.dataframe(result_df, use_container_width=True, height=400)
            
            # 导出结果
            st.subheader("💾 导出结果")
            
            # 生成 Excel
            output = BytesIO()
            with pd.ExcelWriter(output, engine='openpyxl') as writer:
                result_df.to_excel(writer, index=False, sheet_name='评估结果')
            
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            st.download_button(
                label="📥 下载评估结果 (Excel)",
                data=output.getvalue(),
                file_name=f"eval_results_{timestamp}.xlsx",
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                type="primary"
            )
            
            # 详细查看单条结果
            st.subheader("🔍 详细查看")
            view_idx = st.selectbox(
                "选择查看的结果",
                range(len(results)),
                format_func=lambda x: f"第 {start_idx + x} 行"
            )
            
            col1, col2 = st.columns(2)
            with col1:
                st.markdown("**输入 Prompt:**")
                st.text_area(
                    "prompt",
                    st.session_state.prompts_generated[view_idx],
                    height=300,
                    disabled=True,
                    label_visibility="collapsed"
                )
            with col2:
                st.markdown("**模型响应:**")
                st.text_area(
                    "response",
                    results[view_idx]["response"],
                    height=300,
                    disabled=True,
                    label_visibility="collapsed"
                )


if __name__ == "__main__":
    main()
