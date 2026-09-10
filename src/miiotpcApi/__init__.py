"""米家 PC/笔记本设备控制 API。

miiotpcApi — 米家笔记本/PC 设备控制 API
Copyright (C) 2026 comor <304593790@qq.com>

本项目是 mijiaAPI（https://github.com/Do1e/mijia-api, GPL-3.0-or-later）
的衍生作品（精简子集）。原项目著作权归 Do1e <i@do1e.cn> 所有。

本程序是自由软件：你可以在自由软件基金会发布的 GNU 通用公共许可证第 3 版
（或任何更新版本）的条款下重新分发和/或修改它。本程序的分发是希望它有用，
但不提供任何担保。详情请见 <https://www.gnu.org/licenses/>。

完整的衍生声明与上游来源见项目根目录的 NOTICE 文件。
"""

from .api import miiotpcAPI
from .device import DevAction, DevProp, MiotDevice, PCDevice, get_device_info
from .version import version

__all__ = [
    "DevAction",
    "DevProp",
    "MiotDevice",
    "PCDevice",
    "get_device_info",
    "miiotpcAPI",
    "version",
]
