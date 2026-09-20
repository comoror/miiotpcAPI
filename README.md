# miiotpcApi

米家笔记本/PC 设备控制 API 与 CLI。

本项目是 [mijiaAPI](https://github.com/Do1e/mijia-api) 的**精简子集**，只保留控制
笔记本/PC 设备所需的能力，去掉了家庭、场景、耗材、统计、小爱音箱等与笔记本
控制无关的部分。

0.2.0 起新增了一个**为 AI agent 定制的 MCP server**（`miiotpcApi-mcp`）。它不是
上游那份通用 MCP Server 的照搬，而是只针对笔记本查询/控制、且返回**已解读结果**
的精简实现，依赖是可选的，不装不影响 CLI 与 Python API。

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
- 提供 **Python API、CLI、MCP server** 三种使用方式
- MCP server 返回**已解读的中文结果**，AI agent 无需自己翻译 MIoT 枚举

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

### MCP server（供 AI agent 调用）

MCP 依赖是**可选**的，需要额外安装：

```bash
pip install "miiotpcApi[mcp]"
```

注册到 Claude Code：

```bash
claude mcp add --transport stdio miiotpc \
  -- uvx --from "miiotpcApi[mcp]@latest" miiotpcApi-mcp
```

> **必须带 `@latest` 或固定版本号，不要写裸 `miiotpcApi[mcp]`。**
> 实测裸 spec 会被 uv 解析到 **0.1.0**，而旧版本没有 `miiotpcApi-mcp` 入口，
> server 根本起不来。以下写法均正确解析到 0.2.0：
> `"miiotpcApi[mcp]@latest"`、`"miiotpcApi[mcp]==0.2.0"`、`"miiotpcApi[mcp]>=0.2.0"`。
> 想锁定版本就用 `==0.2.0`；想跟随更新就用 `@latest`。

暴露 5 个工具：

| 工具 | 用途 |
|------|------|
| `list_devices` | 列出笔记本设备（did / 名称 / 型号 / 联网状态）|
| `get_power_status` | 查询是否开机；不传 `did` 则批量查全部 |
| `get_full_status` | 完整状态：运行状态 + 温度 + 电量 + 充电 |
| `set_power` | 唤醒开机 / 睡眠 / 关机 |
| `get_device_spec` | 查 MIoT Spec（**免认证**）|

**所有工具返回已解读的中文文本**，而不是原始枚举值。例如不会只给
`status: 3`，而是给「已睡眠（status=3，非运行中）」，并说明关机/睡眠设备的
温度与电量由主板 EC 上报、依然是实时值。

> **为什么这样做**：MIoT 的 `status` 是枚举、`isOnline` 是联网状态，二者正交
> 且都容易被误读。如果工具只返回裸数据，调用方几乎必然把「关机设备的温度」
> 当成过期快照丢掉——而实际上关机后主板 EC 仍在工作，那些数值是实时的。
> 把解读写进返回值，领域规则就落在了可测试的代码里。

server **不提供登录工具**：二维码扫码必须由人完成，暴露成工具只会诱使
AI agent 调用一个必然阻塞的接口。认证失效时工具会返回提示，让用户自行执行
`miiotpcApi login`。

`set_power` 有**真实世界副作用**，在 MCP 工具元数据中标记为 destructive，
宿主可以对该工具单独设权限审批；其余查询工具标记为只读。

## 支持的 MIoT 能力

以小米笔记本为例，常见 Spec（`urn:miot-spec-v2:device:laptop`）支持：

| 属性 | 读写 | 说明 |
|------|------|------|
| `status` | 只读 | 工作状态枚举。**8=运行中，非 8 即非运行中**（1=正在唤醒 / 2=已关机 / 3=已睡眠 / 4=正在关机 / 6=正在进入睡眠）|
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
