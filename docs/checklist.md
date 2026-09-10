# 实施检查清单

> 逐文件、逐步骤的实施清单，直接对照执行

## 文件清单

| 文件 | 行数(估) | 来源 | 状态 |
|------|---------|------|------|
| `pyproject.toml` | ~25 | 新建 | ☐ |
| `src/miiotpcApi/__init__.py` | ~30 | 新建 | ☐ |
| `src/miiotpcApi/version.py` | 1 | 新建 | ☐ |
| `src/miiotpcApi/miutils.py` | ~60 | 直接复制 | ☐ |
| `src/miiotpcApi/errors.py` | ~80 | 直接复制 | ☐ |
| `src/miiotpcApi/logger.py` | ~50 | 复制+改名 | ☐ |
| `src/miiotpcApi/api.py` | ~250 | 精简复制 | ☐ |
| `src/miiotpcApi/device.py` | ~400 | 精简+新增 | ☐ |
| `src/miiotpcApi/__main__.py` | ~300 | 精简复制 | ☐ |

---

## Step 1：pyproject.toml

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

[project.optional-dependencies]
dev = [
    "pytest>=7.0",
]

[project.scripts]
miiotpcApi = "miiotpcApi.__main__:cli"

[build-system]
requires = ["hatchling"]
build-backend = "hatchling.build"
```

**检查项：**
- [ ] 无 `fastmcp` 依赖
- [ ] 无 `pillow` 依赖
- [ ] 入口点为 `miiotpcApi.__main__:cli`
- [ ] Python >= 3.10

---

## Step 2：version.py

```python
version = "0.1.0"
```

**检查项：**
- [ ] 仅一行

---

## Step 3：miutils.py

**来源：** 直接从 `C:\Users\Bark\AppData\Local\uv\cache\archive-v0\TB_u9eOK0QSnoqjw\Lib\site-packages\mijiaAPI\miutils.py` 复制

**改动：** 无

**检查项：**
- [ ] 包含 `gen_nonce()`
- [ ] 包含 `get_signed_nonce()`
- [ ] 包含 `gen_enc_signature()`
- [ ] 包含 `generate_enc_params()`
- [ ] 包含 `encrypt_rc4()`
- [ ] 包含 `decrypt_rc4()`
- [ ] 包含 `decrypt()`
- [ ] 导入 `from Crypto.Cipher import ARC4`

---

## Step 4：errors.py

**来源：** 直接从 `mijiaAPI/errors.py` 复制

**改动：** 无

**检查项：**
- [ ] 包含 `ERROR_CODE` 字典（~50个错误码）
- [ ] 包含所有异常类：`LoginError`, `APIError`, `DeviceNotFoundError`, `MultipleDevicesFoundError`, `DeviceGetError`, `DeviceSetError`, `DeviceActionError`, `GetDeviceInfoError`

---

## Step 5：logger.py

**来源：** 从 `mijiaAPI/logger.py` 复制

**改动：** 一行

```python
# 原: logger = get_logger("mijiaAPI")
# 改为:
logger = get_logger("miiotpcApi")
```

**检查项：**
- [ ] 包含 `ColorFormatter` 类
- [ ] 包含 `get_logger()` 函数
- [ ] logger 名称为 `"miiotpcApi"`
- [ ] 默认级别为 `INFO`

---

## Step 6：api.py

**来源：** 从 `mijiaAPI/apis.py` 精简

**类名：** `miiotpcAPI`（原 `mijiaAPI`）

**保留方法（逐个确认）：**
- [ ] `__init__(auth_data_path=None)` — 默认路径改为 `~/.config/miiotpc-api/auth.json`
- [ ] `_init_session()`
- [ ] `available` 属性
- [ ] `pass_o` 属性
- [ ] `user_agent` 属性
- [ ] `deviceId` 属性
- [ ] `_parse_service_ret()`
- [ ] `_handle_ret()`
- [ ] `_print_qr()` 静态方法
- [ ] `_save_auth_data()`
- [ ] `_get_location()`
- [ ] `_refresh_token()`
- [ ] `login()` → 调用 `QRlogin()`
- [ ] `QRlogin()`
- [ ] `_get_qr_login_data()`
- [ ] `_complete_qr_login()`
- [ ] `_request(uri, data, refresh_token=True)`
- [ ] `check_new_msg(begin_at, refresh_token)`
- [ ] `get_devices_list()` — 简化，无 home_id 参数
- [ ] `get_shared_devices_list()`
- [ ] `get_devices_prop(data)`
- [ ] `set_devices_prop(data)`
- [ ] `run_action(data)`
- [ ] `find_pc_devices(keyword=None)` — **新增**

**移除方法（逐个确认）：**
- [ ] ~~`get_homes_list()`~~
- [ ] ~~`_get_devices_list(home_id)`~~
- [ ] ~~`_get_home_owner(home_id)`~~
- [ ] ~~`_add_home_id(data, home_id)`~~
- [ ] ~~`_get_scenes_list(home_id)`~~
- [ ] ~~`get_scenes_list(home_id)`~~
- [ ] ~~`run_scene(scene_id, home_id)`~~
- [ ] ~~`_get_consumable_items(home_id)`~~
- [ ] ~~`get_consumable_items(home_id)`~~
- [ ] ~~`get_statistics(data)`~~

**`get_devices_list()` 改动要点：**
- 移除 `home_id` 参数
- 直接调用 `_get_all_devices()` 或合并主设备和共享设备
- 不再需要 `get_homes_list()`

**`find_pc_devices()` 新增逻辑：**
```python
def find_pc_devices(self, keyword=None) -> list:
    devices = self.get_devices_list()
    pc_keywords = {"pc", "电脑", "笔记本", "laptop", "desktop", "notebook"}
    if keyword:
        pc_keywords.add(keyword.lower())
    return [
        d for d in devices
        if any(kw in d.get("name", "").lower() or
               kw in d.get("model", "").lower()
               for kw in pc_keywords)
    ]
```

---

## Step 7：device.py

**来源：** 从 `mijiaAPI/devices.py` 精简 + 新增

**保留组件（逐个确认）：**

### DevProp 类
- [ ] `__init__(prop_dict)` — name, desc, type, rw, range, value_list, method
- [ ] `__str__()`

### DevAction 类
- [ ] `__init__(act_dict)` — name, desc, method
- [ ] `__str__()`

### MiotDevice 类（原 mijiaDevice）
- [ ] `__init__(api, did=None, dev_name=None, sleep_time=0.5)`
- [ ] `__str__()`
- [ ] `get(name)` — 读取属性
- [ ] `set(name, value)` — 设置属性（含类型验证）
- [ ] `_validate_value(prop, value)` — 内部验证方法（可选提取）
- [ ] `__getattr__(name)` — 魔术方法读取
- [ ] `__setattr__(name, value)` — 魔术方法设置
- [ ] `run_action(name, value=None, **kwargs)` — 执行动作

### get_device_info() 函数
- [ ] `get_device_info(device_model, cache_path=None)` — 完整复制

### 辅助函数
- [ ] `_deduplicate_names(items, iid_key)` — 完整复制

**新增 PCDevice 类（逐项确认）：**

### PCDevice 初始化
- [ ] `__init__(api, did=None, dev_name=None, sleep_time=0.5)`
- [ ] 内部创建 `MiotDevice` 实例
- [ ] 调用 `_detect_capabilities()`

### 能力检测
- [ ] `_detect_capabilities()` — 遍历 prop_list 和 action_list
- [ ] 属性匹配: on/power → power, brightness → brightness, volume → volume, lock → lock
- [ ] 动作匹配: power-on/turn-on/boot → power_on, sleep/suspend → sleep, wake → wake
- [ ] 初始化 `self._capabilities` 字典

### 属性方法
- [ ] `name` 属性 → `self._device.name`
- [ ] `model` 属性 → `self._device.model`
- [ ] `did` 属性 → `self._device.did`
- [ ] `capabilities` 属性 → 能力字典副本
- [ ] `status` 属性 → 状态概览字典
- [ ] `spec` 属性 → `str(self._device)`

### 电源控制
- [ ] `power_on()` — 优先动作，回退属性
- [ ] `power_off()` — 优先动作，回退属性
- [ ] `is_on()` — 查询电源状态

### 系统控制
- [ ] `sleep()` — 睡眠（动作或属性）
- [ ] `wake()` — 唤醒
- [ ] `lock_screen()` — 锁屏（动作或属性）

### 属性控制
- [ ] `get_brightness()` — 获取亮度
- [ ] `set_brightness(value)` — 设置亮度
- [ ] `get_volume()` — 获取音量
- [ ] `set_volume(value)` — 设置音量

### 通用接口
- [ ] `get_prop(name)` — 透传到 MiotDevice.get()
- [ ] `set_prop(name, value)` — 透传到 MiotDevice.set()
- [ ] `run_action(name, value=None, **kwargs)` — 透传到 MiotDevice.run_action()

### 辅助方法
- [ ] `_check_capability(cap, action_desc)` — 能力检查
- [ ] `__str__()` — 设备信息字符串

---

## Step 8：__main__.py

**来源：** 从 `mijiaAPI/__main__.py` 精简

**保留子命令（逐个确认）：**
- [ ] `login` — 二维码登录
- [ ] `get` — 获取属性
- [ ] `set` — 设置属性
- [ ] `action` — 执行动作

**保留选项（逐个确认）：**
- [ ] `-v, --version`
- [ ] `-p, --auth_path`（默认 `~/.config/miiotpc-api/auth.json`）
- [ ] `-l, --list_devices`
- [ ] `--get_device_info MODEL`

**新增选项/子命令（逐个确认）：**
- [ ] `--list_pc` — 筛选PC设备
- [ ] `pc` 子命令 — PC控制
  - [ ] `--list` — 列出PC设备
  - [ ] `--did` / `--dev_name` — 设备标识（互斥）
  - [ ] `--power on/sleep/off` — 唤醒/开机、睡眠、关机
  - [ ] `--status` — 状态概览

**移除子命令/选项（逐个确认）：**
- [ ] ~~`mcp` 子命令~~
- [ ] ~~`run` 子命令~~
- [ ] ~~`statistics` 子命令~~
- [ ] ~~`--list_homes`~~
- [ ] ~~`--list_scenes`~~
- [ ] ~~`--list_consumable_items`~~
- [ ] ~~`--run_scene`~~

**辅助函数（逐个确认）：**
- [ ] `json_object(value)` — JSON 参数解析
- [ ] `init_api(auth_path)` — API 初始化+认证检查
- [ ] `get_devices_list(api, verbose)` — 设备列表打印
- [ ] `get_pc_devices(api, verbose)` — PC设备列表打印
- [ ] `pc_action_handler(api, args)` — PC控制处理
- [ ] `handle_get(api, args)` — get 子命令处理
- [ ] `handle_set(api, args)` — set 子命令处理
- [ ] `handle_action(api, args)` — action 子命令处理
- [ ] `main(args)` — 主入口
- [ ] `cli()` — CLI 入口点

---

## Step 9：__init__.py

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
```

**检查项：**
- [ ] 导出 `miiotpcAPI`
- [ ] 导出 `MiotDevice`, `PCDevice`, `get_device_info`
- [ ] 导出所有异常类
- [ ] 导出 `decrypt`
- [ ] 定义 `__version__`
- [ ] 无 `mijiaAPI`, `mijiaDevice` 引用

---

## 最终验证

### 安装验证

```bash
cd e:\Work.py\miiotpcApi
uv sync
uv run miiotpcApi --version
# 预期: miiotpcApi 0.1.0
```

### 功能验证

```bash
# 登录
uv run miiotpcApi login
# 预期: 显示二维码

# 列出设备
uv run miiotpcApi -l
# 预期: 显示所有设备

# 列出PC设备
uv run miiotpcApi --list_pc
# 预期: 显示PC/笔记本设备

# 查看设备规格
uv run miiotpcApi --get_device_info <MODEL>
# 预期: 显示设备属性和动作

# PC控制
uv run miiotpcApi --dev_name "..." --status
# 预期: 显示状态概览
```

### 测试验证

```bash
uv run pytest tests/ -v
# 预期: 所有测试通过
```
