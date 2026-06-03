"""
工具函数：日志、时间处理等
"""

import logging
import sys
from datetime import datetime


def setup_logger(name: str = "football_predictor", level: int = logging.INFO) -> logging.Logger:
    """配置日志器"""
    logger = logging.getLogger(name)
    logger.setLevel(level)

    if not logger.handlers:
        handler = logging.StreamHandler(sys.stdout)
        handler.setLevel(level)
        formatter = logging.Formatter(
            "[%(asctime)s] %(levelname)s - %(message)s",
            datefmt="%H:%M:%S",
        )
        handler.setFormatter(formatter)
        logger.addHandler(handler)

    return logger


logger = setup_logger()


def parse_date(date_str: str) -> datetime | None:
    """尝试多种日期格式解析"""
    formats = [
        "%d/%m/%y", "%d/%m/%Y", "%Y-%m-%d",
        "%d-%m-%Y", "%d-%m-%y", "%m/%d/%Y",
    ]
    for fmt in formats:
        try:
            return datetime.strptime(date_str.strip(), fmt)
        except (ValueError, AttributeError):
            continue
    return None
