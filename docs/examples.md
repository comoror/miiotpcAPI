# 代码示例

## 一、基础用法

### 1.1 登录并列出设备

```python
from miiotpcApi import miiotpcAPI

api = miiotpcAPI()
api.login()  # 首次需要扫码

# 列出所有设备
devices = api.get_devices_list()
for dev in devices:
    online = "在线" if dev.get("isOnline") else "离线"
    print(f"{dev['name']} ({dev['model']}) - {online}")
```

### 1.2 筛选PC设备

```python
from miiotpcApi import miiotpcAPI

api = miiotpcAPI()  # 假设已登录

# 自动筛选PC/笔记本设备
pc_devices = api.find_pc_devices()
for dev in pc_devices:
    print(f"PC设备: {dev['name']} (did: {dev['did']})")

# 使用自定义关键词
xiaomi_devices = api.find_pc_devices(keyword="小米")
```

---

## 二、PCDevice 高层接口

### 2.1 电源控制

```python
from miiotpcApi import miiotpcAPI, PCDevice

api = miiotpcAPI()
pc = PCDevice(api, dev_name="我的笔记本")

# 查看支持的能力
print(pc.capabilities)
# {'power': True, 'sleep': True, 'brightness': True, ...}

# 开机
pc.power_on()

# 关机
pc.power_off()

# 睡眠
pc.sleep()

# 查询电源状态
if pc.is_on():
    print("PC已开机")
else:
    print("PC已关机")
```

### 2.2 系统控制

```python
from miiotpcApi import miiotpcAPI, PCDevice

api = miiotpcAPI()
pc = PCDevice(api, dev_name="我的笔记本")

# 睡眠
pc.sleep()

# 唤醒
pc.wake()

# 锁屏
pc.lock_screen()
```

### 2.3 属性控制

```python
from miiotpcApi import miiotpcAPI, PCDevice

api = miiotpcAPI()
pc = PCDevice(api, dev_name="我的笔记本")

# 屏幕亮度
brightness = pc.get_brightness()
print(f"当前亮度: {brightness}")
pc.set_brightness(80)

# 音量
volume = pc.get_volume()
print(f"当前音量: {volume}")
pc.set_volume(50)
```

### 2.4 状态概览

```python
from miiotpcApi import miiotpcAPI, PCDevice

api = miiotpcAPI()
pc = PCDevice(api, dev_name="我的笔记本")

# 获取完整状态
status = pc.status
print(f"设备: {status['name']}")
print(f"型号: {status['model']}")
print(f"能力: {status['capabilities']}")
for key, value in status.items():
    if key not in ('name', 'model', 'did', 'capabilities'):
        print(f"  {key}: {value}")

# 查看设备规格
print(pc.spec)
```

---

## 三、MiotDevice 通用接口

### 3.1 基础属性操作

```python
from miiotpcApi import miiotpcAPI, MiotDevice

api = miiotpcAPI()
device = MiotDevice(api, dev_name="我的笔记本")

# 读取属性
value = device.get("on")
print(f"电源状态: {value}")

# 设置属性
device.set("on", True)

# 使用魔术方法
print(device.on)       # 等价于 device.get("on")
device.on = False      # 等价于 device.set("on", False)

# 属性名中的横线自动转下划线
device.set("brightness", 80)
device.set("color_temperature", 2700)
```

### 3.2 动作执行

```python
from miiotpcApi import miiotpcAPI, MiotDevice

api = miiotpcAPI()
device = MiotDevice(api, dev_name="我的笔记本")

# 执行动作（无参数）
device.run_action("power-on")

# 执行动作（带参数）
device.run_action("reboot", value=[1])  # value 是列表
```

### 3.3 查看设备规格

```python
from miiotpcApi import miiotpcAPI, MiotDevice

api = miiotpcAPI()
device = MiotDevice(api, dev_name="我的笔记本")

# 查看所有属性
for name, prop in device.prop_list.items():
    if "_" not in name:  # 跳过别名
        print(f"{name}: {prop.desc} ({prop.type}, {prop.rw})")

# 查看所有动作
for name, action in device.action_list.items():
    print(f"{name}: {action.desc}")
```

### 3.4 批量属性操作

```python
from miiotpcApi import miiotpcAPI

api = miiotpcAPI()

# 批量读取
results = api.get_devices_prop([
    {"did": "123", "siid": 2, "piid": 1},
    {"did": "123", "siid": 2, "piid": 2},
])
for r in results:
    print(f"siid={r['siid']}, piid={r['piid']}: {r['value']}")

# 批量设置
results = api.set_devices_prop([
    {"did": "123", "siid": 2, "piid": 1, "value": True},
    {"did": "123", "siid": 2, "piid": 2, "value": 80},
])
for r in results:
    print(f"siid={r['siid']}, piid={r['piid']}: {r['message']}")
```

---

## 四、错误处理

### 4.1 完整错误处理示例

```python
from miiotpcApi import miiotpcAPI, PCDevice
from miiotpcApi.errors import (
    LoginError, APIError,
    DeviceNotFoundError, MultipleDevicesFoundError,
    DeviceGetError, DeviceSetError, DeviceActionError,
)

def control_pc(dev_name: str, action: str):
    """PC控制的完整错误处理示例"""
    api = miiotpcAPI()

    # 认证错误
    try:
        if not api.available:
            api._refresh_token()
    except LoginError:
        print("认证失败，正在重新登录...")
        api.login()

    # 设备初始化错误
    try:
        pc = PCDevice(api, dev_name=dev_name)
    except DeviceNotFoundError:
        print(f"未找到设备: {dev_name}")
        print("可用设备:")
        for d in api.get_devices_list():
            print(f"  - {d['name']}")
        return
    except MultipleDevicesFoundError as e:
        print(f"找到多个设备: {e}")
        print("请使用 did 参数精确指定")
        return

    # 设备操作错误
    try:
        if action == "on":
            pc.power_on()
            print(f"{pc.name} 已开机")
        elif action == "off":
            pc.power_off()
            print(f"{pc.name} 已关机")
        elif action == "sleep":
            pc.sleep()
            print(f"{pc.name} 已睡眠")
        elif action == "wake":
            pc.wake()
            print(f"{pc.name} 已唤醒")
        elif action == "status":
            print(f"设备: {pc.name}")
            print(f"状态: {pc.status}")
    except NotImplementedError as e:
        print(f"操作不支持: {e}")
    except DeviceGetError as e:
        print(f"读取失败: {e}")
    except DeviceSetError as e:
        print(f"设置失败: {e}")
    except DeviceActionError as e:
        print(f"动作执行失败: {e}")
    except APIError as e:
        code, message = e.args
        print(f"API错误 [{code}]: {message}")

# 使用
control_pc("我的笔记本", "on")
```

---

## 五、CLI 使用示例

### 5.1 基础操作

```bash
# 登录
miiotpcApi login

# 列出所有设备
miiotpcApi -l

# 仅列出PC设备
miiotpcApi --list_pc

# 查看设备规格
miiotpcApi --get_device_info xiaomi.pc.v1
```

### 5.2 PC控制

```bash
# 查看状态
miiotpcApi --dev_name "我的笔记本" --status

# 电源控制
miiotpcApi --dev_name "我的笔记本" --power on
miiotpcApi --dev_name "我的笔记本" --power off
miiotpcApi --dev_name "我的笔记本" --power sleep

# 系统控制
miiotpcApi --dev_name "我的笔记本" --power sleep
miiotpcApi --dev_name "我的笔记本" --wake
miiotpcApi --dev_name "我的笔记本" --lock

# 属性控制
miiotpcApi --dev_name "我的笔记本" --brightness 80
miiotpcApi --dev_name "我的笔记本" --get-brightness
miiotpcApi --dev_name "我的笔记本" --volume 50
miiotpcApi --dev_name "我的笔记本" --get-volume

# 使用 did 指定设备
miiotpcApi --did "123456789" --power on
```

### 5.3 通用属性操作

```bash
# 读取属性
miiotpcApi get --dev_name "我的笔记本" --prop_name on

# 设置属性
miiotpcApi set --dev_name "我的笔记本" --prop_name brightness --value 80

# 执行动作
miiotpcApi action --dev_name "我的笔记本" --action_name power-on

# 执行带参数的动作
miiotpcApi action --dev_name "我的笔记本" --action_name reboot --params '{"value":[1]}'
```

---

## 六、环境变量

```bash
# 设置日志级别（默认 INFO）
export MIIOTPC_LOG_LEVEL=DEBUG

# 运行命令
miiotpcApi --dev_name "我的笔记本" --status
```

---

## 七、完整工作流示例

### 7.1 首次配置

```bash
# 1. 安装
cd e:\Work.py\miiotpcApi
uv sync

# 2. 登录
uv run miiotpcApi login
# 扫描二维码

# 3. 确认设备
uv run miiotpcApi --list_pc

# 4. 测试控制
uv run miiotpcApi --dev_name "我的笔记本" --status
```

### 7.2 日常使用脚本

```python
#!/usr/bin/env python3
"""pc_control.py - PC控制脚本"""

from miiotpcApi import miiotpcAPI, PCDevice
from miiotpcApi.errors import LoginError, APIError
import sys

def main():
    dev_name = "我的笔记本"

    api = miiotpcAPI()
    try:
        if not api.available:
            api._refresh_token()
    except LoginError:
        api.login()

    pc = PCDevice(api, dev_name=dev_name)

    if len(sys.argv) < 2:
        print(f"用法: {sys.argv[0]} <on|off|sleep|wake|status>")
        sys.exit(1)

    cmd = sys.argv[1]
    try:
        if cmd == "on":
            pc.power_on()
            print(f"{pc.name} 已开机")
        elif cmd == "off":
            pc.power_off()
            print(f"{pc.name} 已关机")
        elif cmd == "sleep":
            pc.sleep()
            print(f"{pc.name} 已睡眠")
        elif cmd == "wake":
            pc.wake()
            print(f"{pc.name} 已唤醒")
        elif cmd == "status":
            status = pc.status
            print(f"设备: {status['name']}")
            print(f"型号: {status['model']}")
            print(f"能力: {status['capabilities']}")
        else:
            print(f"未知命令: {cmd}")
            sys.exit(1)
    except APIError as e:
        print(f"错误: {e}")
        sys.exit(1)

if __name__ == "__main__":
    main()
```

使用：
```bash
python pc_control.py on
python pc_control.py off
python pc_control.py status
```
