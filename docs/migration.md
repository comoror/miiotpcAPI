# 从 mijiaAPI 迁移到 miiotpcApi

## 概念映射

| mijiaAPI | miiotpcApi | 说明 |
|----------|-----------|------|
| `mijiaAPI` | `miiotpcAPI` | 类名改了，用法相同 |
| `mijiaDevice` | `MiotDevice` | 类名改了，用法相同 |
| — | `PCDevice` | 新增高层PC封装 |
| `~/.config/mijia-api/auth.json` | `~/.config/miiotpc-api/auth.json` | 默认路径不同 |
| `mijiaAPI` (包名) | `miiotpcApi` (包名) | import 路径不同 |

## 代码迁移

### 认证初始化

```python
# 原 mijiaAPI
from mijiaAPI import mijiaAPI
api = mijiaAPI()
api.login()

# 新 miiotpcApi（兼容）
from miiotpcApi import miiotpcAPI
api = miiotpcAPI()
api.login()

# 如果已有 mijiaAPI 的认证文件，可复用：
api = miiotpcAPI(auth_data_path="~/.config/mijia-api/auth.json")
```

### 设备控制

```python
# 原 mijiaAPI
from mijiaAPI import mijiaDevice
device = mijiaDevice(api, dev_name="我的笔记本")
device.set("on", True)
value = device.get("on")

# 新 miiotpcApi（底层兼容）
from miiotpcApi import MiotDevice
device = MiotDevice(api, dev_name="我的笔记本")
device.set("on", True)
value = device.get("on")

# 新 miiotpcApi（高层推荐）
from miiotpcApi import PCDevice
pc = PCDevice(api, dev_name="我的笔记本")
pc.power_on()
value = pc.is_on()
```

### 属性读写

```python
# 原 mijiaAPI（属性名带横线的需要替换）
device.set("brightness", 80)
device.set("color-temperature", 2700)  # 属性名中有横线

# 新 miiotpcApi（相同，横线自动转下划线别名）
device.set("brightness", 80)
device.set("color_temperature", 2700)  # 支持下划线别名
```

### 设备列表

```python
# 原 mijiaAPI
devices = api.get_devices_list()  # 包含所有设备
shared = api.get_shared_devices_list()  # 共享设备

# 新 miiotpcApi（相同）
devices = api.get_devices_list()  # 包含所有设备
shared = api.get_shared_devices_list()  # 共享设备

# 新增：筛选PC设备
pc_devices = api.find_pc_devices()
```

### 移除的功能

以下功能在 miiotpcApi 中**不可用**，如需要请继续使用 mijiaAPI：

```python
# ❌ 以下功能已移除

# 家庭管理
homes = api.get_homes_list()

# 场景管理
scenes = api.get_scenes_list()
api.run_scene(scene_id, home_id)

# 耗材管理
items = api.get_consumable_items()

# 统计功能
stats = api.get_statistics({...})

# 小爱音箱控制
from mijiaAPI.mcp_server import run_speaker_command
```

## CLI 迁移

```bash
# 原 mijiaAPI CLI
mijiaAPI login
mijiaAPI -l
mijiaAPI --list_homes
mijiaAPI --list_scenes
mijiaAPI get --dev_name "..." --prop_name on
mijiaAPI set --dev_name "..." --prop_name brightness --value 80
mijiaAPI mcp

# 新 miiotpcApi CLI
miiotpcApi login
miiotpcApi -l
miiotpcApi --list_pc
miiotpcApi --dev_name "..." --status
miiotpcApi --dev_name "..." --power on
miiotpcApi get --dev_name "..." --prop_name on
miiotpcApi set --dev_name "..." --prop_name brightness --value 80
# miiotpcApi mcp  ← 不可用
```

## 依赖对比

```toml
# mijiaAPI 依赖
dependencies = [
    "fastmcp>=3.4.2",        # ← 移除
    "pillow>=11.3.0",        # ← 移除
    "pycryptodome>=3.23.0",  # 保留
    "qrcode>=8.2",           # 保留
    "requests>=2.32.5",      # 保留
    "tzlocal>=5.3.1",        # 保留
]

# miiotpcApi 依赖
dependencies = [
    "pycryptodome>=3.23.0",
    "qrcode>=8.2",
    "requests>=2.32.5",
    "tzlocal>=5.3.1",
]
```

## 共存说明

miiotpcApi 和 mijiaAPI **可以同时安装**，因为包名不同：

```python
# 可以同时使用
from mijiaAPI import mijiaAPI as OldAPI   # 用于场景/耗材/统计
from miiotpcApi import miiotpcAPI as PCAPI  # 用于PC控制

old = OldAPI()
pc = PCAPI()
```

认证文件路径默认不同，不会互相影响：
- mijiaAPI: `~/.config/mijia-api/auth.json`
- miiotpcApi: `~/.config/miiotpc-api/auth.json`
