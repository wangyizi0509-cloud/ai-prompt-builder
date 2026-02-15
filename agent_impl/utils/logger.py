import logging
import os
import sys
from logging.handlers import RotatingFileHandler

# 日志文件路径
LOG_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "logs")
LOG_FILE = os.path.join(LOG_DIR, "backend.log")

def setup_logger():
    """
    配置全局日志系统，输出到控制台和本地文件
    """
    # 创建 root logger
    logger = logging.getLogger()
    logger.setLevel(logging.INFO)

    # 如果已经有 handler，说明已经初始化过，不再重复添加
    if logger.handlers:
        return logger

    # 日志格式
    formatter = logging.Formatter(
        '[%(asctime)s] [%(levelname)s] [%(name)s] - %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S'
    )

    # 1. 控制台 Handler
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setFormatter(formatter)
    logger.addHandler(console_handler)

    # 2. 文件 Handler (支持自动切分，保留最近 5 个，每个最大 10MB)
    # In some container runtimes the app directory can be read-only.
    # Fail open: keep stdout logging available instead of crashing app startup.
    try:
        if not os.path.exists(LOG_DIR):
            os.makedirs(LOG_DIR)
        file_handler = RotatingFileHandler(
            LOG_FILE,
            maxBytes=10 * 1024 * 1024,
            backupCount=5,
            encoding='utf-8'
        )
        file_handler.setFormatter(formatter)
        logger.addHandler(file_handler)
        logger.info(f"Logging initialized. Log file: {LOG_FILE}")
    except Exception as e:
        logger.warning("File logging disabled: %s", e)
        logger.info("Logging initialized with stdout only")
    return logger

# 默认初始化
logger = setup_logger()

def get_logger(name):
    """获取指定模块名的 logger"""
    return logging.getLogger(name)
