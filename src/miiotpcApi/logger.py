# miiotpcApi — 米家笔记本/PC 设备控制 API
# Copyright (C) 2026 comor <304593790@qq.com>
#
# 本文件是 mijiaAPI（https://github.com/Do1e/mijia-api, GPL-3.0-or-later）
# 的衍生作品。原项目著作权归 Do1e <i@do1e.cn> 所有。
#
# 本程序是自由软件：你可以在自由软件基金会发布的 GNU 通用公共许可证第 3 版
# （或任何更新版本）的条款下重新分发和/或修改它。本程序的分发是希望它有用，
# 但不提供任何担保。详情请见 <https://www.gnu.org/licenses/>。
#
# 完整的衍生声明与上游来源见项目根目录的 NOTICE 文件。

import logging
import sys


class ColorFormatter(logging.Formatter):
    COLORS = {
        "DEBUG": "\033[36m",      # 青色
        "INFO": "\033[32m",       # 绿色
        "WARNING": "\033[33m",    # 黄色
        "ERROR": "\033[31m",      # 红色
        "CRITICAL": "\033[1;31m", # 加粗红色
        "RESET": "\033[0m",       # 重置颜色
    }

    def __init__(self, fmt=None, datefmt=None, style='%'):
        super().__init__(fmt, datefmt, style)
        self.use_colors = sys.stdout.isatty()

    def format(self, record):
        log_message = super().format(record)
        if self.use_colors:
            color_code = self.COLORS.get(record.levelname, self.COLORS["RESET"])
            return f"{color_code}{log_message}{self.COLORS['RESET']}"
        return log_message

def get_logger(name: str) -> logging.Logger:
    logger = logging.getLogger(name)
    console_handler = logging.StreamHandler()
    formatter = ColorFormatter(
        "%(asctime)s.%(msecs)03d - %(name)s - %(levelname)s: %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )
    console_handler.setFormatter(formatter)
    logger.addHandler(console_handler)
    return logger

logger = get_logger("miiotpcApi")
logger.setLevel(logging.INFO)
