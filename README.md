# miiotpcApi

米家笔记本/PC 设备控制 API 与 CLI。

本项目是 [mijiaAPI](https://github.com/Do1e/mijia-api) 的**精简子集**，只保留控制
笔记本/PC 设备所需的能力，去掉了 MCP Server、家庭、场景、耗材、统计、小爱音箱
等与笔记本控制无关的部分。

[![License: GPL v3](https://img.shields.io/badge/License-GPLv3-blue.svg)](https://www.gnu.org/licenses/gpl-3.0)
[![Python](https://img.shields.io/badge/python-3.10%2B-blue.svg)](https://www.python.org/downloads/)
[![PyPI](https://img.shields.io/badge/PyPI-miiotpcApi-blue.svg)](https://pypi.org/project/miiotpcApi/)

**项目地址：<https://github.com/comoror/miiotpcAPI>**

> ⚠️ 本项目与小米公司无任何关联、授权或赞助关系，是一个独立的第三方社区项目。
> "Xiaomi"、"米家"、"MIoT" 等是小米公司的商标。

## 功能

- 米家账号二维码登录，Token 自动刷新
- 列出所有米家设备 / 筛选笔记本设备
- 笔记本语义化控制：唤醒/开机、睡眠、关机
- 查询工作状态、CPU 温度、电池电量、充电状态
- 通用 MIoT 属性读写与动作执行
- 查看任意设备型号的 MIoT Spec（无需登录）
- 提供 Python API 与 CLI 两种使用方式

## 安装

```bash
pip install miiotpcApi
# 或使用 uv
uv add miiotpcApi
```

要求 Python >= 3.10。

## 快速开始

### CLI

```bash
# 首次使用：扫码登录（认证文件默认保存到 ~/.config/miiotpc-api/auth.json）
miiotpcApi login

# 列出笔记本设备
miiotpcApi --list-pc

# 查看状态概览
miiotpcApi --dev-name "我的笔记本" --status

# 电源控制
miiotpcApi --dev-name "我的笔记本" --power on     # 唤醒/开机
miiotpcApi --dev-name "我的笔记本" --power sleep  # 睡眠
miiotpcApi --dev-name "我的笔记本" --power off    # 关机

# 查询状态
miiotpcApi --dev-name "我的笔记本" --temperature
miiotpcApi --dev-name "我的笔记本" --battery
miiotpcApi --dev-name "我的笔记本" --charging-state
```

### Python API

```python
from miiotpcApi import miiotpcAPI, PCDevice

api = miiotpcAPI()
api.login()  # 首次需要扫码

pc = PCDevice(api, dev_name="我的笔记本")

pc.power_on()            # 唤醒/开机
pc.sleep()               # 睡眠
pc.power_off()           # 关机

print(pc.is_on())            # True = 运行中
print(pc.get_temperature())  # CPU 温度
print(pc.get_battery_level())# 电池电量
print(pc.status)             # 状态概览
```

## 支持的 MIoT 能力

以小米笔记本为例，常见 Spec（`urn:miot-spec-v2:device:laptop`）支持：

| 属性 | 读写 | 说明 |
|------|------|------|
| `status` | 只读 | 工作状态枚举（1 唤醒中 / 2 关机 / 3 睡眠 / 4 关机中 / 6 进入睡眠中 / 8 运行中）|
| `temperature` | 只读 | CPU 温度（°C）|
| `battery-level` | 只读 | 电池电量（%）|
| `charging-state` | 只读 | 1 插电 / 2 电池供电 |

| 动作 | 说明 |
|------|------|
| `turn-on` | 唤醒/开机 |
| `turn-off` | 关机 |
| `sleep-mode-on` | 睡眠 |

具体能力因设备型号而异，可用 `miiotpcApi --get-device-info <model>` 查看任意型号的
完整 Spec（无需登录）。

## 许可证

本项目采用 **GNU General Public License v3.0 or later（GPL-3.0-or-later）** 发布，
详见 [LICENSE](LICENSE) 文件。

**重要：本项目是 mijiaAPI 的衍生作品。** 原项目作者 Do1e 保留其原始代码的著作权，
原项目同样以 GPL-3.0-or-later 发布。根据 GPL 的 copyleft 条款，本项目必须沿用
相同许可证。完整的衍生声明、上游组件来源与商标声明见 [NOTICE](NOTICE) 文件。

部分文件继承自更上游的开源项目，其著作权归原作者所有：

| 文件/内容 | 原始来源 | 作者 | 许可证 |
|-----------|----------|------|--------|
| `miutils.py` | [Squachen/micloud](https://github.com/Squachen/micloud) | Sammy Svensson | MIT |
| `ERROR_CODE` 错误码表 | [kekeandzeyu/ha_xiaomi_home](https://github.com/kekeandzeyu/ha_xiaomi_home) | — | 参考来源 |

## 致谢

- [Do1e/mijia-api](https://github.com/Do1e/mijia-api) — 本项目的基础，感谢原作者的开源工作
- [Squachen/micloud](https://github.com/Squachen/micloud) — 提供加密与签名实现
- [kekeandzeyu/ha_xiaomi_home](https://github.com/kekeandzeyu/ha_xiaomi_home) — 错误码对照数据
- [MIoT Spec](https://home.miot-spec.com/) — 小米官方设备规格平台

## 免责声明

本软件按"现状"提供，不提供任何明示或暗示的担保。使用本软件控制实体设备可能产生
不可预见的后果，风险由使用者自行承担。作者不对因使用本软件造成的任何损失负责。
