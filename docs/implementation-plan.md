# miiotpcApi 实施方案

> 基于 mijiaAPI v4.2.1 的子集包，专注于米家笔记本/PC 设备控制

## 一、项目概述

### 1.1 背景

mijiaAPI 是一个功能完整的米家设备控制 Python 包，支持所有米家设备类型。本项目 `miiotpcApi` 从中提取与笔记本/PC 设备控制相关的子集，形成一个轻量级、专注的包。

### 1.2 目标

- 仅保留笔记本/PC 设备控制所需的核心功能
- 提供简洁的 Python API 和 CLI（不含 MCP Server）
- 降低依赖复杂度，减少包体积
- 保持与 mijiaAPI 相同的认证和加密机制

### 1.3 参考源码位置

```
C:\Users\Bark\AppData\Local\uv\cache\archive-v0\TB_u9eOK0QSnoqjw\Lib\site-packages\mijiaAPI\
```

---

## 二、架构设计

### 2.1 包结构对比

```
mijiaAPI (原包, 8个模块)          miiotpcApi (新包, 6个模块)
├── __init__.py                   ├── __init__.py           # 精简导出
├── __main__.py                   ├── __main__.py           # 精简CLI
├── apis.py                       ├── api.py                # 核心API客户端 (精简)
├── devices.py                    ├── device.py             # PC设备封装 (新增高层抽象)
├── errors.py                     ├── errors.py             # 错误定义 (保留)
├── logger.py                     ├── logger.py             # 日志 (保留)
├── mcp_server.py                 └── miutils.py            # 加密工具 (保留)
├── miutils.py                    (不包含 mcp_server.py, version.py)
└── version.py
```

### 2.2 模块职责

| 模块 | 来源 | 变更类型 | 说明 |
|------|------|---------|------|
| `api.py` | `apis.py` | **精简** | 保留认证、设备列表、属性读写、动作执行；移除场景、耗材、统计 |
| `device.py` | `devices.py` | **重构** | 保留底层 MiotDevice；新增 PCDevice 高层抽象 |
| `errors.py` | `errors.py` | **保留** | 完整保留错误码映射和异常类 |
| `logger.py` | `logger.py` | **保留** | 仅改 logger 名为 `miiotpcApi` |
| `miutils.py` | `miutils.py` | **保留** | 加密工具完全保留 |
| `__main__.py` | `__main__.py` | **精简** | 保留 login/get/set/action，并将 PC 控制选项提升到顶层 |

> **不包含** `mcp_server.py`，不需要 MCP Server 功能。

---

## 三、详细实施方案

### 阶段一：项目初始化与基础设施（Step 1-2）

#### Step 1：创建项目骨架

创建 `pyproject.toml`：

```toml
[project]
name = "miiotpcApi"
version = "0.1.0"
description = "米家笔记本/PC设备控制 API"
requires-python = ">=3.10"
license = "MIT"
dependencies = [
    "pycryptodome>=3.23.0",
    "qrcode>=8.2",
    "requests>=2.32.5",
    "tzlocal>=5.3.1",
]

[project.scripts]
miiotpcApi = "miiotpcApi.__main__:cli"

[build-system]
requires = ["hatchling"]
build-backend = "hatchling.build"
```

> **依赖对比**：去掉了 `pillow`（qrcode 可选图片依赖）和 `fastmcp`（MCP Server 依赖），仅保留核心依赖。

#### Step 2：复制并适配基础模块

以下模块从 mijiaAPI 直接复制，仅做最小改动：

**2a. `miutils.py`** — 完全复制，无修改

**2b. `logger.py`** — 修改 logger 名称

```python
# 改动点：
# 原: logger = get_logger("mijiaAPI")
# 新:
logger = get_logger("miiotpcApi")
```

**2c. `errors.py`** — 完整复制，无修改

---

### 阶段二：核心 API 客户端（Step 3）

#### Step 3：精简 `api.py`

从 `apis.py` 精简而来。

**✅ 保留的方法：**

| 方法 | 说明 |
|------|------|
| `__init__()` | 初始化+加载认证 |
| `_init_session()` | 创建 HTTP Session |
| `available` | 检查认证是否有效 |
| `login()` / `QRlogin()` | 二维码登录 |
| `_refresh_token()` | 刷新 Token |
| `_request()` | 加密请求基础方法 |
| `get_devices_list()` | 获取设备列表 |
| `get_shared_devices_list()` | 获取共享设备 |
| `get_devices_prop()` | 读取设备属性 |
| `set_devices_prop()` | 设置设备属性 |
| `run_action()` | 执行设备动作 |
| `check_new_msg()` | Token 有效性检测 |

**🆕 新增方法：**

| 方法 | 说明 |
|------|------|
| `find_pc_devices(keyword)` | 按关键词筛选PC/笔记本设备 |

**❌ 移除的方法：**

| 方法 | 移除原因 |
|------|---------|
| `get_homes_list()` | 家庭管理 |
| `_get_devices_list(home_id)` | 简化设备获取 |
| `_get_home_owner()` | 家庭管理辅助 |
| `_add_home_id()` | 家庭管理辅助 |
| `get_scenes_list()` / `_get_scenes_list()` | 场景管理 |
| `run_scene()` | 场景管理 |
| `get_consumable_items()` / `_get_consumable_items()` | 耗材管理 |
| `get_statistics()` | 统计功能 |

**默认路径改动：**
- 原: `~/.config/mijia-api/auth.json`
- 新: `~/.config/miiotpc-api/auth.json`

详细实现规格见 [api-detail.md](api-detail.md)

---

### 阶段三：设备封装层（Step 4）

#### Step 4：创建 `device.py`

包含以下组件：

| 组件 | 来源 | 说明 |
|------|------|------|
| `DevProp` | 原样复制 | 属性描述符 |
| `DevAction` | 原样复制 | 动作描述符 |
| `MiotDevice` | 原 `mijiaDevice` 改名 | 底层通用设备封装 |
| `PCDevice` | **新增** | PC高层语义接口 |
| `get_device_info()` | 原样复制 | 获取设备 MIoT Spec |

**PCDevice 提供的接口：**

```python
pc = PCDevice(api, dev_name="我的笔记本")

# 电源控制
pc.power_on()           # 开机（优先动作，回退属性）
pc.power_off()          # 关机
pc.sleep()              # 睡眠
pc.is_on()              # 查询状态

# 系统控制
pc.sleep()              # 睡眠
pc.wake()               # 唤醒
pc.lock_screen()        # 锁屏

# 属性控制
pc.get_brightness()     # 屏幕亮度
pc.set_brightness(80)
pc.get_volume()         # 音量
pc.set_volume(50)

# 状态概览
pc.capabilities         # 支持的能力
pc.status               # 所有可读属性

# 通用透传
pc.get_prop("on")
pc.set_prop("on", True)
pc.run_action("power-on")
```

详细实现规格见 [device-detail.md](device-detail.md)

---

### 阶段四：CLI 入口（Step 5）

#### Step 5：精简 `__main__.py`

**✅ 保留的子命令：**

| 子命令 | 说明 |
|--------|------|
| `login` | 二维码登录 |
| `get` | 获取设备属性 |
| `set` | 设置设备属性 |
| `action` | 执行设备动作 |

**✅ 保留的选项：**

| 选项 | 说明 |
|------|------|
| `-l, --list_devices` | 列出所有设备 |
| `--get_device_info MODEL` | 获取设备规格 |

**🆕 新增的选项/子命令：**

| 选项/子命令 | 说明 |
|-------------|------|
| `--list_pc` | 仅列出PC/笔记本设备 |
| `pc` 子命令 | PC设备控制快捷操作 |

**❌ 移除的选项/子命令：**

| 选项/子命令 | 移除原因 |
|-------------|---------|
| `--list_homes` | 家庭管理 |
| `--list_scenes` | 场景管理 |
| `--list_consumable_items` | 耗材管理 |
| `--run_scene` | 场景执行 |
| `run` 子命令 | 小爱音箱控制 |
| `statistics` 子命令 | 统计功能 |
| `mcp` 子命令 | MCP Server |

详细实现规格见 [cli-detail.md](cli-detail.md)

---

### 阶段五：包导出（Step 6）

#### Step 6：创建 `__init__.py`

```python
from .api import miiotpcAPI
from .device import MiotDevice, PCDevice, get_device_info
from .errors import (
    APIError,
    DeviceActionError,
    DeviceGetError,
    DeviceNotFoundError,
    DeviceSetError,
    GetDeviceInfoError,
    LoginError,
    MultipleDevicesFoundError,
)
from .miutils import decrypt

__version__ = "0.1.0"

__all__ = [
    "miiotpcAPI",
    "MiotDevice",
    "PCDevice",
    "get_device_info",
    "APIError",
    "DeviceActionError",
    "DeviceGetError",
    "DeviceNotFoundError",
    "DeviceSetError",
    "GetDeviceInfoError",
    "LoginError",
    "MultipleDevicesFoundError",
    "decrypt",
    "__version__",
]
```

---

## 四、使用方式

### 4.1 Python API

```python
from miiotpcApi import miiotpcAPI, PCDevice, MiotDevice

api = miiotpcAPI()
api.login()

# 方式1: 高层 PCDevice（推荐）
pc = PCDevice(api, dev_name="我的笔记本")
pc.power_on()
pc.set_brightness(80)
print(pc.is_on())
print(pc.status)

# 方式2: 底层 MiotDevice（兼容原 mijiaAPI 用法）
device = MiotDevice(api, dev_name="我的笔记本")
device.set("on", True)
```

### 4.2 CLI

```bash
# 登录
miiotpcApi login

# 列出所有设备
miiotpcApi -l

# 仅列出PC设备
miiotpcApi --list_pc

# PC设备控制
miiotpcApi --dev_name "我的笔记本" --power on
miiotpcApi --dev_name "我的笔记本" --power off
miiotpcApi --dev_name "我的笔记本" --sleep
miiotpcApi --dev_name "我的笔记本" --power sleep
miiotpcApi --dev_name "我的笔记本" --status

# 通用属性操作
miiotpcApi get --dev_name "我的笔记本" --prop_name on
miiotpcApi set --dev_name "我的笔记本" --prop_name brightness --value 80
miiotpcApi action --dev_name "我的笔记本" --action_name power-on
```

---

## 五、目录结构（最终）

```
miiotpcApi/
├── pyproject.toml
├── README.md
├── LICENSE
├── docs/
│   ├── implementation-plan.md    # 本文档
│   ├── api-detail.md             # api.py 详细规格
│   ├── device-detail.md          # device.py 详细规格
│   └── cli-detail.md             # __main__.py 详细规格
├── src/
│   └── miiotpcApi/
│       ├── __init__.py
│       ├── __main__.py
│       ├── api.py
│       ├── device.py
│       ├── errors.py
│       ├── logger.py
│       └── miutils.py
└── tests/
    ├── test_api.py
    └── test_device.py
```

---

## 六、开发步骤清单

| 步骤 | 任务 | 优先级 | 预计工作量 |
|------|------|--------|-----------|
| 1 | 创建 pyproject.toml + 项目骨架 | P0 | 10 min |
| 2 | 复制 miutils.py / errors.py / logger.py | P0 | 5 min |
| 3 | 创建 api.py（精简版 apis.py） | P0 | 30 min |
| 4 | 创建 device.py（MiotDevice + PCDevice） | P0 | 40 min |
| 5 | 创建 __main__.py（精简版 CLI + 顶层 PC 控制选项） | P1 | 30 min |
| 6 | 创建 __init__.py | P0 | 5 min |
| 7 | 编写 README.md | P2 | 15 min |
| 8 | 基础测试 | P2 | 30 min |
| 9 | `uv sync` + `uv run miiotpcApi login` 验证 | P0 | 10 min |

**总计预估：约 2.5 小时**

---

## 七、注意事项

1. **认证文件路径**：默认改为 `~/.config/miiotpc-api/auth.json`，避免与 mijiaAPI 冲突
2. **PCDevice 能力检测**：需要实际接入PC设备后，根据其 MIoT Spec 调整 `_detect_capabilities()` 的匹配逻辑
3. **MIoT Spec 缓存**：设备规格信息缓存路径跟随 auth_data_path 的父目录
4. **小米 API 端点**：`https://api.mijia.tech/app` 是统一的，不会因包名改变而变化
5. **get_devices_list() 简化**：原版支持按 home_id 过滤，新版简化为获取全部设备
6. **PCDevice 是语义层**：其方法最终映射到 MIoT Spec 的属性/动作，具体映射取决于设备实际支持的 Spec
