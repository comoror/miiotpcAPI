# device.py 详细实现规格

> 设备封装层：底层 MiotDevice + 高层 PCDevice

## 一、模块结构

```python
"""miiotpcApi.device - 设备控制模块

提供两层设备控制接口：
- MiotDevice: 底层 MIoT Spec 设备封装（通用，兼容原 mijiaDevice）
- PCDevice: PC/笔记本设备高层语义接口（推荐）
- DevProp / DevAction: 属性/动作描述符
- get_device_info(): 获取设备 MIoT Spec 信息
"""

import json
import re
import time
from collections import Counter
from pathlib import Path
from typing import Optional, Union

import requests

from .api import miiotpcAPI
from .errors import (
    DeviceActionError,
    DeviceGetError,
    DeviceNotFoundError,
    DeviceSetError,
    GetDeviceInfoError,
    MultipleDevicesFoundError,
)
from .logger import logger
```

---

## 二、常量

```python
DEVICE_SPEC_URL = "https://home.miot-spec.com/spec/"
DEVICE_INFO_CACHE_VERSION = 1
```

---

## 三、辅助函数

### `_deduplicate_names(items, iid_key)` [内部函数]

从原版直接复制。处理同名属性/动作的去重，通过追加 siid/piid/aiid 后缀区分。

```python
def _deduplicate_names(items: list[dict], iid_key: str) -> None:
    """对同名属性/动作添加 iid 后缀以去重"""
    name_counts = Counter(item["name"] for item in items)
    for item in items:
        if name_counts[item["name"]] > 1:
            item["name"] = f"{item['name']}-{item['method']['siid']}"

    name_counts = Counter(item["name"] for item in items)
    for item in items:
        if name_counts[item["name"]] > 1:
            item["name"] = f"{item['name']}-{item['method'][iid_key]}"
```

---

## 四、DevProp 类（原样保留）

```python
class DevProp:
    """设备属性描述符

    属性:
        name (str): 属性名称（MIoT Spec type 字段）
        desc (str): 属性描述
        type (str): 数据类型 - bool/int/uint/float/string
        rw (str): 读写权限 - "r"/"w"/"rw"
        range (list|None): 数值范围 [min, max, step]
        value_list (list|None): 枚举值列表 [{"value": x, "description": "..."}]
        method (dict): API 调用参数 {"siid": int, "piid": int}
    """

    def __init__(self, prop_dict: dict):
        self.name = prop_dict["name"]
        self.desc = prop_dict["description"]
        self.type = prop_dict["type"]
        if self.type not in ["bool", "int", "uint", "float", "string"]:
            raise ValueError(f"不支持的类型: {self.type}, 可选: bool, int, uint, float, string")
        self.rw = prop_dict["rw"]
        self.range = prop_dict["range"]
        self.value_list = prop_dict.get("value-list", None)
        self.method = prop_dict["method"]

    def __str__(self):
        lines = [
            f"  {self.name}: {self.desc}",
            f"    valuetype: {self.type}, rw: {self.rw}, range: {self.range}"
        ]
        if self.value_list:
            value_lines = [
                f"    {item['value']}: {item['description']}"
                for item in self.value_list
            ]
            lines.extend(value_lines)
        return "\n".join(lines)
```

---

## 五、DevAction 类（原样保留）

```python
class DevAction:
    """设备动作描述符

    属性:
        name (str): 动作名称（MIoT Spec type 字段）
        desc (str): 动作描述
        method (dict): API 调用参数 {"siid": int, "aiid": int}
    """

    def __init__(self, act_dict: dict):
        self.name = act_dict["name"]
        self.desc = act_dict["description"]
        self.method = act_dict["method"]

    def __str__(self):
        return f"  {self.name}: {self.desc}"
```

---

## 六、MiotDevice 类（原 mijiaDevice 改名）

完全保留原版逻辑，仅类名从 `mijiaDevice` 改为 `MiotDevice`。

```python
class MiotDevice:
    """MIoT 通用设备封装

    通过 did 或 dev_name 定位设备，自动获取 MIoT Spec，
    提供属性读写（get/set）和动作执行（run_action）接口。
    支持 __getattr__/__setattr__ 魔术方法直接操作属性。

    用法:
        device = MiotDevice(api, dev_name="我的笔记本")
        device.get("on")              # 读取属性
        device.set("on", True)        # 设置属性
        device.on                     # 同 get("on")
        device.on = True              # 同 set("on", True)
        device.run_action("reboot")   # 执行动作
    """

    def __init__(
        self,
        api: miiotpcAPI,
        did: Optional[str] = None,
        dev_name: Optional[str] = None,
        sleep_time: float = 0.5,
    ):
        self.api = api

        if did is None and dev_name is None:
            raise ValueError("必须提供 did 或 dev_name 参数之一")
        if did is not None and dev_name is not None:
            logger.warning("同时提供了 did 和 dev_name 参数，将忽略 dev_name")

        devices_list = self.api.get_devices_list()
        if did is None:
            matches = [d for d in devices_list if d["name"] == dev_name]
            if not matches:
                raise DeviceNotFoundError(dev_name)
            if len(matches) > 1:
                raise MultipleDevicesFoundError(
                    f"找到多个名为 '{dev_name}' 的设备，请使用 did 参数指定"
                )
            did = matches[0]["did"]
            model = matches[0]["model"]
        else:
            matches = [d for d in devices_list if d["did"] == did]
            if not matches:
                raise DeviceNotFoundError(did)
            if len(matches) > 1:
                raise MultipleDevicesFoundError(
                    f"找到多个 did 为 '{did}' 的设备"
                )
            dev_name = matches[0].get("name", None)
            model = matches[0]["model"]

        dev_info = get_device_info(model, cache_path=api.auth_data_path.parent)
        self.did = did
        self.model = model
        self.name = dev_name if dev_name is not None else dev_info["name"]
        self.sleep_time = sleep_time

        self.prop_list = {}
        for prop in dev_info.get("properties", []):
            prop_obj = DevProp(prop)
            name = prop["name"]
            self.prop_list[name] = prop_obj
            if "-" in name:
                self.prop_list[name.replace("-", "_")] = prop_obj

        self.action_list = {
            act["name"]: DevAction(act)
            for act in dev_info.get("actions", [])
        }

    def __str__(self) -> str:
        prop_list_str = "\n".join(
            filter(None, (str(v) for k, v in self.prop_list.items() if "_" not in k))
        )
        action_list_str = "\n".join(map(str, self.action_list.values()))
        return (
            f"{self.name} ({self.model})\n"
            f"Properties:\n{prop_list_str if prop_list_str else 'No properties'}\n"
            f"Actions:\n{action_list_str if action_list_str else 'No actions'}"
        )

    def get(self, name: str) -> Union[bool, int, float, str]:
        """获取设备属性值"""
        if name not in self.prop_list:
            raise ValueError(f"不支持的属性: {name}, 可用: {list(self.prop_list.keys())}")
        prop = self.prop_list[name]
        if "r" not in prop.rw:
            raise ValueError(f"属性 {name} 不可读取")
        method = prop.method.copy()
        method["did"] = self.did
        result = self.api.get_devices_prop(method)
        if result["code"] != 0:
            raise DeviceGetError(self.name, name, result["code"])
        time.sleep(self.sleep_time)
        logger.debug(f"获取属性: {self.name} -> {name}, 结果: {result}")
        return result["value"]

    def set(self, name: str, value: Union[bool, int, float, str]):
        """设置设备属性值"""
        if name not in self.prop_list:
            raise ValueError(f"不支持的属性: {name}, 可用: {list(self.prop_list.keys())}")
        prop = self.prop_list[name]
        if "w" not in prop.rw:
            raise ValueError(f"属性 {name} 不可写入")

        # 类型验证和转换
        value = self._validate_value(prop, value)

        method = prop.method.copy()
        method["did"] = self.did
        method["value"] = value
        result = self.api.set_devices_prop(method)
        if result["code"] == 1:
            logger.warning(f"网关已接收，无法判断是否成功: {self.name} -> {name}")
        elif result["code"] != 0:
            raise DeviceSetError(self.name, name, result["code"])
        time.sleep(self.sleep_time)
        logger.debug(f"设置属性: {self.name} -> {name}, 值: {value}")

    def _validate_value(self, prop: DevProp, value) -> Union[bool, int, float, str]:
        """验证并转换属性值类型"""
        if prop.type == "bool":
            if isinstance(value, str):
                if value.lower() == "true":
                    value = True
                elif value.lower() == "false":
                    value = False
                elif value in ["0", "1"]:
                    value = bool(int(value))
                else:
                    raise ValueError(f"无效布尔值: {value}")
            elif isinstance(value, int):
                if value == 0:
                    value = False
                elif value == 1:
                    value = True
                else:
                    raise ValueError(f"无效布尔值: {value}")
            elif not isinstance(value, bool):
                raise ValueError(f"无效布尔值: {value}")
        elif prop.type in ["int", "uint"]:
            value = int(value)
            if prop.range:
                if value < prop.range[0] or value > prop.range[1]:
                    raise ValueError(f"{value} 超出范围 {prop.range[:2]}")
                if len(prop.range) >= 3 and prop.range[2] != 1:
                    if (value - prop.range[0]) % prop.range[2] != 0:
                        raise ValueError(f"步长不匹配: {value}, 范围 {prop.range[:2]}, 步长 {prop.range[2]}")
        elif prop.type == "float":
            value = float(value)
            if prop.range:
                if value < prop.range[0] or value > prop.range[1]:
                    raise ValueError(f"{value} 超出范围 {prop.range[:2]}")
        elif prop.type == "string":
            if not isinstance(value, str):
                raise ValueError(f"无效字符串值: {value}")

        if prop.value_list:
            if value not in [item["value"] for item in prop.value_list]:
                raise ValueError(f"无效值: {value}, 可选: {prop.value_list}")

        return value

    def __getattr__(self, name: str) -> Union[bool, int, float, str]:
        if "prop_list" in self.__dict__ and name in self.prop_list:
            return self.get(name)
        return super().__getattr__(name)

    def __setattr__(self, name: str, value):
        if "prop_list" in self.__dict__ and name in self.prop_list:
            self.set(name, value)
        else:
            super().__setattr__(name, value)

    def run_action(self, name: str, value=None, **kwargs):
        """执行设备动作"""
        if name not in self.action_list:
            raise ValueError(f"不支持的动作: {name}, 可用: {list(self.action_list.keys())}")
        act = self.action_list[name]
        method = act.method.copy()
        method["did"] = self.did
        if value is not None:
            method["value"] = value
        if kwargs:
            for k, v in kwargs.items():
                if k.startswith("_"):
                    k = k[1:]
                if k in method:
                    raise ValueError(f"无效参数: {k}")
                method[k] = v
        result = self.api.run_action(method)
        if result["code"] == 1:
            logger.warning(f"网关已接收，无法判断是否成功: {self.name} -> {name}")
        elif result["code"] != 0:
            raise DeviceActionError(self.name, name, result["code"])
        time.sleep(self.sleep_time)
        logger.debug(f"执行动作: {self.name} -> {name}")
```

---

## 七、PCDevice 类（新增高层封装）

```python
class PCDevice:
    """PC/笔记本设备高层封装

    在 MiotDevice 之上提供语义化的 PC 控制接口。
    自动检测设备支持的能力，不支持的操作会抛出明确的错误。

    用法:
        pc = PCDevice(api, dev_name="我的笔记本")
        pc.power_on()             # 开机
        pc.power_off()            # 关机
        pc.is_on()                # 查询电源状态
        pc.sleep()                # 睡眠
        pc.power_on()             # 唤醒/开机
        pc.get_brightness()       # 获取亮度
        pc.set_brightness(80)     # 设置亮度
        print(pc.capabilities)    # 查看支持的能力
        print(pc.status)          # 获取状态概览
    """

    # 常见 MIoT Spec 属性名到 PC 语义的映射
    _POWER_PROPS = {"on", "power", "switch", "power-status"}
    _SLEEP_PROPS = {"sleep", "sleep-mode", "suspend"}
    _BRIGHTNESS_PROPS = {"brightness", "screen-brightness", "display-brightness"}
    _VOLUME_PROPS = {"volume", "speaker-volume"}
    _LOCK_PROPS = {"lock", "screen-lock", "locked"}

    # 常见动作名映射
    _POWER_ON_ACTIONS = {"power-on", "turn-on", "on", "boot"}
    _POWER_OFF_ACTIONS = {"power-off", "turn-off", "off", "shutdown"}
    _SLEEP_ACTIONS = {"sleep", "suspend", "hibernate"}
    _WAKE_ACTIONS = {"wake", "wake-up", "resume"}
    _LOCK_ACTIONS = {"lock", "lock-screen"}

    def __init__(
        self,
        api: miiotpcAPI,
        did: Optional[str] = None,
        dev_name: Optional[str] = None,
        sleep_time: float = 0.5,
    ):
        self._device = MiotDevice(api, did=did, dev_name=dev_name, sleep_time=sleep_time)
        self._capabilities = {}
        self._prop_map = {}    # 语义名 -> DevProp
        self._action_map = {}  # 语义名 -> DevAction
        self._detect_capabilities()

    @property
    def name(self) -> str:
        """设备名称"""
        return self._device.name

    @property
    def model(self) -> str:
        """设备型号"""
        return self._device.model

    @property
    def did(self) -> str:
        """设备ID"""
        return self._device.did

    @property
    def capabilities(self) -> dict:
        """设备支持的控制能力

        返回:
            dict: {
                "power": True/False,
                "sleep": True/False,
                "wake": True/False,
                "lock": True/False,
                "brightness": True/False,
                "volume": True/False,
            }
        """
        return self._capabilities.copy()

    @property
    def status(self) -> dict:
        """获取设备状态概览

        返回:
            dict: 当前所有可读属性的值
        """
        result = {
            "name": self.name,
            "model": self.model,
            "did": self.did,
            "capabilities": self.capabilities,
        }
        # 读取所有已映射的可读属性
        for semantic_name, prop in self._prop_map.items():
            if "r" in prop.rw:
                try:
                    result[semantic_name] = self._device.get(prop.name)
                except Exception as e:
                    result[semantic_name] = f"<读取失败: {e}>"
        return result

    @property
    def spec(self) -> str:
        """设备完整规格信息"""
        return str(self._device)

    # ---- 能力检测 ----

    def _detect_capabilities(self):
        """自动检测设备支持的 PC 控制能力"""
        props = self._device.prop_list
        actions = self._device.action_list

        # 检测属性
        for name, prop in props.items():
            if "_" in name:  # 跳过别名
                continue
            name_lower = name.lower()
            if any(kw in name_lower for kw in self._POWER_PROPS):
                self._capabilities["power"] = True
                self._prop_map["on"] = prop
            elif any(kw in name_lower for kw in self._BRIGHTNESS_PROPS):
                self._capabilities["brightness"] = True
                self._prop_map["brightness"] = prop
            elif any(kw in name_lower for kw in self._VOLUME_PROPS):
                self._capabilities["volume"] = True
                self._prop_map["volume"] = prop
            elif any(kw in name_lower for kw in self._LOCK_PROPS):
                self._capabilities["lock"] = True
                self._prop_map["lock"] = prop

        # 检测动作
        for name, action in actions.items():
            name_lower = name.lower()
            if any(kw in name_lower for kw in self._POWER_ON_ACTIONS):
                self._capabilities["power_on_action"] = True
                self._action_map["power_on"] = action
            if any(kw in name_lower for kw in self._POWER_OFF_ACTIONS):
                self._capabilities["power_off_action"] = True
                self._action_map["power_off"] = action
            if any(kw in name_lower for kw in self._SLEEP_ACTIONS):
                self._capabilities["sleep"] = True
                self._action_map["sleep"] = action
            if any(kw in name_lower for kw in self._WAKE_ACTIONS):
                self._capabilities["wake"] = True
                self._action_map["wake"] = action
            if any(kw in name_lower for kw in self._LOCK_ACTIONS):
                self._capabilities["lock_action"] = True
                self._action_map["lock"] = action

    def _check_capability(self, cap: str, action_desc: str):
        """检查设备是否支持某能力"""
        if not self._capabilities.get(cap, False):
            raise NotImplementedError(
                f"设备 {self.name} 不支持 {action_desc} 操作。"
                f"支持的能力: {self.capabilities}"
            )

    # ---- 电源控制 ----

    def power_on(self) -> bool:
        """开机

        优先使用 power-on 动作，其次使用 set("on", True)

        返回:
            bool: 操作是否成功
        """
        if self._capabilities.get("power_on_action"):
            action = self._action_map["power_on"]
            self._device.run_action(action.name)
            return True
        elif self._capabilities.get("power"):
            prop = self._prop_map["on"]
            if "w" in prop.rw:
                self._device.set(prop.name, True)
                return True
        self._check_capability("power", "开机")

    def power_off(self) -> bool:
        """关机

        优先使用 power-off 动作，其次使用 set("on", False)

        返回:
            bool: 操作是否成功
        """
        if self._capabilities.get("power_off_action"):
            action = self._action_map["power_off"]
            self._device.run_action(action.name)
            return True
        elif self._capabilities.get("power"):
            prop = self._prop_map["on"]
            if "w" in prop.rw:
                self._device.set(prop.name, False)
                return True
        self._check_capability("power", "关机")

    def power_toggle_removed(self) -> bool:
        """电源切换

        返回:
            bool: 切换后的电源状态 (True=开, False=关)
        """
        current = self.is_on()
        if current:
            self.power_off()
        else:
            self.power_on()
        return not current

    def is_on(self) -> bool:
        """查询电源状态

        返回:
            bool: True=开机, False=关机
        """
        if self._capabilities.get("power"):
            prop = self._prop_map["on"]
            if "r" in prop.rw:
                return bool(self._device.get(prop.name))
        raise NotImplementedError(f"设备 {self.name} 不支持查询电源状态")

    # ---- 系统控制 ----

    def sleep(self) -> bool:
        """睡眠

        返回:
            bool: 操作是否成功
        """
        if self._capabilities.get("sleep"):
            action = self._action_map["sleep"]
            self._device.run_action(action.name)
            return True
        # 回退：尝试设置 sleep 属性
        for name, prop in self._device.prop_list.items():
            if any(kw in name.lower() for kw in self._SLEEP_PROPS):
                if "w" in prop.rw:
                    self._device.set(name, True)
                    return True
        self._check_capability("sleep", "睡眠")

    def wake(self) -> bool:
        """唤醒

        返回:
            bool: 操作是否成功
        """
        if self._capabilities.get("wake"):
            action = self._action_map["wake"]
            self._device.run_action(action.name)
            return True
        self._check_capability("wake", "唤醒")

    def lock_screen(self) -> bool:
        """锁屏

        返回:
            bool: 操作是否成功
        """
        if self._capabilities.get("lock_action"):
            action = self._action_map["lock"]
            self._device.run_action(action.name)
            return True
        elif self._capabilities.get("lock"):
            prop = self._prop_map["lock"]
            if "w" in prop.rw:
                self._device.set(prop.name, True)
                return True
        self._check_capability("lock", "锁屏")

    # ---- 属性控制 ----

    def get_brightness(self) -> int:
        """获取屏幕亮度

        返回:
            int: 亮度值 (通常 0-100)
        """
        self._check_capability("brightness", "亮度查询")
        return self._device.get(self._prop_map["brightness"].name)

    def set_brightness(self, value: int) -> None:
        """设置屏幕亮度

        参数:
            value: 亮度值 (通常 0-100)
        """
        self._check_capability("brightness", "亮度设置")
        self._device.set(self._prop_map["brightness"].name, value)

    def get_volume(self) -> int:
        """获取音量

        返回:
            int: 音量值 (通常 0-100)
        """
        self._check_capability("volume", "音量查询")
        return self._device.get(self._prop_map["volume"].name)

    def set_volume(self, value: int) -> None:
        """设置音量

        参数:
            value: 音量值 (通常 0-100)
        """
        self._check_capability("volume", "音量设置")
        self._device.set(self._prop_map["volume"].name, value)

    # ---- 通用接口（透传） ----

    def get_prop(self, name: str):
        """获取任意属性（透传到底层 MiotDevice）

        参数:
            name: MIoT Spec 属性名

        返回:
            属性值
        """
        return self._device.get(name)

    def set_prop(self, name: str, value):
        """设置任意属性（透传到底层 MiotDevice）

        参数:
            name: MIoT Spec 属性名
            value: 要设置的值
        """
        self._device.set(name, value)

    def run_action(self, name: str, value=None, **kwargs):
        """执行任意动作（透传到底层 MiotDevice）

        参数:
            name: MIoT Spec 动作名
            value: 动作参数（可选）
        """
        self._device.run_action(name, value=value, **kwargs)

    def __str__(self) -> str:
        caps = ", ".join(k for k, v in self._capabilities.items() if v)
        return f"PCDevice: {self.name} ({self.model})\n支持的能力: {caps or '无'}"
```

---

## 八、get_device_info 函数（原样保留）

```python
def get_device_info(
    device_model: str,
    cache_path: Optional[Union[str, Path]] = None
) -> dict:
    """获取设备 MIoT Spec 规格信息

    从 https://home.miot-spec.com/spec/{model} 获取设备的属性和动作定义。
    支持本地缓存。

    参数:
        device_model: 设备型号，如 'xiaomi.pc.v1'
        cache_path: 缓存目录路径，None 则不缓存

    返回:
        dict: {
            "version": int,
            "name": str,
            "model": str,
            "properties": [{"name", "description", "type", "rw", "range", "value-list", "method"}],
            "actions": [{"name", "description", "method"}]
        }
    """
    # 直接从 mijiaAPI/devices.py 完整复制，无修改
    ...
```

---

## 九、PCDevice 能力检测的扩展性说明

`_detect_capabilities()` 的关键词匹配是基于常见 MIoT Spec 命名约定的启发式方法。

**局限性：**
- 不同厂商的 PC 设备可能使用不同的属性/动作名
- 某些设备可能通过自定义 service 实现 PC 控制

**扩展方案：**
1. 运行时日志：检测到的能力通过 `logger.info` 输出，方便调试
2. 用户可手动指定映射（未来版本）：
   ```python
   pc = PCDevice(api, dev_name="...", prop_map={"on": "custom-power-prop"})
   ```
3. 通过 `get_device_info()` 先查看设备 spec，再决定如何使用
