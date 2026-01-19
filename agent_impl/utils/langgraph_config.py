"""
LangGraph 配置工具
提供统一的配置管理，支持本地和云端切换
"""
import os
from dotenv import load_dotenv

load_dotenv()

DEBUG_MODE = os.getenv("DEBUG_MODE", "0") == "1"

if DEBUG_MODE:
    LANGGRAPH_URL = os.getenv("LANGGRAPH_LOCAL_URL", "http://127.0.0.1:2024")
    LANGGRAPH_API_KEY = os.getenv("LANGGRAPH_LOCAL_API_KEY", "")
    ASSISTANT_ID = os.getenv("LANGGRAPH_LOCAL_ASSISTANT_ID", "crushe_agent")
else:
    LANGGRAPH_URL = os.getenv("LANGGRAPH_CLOUD_URL", "https://your-deployment-id.us.langgraph.app")
    LANGGRAPH_API_KEY = os.getenv("LANGGRAPH_CLOUD_API_KEY", "")
    ASSISTANT_ID = os.getenv("LANGGRAPH_CLOUD_ASSISTANT_ID", "crushe_agent")


from utils.logger import get_logger

logger = get_logger("config")

def print_config():
    """打印当前配置信息"""
    if DEBUG_MODE:
        logger.info(f"DEBUG_MODE=1: Using local LangGraph server at {LANGGRAPH_URL}")
    else:
        logger.info(f"DEBUG_MODE=0: Using LangGraph Cloud at {LANGGRAPH_URL}")
