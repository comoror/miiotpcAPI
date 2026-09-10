# miiotpcApi — 米家笔记本/PC 设备控制 API
# Copyright (C) 2026 comor <304593790@qq.com>
#
# 本文件是 mijiaAPI（https://github.com/Do1e/mijia-api, GPL-3.0-or-later）
# 的衍生作品，基于 devices.py 重构并新增 PCDevice 高层封装。
# 原项目著作权归 Do1e <i@do1e.cn> 所有。
#
# 本程序是自由软件：你可以在自由软件基金会发布的 GNU 通用公共许可证第 3 版
# （或任何更新版本）的条款下重新分发和/或修改它。本程序的分发是希望它有用，
# 但不提供任何担保。详情请见 <https://www.gnu.org/licenses/>。
#
# 完整的衍生声明与上游来源见项目根目录的 NOTICE 文件。

import copy
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
from .version import version


DEVICE_SPEC_URL = "https://home.miot-spec.com/spec/"
DEVICE_INFO_CACHE_VERSION = 3

# 米家笔记本/PC 设备共用的内置 MIoT Spec
#
# 所有型号含 ".laptop." 的设备（xiaomi.laptop.* / redmi.laptop.*，含 REDMI Book）
# 共享同一套 siid/piid/aiid，因此无需查询上游站点。
#
# 为什么不查 https://home.miot-spec.com：该站点对尚未正式上线、仍在测试阶段的
# 型号会返回 HTTP 404（例如 xiaomi.laptop.p59），而设备本身是完全可控的。
# 内置 Spec 消除了这一网络依赖，也省去每次请求。
#
# 来源：xiaomi.laptop.p52 的官方规格，与同代机型一致。
LAPTOP_MODEL_MARKER = ".laptop."

LAPTOP_SPEC_PROPERTIES = [
    {
        "name": "status",
        "description": "Status / 工作状态",
        "type": "uint",
        "rw": "r",
        "range": None,
        "value-list": [
            {"value": 1, "description": "Waking Up", "desc_zh_cn": "正在唤醒"},
            {"value": 2, "description": "Power Off", "desc_zh_cn": "已关机"},
            {"value": 3, "description": "Sleep", "desc_zh_cn": "已睡眠"},
            {"value": 4, "description": "Shutting Down", "desc_zh_cn": "正在关机"},
            {"value": 6, "description": "Going Sleep", "desc_zh_cn": "正在进入睡眠"},
            {"value": 8, "description": "Running", "desc_zh_cn": "运行中"},
        ],
        "method": {"siid": 2, "piid": 1},
    },
    {
        "name": "temperature",
        "description": "Temperature / 温度",
        "type": "float",
        "rw": "r",
        "range": [0, 130, 1],
        "value-list": None,
        "method": {"siid": 3, "piid": 1},
    },
    {
        "name": "battery-level",
        "description": "Battery Level / 电池电量",
        "type": "uint",
        "rw": "r",
        "range": [0, 100, 1],
        "value-list": None,
        "method": {"siid": 4, "piid": 1},
    },
    {
        "name": "charging-state",
        "description": "Charging State / 电池充电状态",
        "type": "uint",
        "rw": "r",
        "range": None,
        "value-list": [
            {"value": 1, "description": "AC Power", "desc_zh_cn": "插电状态"},
            {"value": 2, "description": "Battery Power", "desc_zh_cn": "离电状态"},
        ],
        "method": {"siid": 4, "piid": 2},
    },
]

LAPTOP_SPEC_ACTIONS = [
    {
        "name": "turn-on",
        "description": "Turn On / 唤醒/开机",
        "method": {"siid": 2, "aiid": 1},
    },
    {
        "name": "turn-off",
        "description": "Turn Off / 关机",
        "method": {"siid": 2, "aiid": 2},
    },
    {
        "name": "sleep-mode-on",
        "description": "Sleep Mode On / 睡眠",
        "method": {"siid": 2, "aiid": 3},
    },
]


def _is_laptop_model(model: Optional[str]) -> bool:
    """判断型号是否属于共用内置 Spec 的笔记本/PC 设备。

    匹配 model 中是否含 ".laptop."，覆盖 xiaomi.laptop.* 与 redmi.laptop.*。
    """
    return LAPTOP_MODEL_MARKER in (model or "").lower()


def _type_name(type_urn: str) -> str:
    """Extract the short MIoT property/action name from a type URN."""
    marker = ":property:"
    if marker not in type_urn:
        marker = ":action:"
    if marker in type_urn:
        return type_urn.split(marker, 1)[1].split(":", 1)[0]
    return type_urn.rsplit(":", 1)[-1]


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


class DevProp():
    """设备属性描述符

    属性:
        name: 属性名称（MIoT Spec type 字段）
        desc: 属性描述
        type: 数据类型 - bool/int/uint/float/string
        rw: 读写权限 - "r"/"w"/"rw"
        range: 数值范围 [min, max, step]
        value_list: 枚举值列表
        method: API 调用参数 {"siid": int, "piid": int}
    """
    def __init__(self, prop_dict: dict):
        self.name = prop_dict["name"]
        self.desc = prop_dict["description"]
        self.type = prop_dict["type"]
        if self.type not in ["bool", "int", "uint", "float", "string"]:
            raise ValueError(f"不支持的类型: {self.type}, 可选类型: bool, int, uint, float, string")
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
            value_lines = [f"    {item['value']}: {item['description']}" for item in self.value_list]
            lines.extend(value_lines)
        return "\n".join(lines)


class DevAction():
    """设备动作描述符

    属性:
        name: 动作名称（MIoT Spec type 字段）
        desc: 动作描述
        method: API 调用参数 {"siid": int, "aiid": int}
    """
    def __init__(self, act_dict: dict):
        self.name = act_dict["name"]
        self.desc = act_dict["description"]
        self.method = act_dict["method"]

    def __str__(self):
        return f"  {self.name}: {self.desc}"


class MiotDevice():
    """MIoT 通用设备封装

    通过 did 或 dev_name 定位设备，自动获取 MIoT Spec，
    提供属性读写（get/set）和动作执行（run_action）接口。
    支持 __getattr__/__setattr__ 魔术方法直接操作属性。

    用法:
        device = MiotDevice(api, dev_name="我的笔记本")
        device.get("on")
        device.set("on", True)
        device.run_action("reboot")
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
            matches = [device for device in devices_list if device["name"] == dev_name]
            if not matches:
                raise DeviceNotFoundError(dev_name)
            else:
                if len(matches) > 1:
                    raise MultipleDevicesFoundError(
                        f"找到多个 dev_name 为 '{dev_name}' 的设备，请使用 did 参数指定具体设备或者修改设备名称以区分"
                    )
                did = matches[0]["did"]
                model = matches[0]["model"]
        else:
            matches = [device for device in devices_list if device["did"] == did]
            if not matches:
                raise DeviceNotFoundError(did)
            else:
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
        prop_list_str = "\n".join(filter(None, (str(v) for k, v in self.prop_list.items() if "_" not in k)))
        action_list_str = "\n".join(map(str, self.action_list.values()))
        return (f"{self.name} ({self.model})\n"
                f"Properties:\n{prop_list_str if prop_list_str else 'No properties available'}\n"
                f"Actions:\n{action_list_str if action_list_str else 'No actions available'}")

    def get(self, name: str) -> Union[bool, int, float, str]:
        """获取设备属性值"""
        if name not in self.prop_list:
            raise ValueError(f"不支持的属性: {name}, 可用属性: {list(self.prop_list.keys())}")
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
            raise ValueError(f"不支持的属性: {name}, 可用属性: {list(self.prop_list.keys())}")
        prop = self.prop_list[name]
        if "w" not in prop.rw:
            raise ValueError(f"属性 {name} 不可写入")
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
                    raise ValueError(f"{value} 超出数值范围, 应该在 {prop.range[:2]} 之间")
                if len(prop.range) >= 3 and prop.range[2] != 1:
                    if (value - prop.range[0]) % prop.range[2] != 0:
                        raise ValueError(
                            f"无效的值: {value}, 应该在范围 {prop.range[:2]} 内且步长为 {prop.range[2]}")
        elif prop.type == "float":
            value = float(value)
            if prop.range:
                if value < prop.range[0] or value > prop.range[1]:
                    raise ValueError(f"{value} 超出数值范围, 应该在 {prop.range[:2]} 之间")
                if len(prop.range) >= 3 and isinstance(prop.range[2], int):
                    if int(value - prop.range[0]) % prop.range[2] != 0:
                        raise ValueError(
                            f"无效的值: {value}, 应该在范围 {prop.range[:2]} 内且步长为 {prop.range[2]}")
        elif prop.type == "string":
            if not isinstance(value, str):
                raise ValueError(f"无效字符串值: {value}")
        else:
            raise ValueError(f"不支持的类型: {prop.type}, 可用类型: bool, int, uint, float, string")
        if prop.value_list:
            if value not in [item["value"] for item in prop.value_list]:
                raise ValueError(f"无效值: {value}, 请使用 {prop.value_list}")
        method = prop.method.copy()
        method["did"] = self.did
        method["value"] = value
        result = self.api.set_devices_prop(method)
        if result["code"] == 1:
            logger.warning(f"网关已经接收指令，无法判断是否设置成功: {self.name} -> {name}, 值: {value}")
        elif result["code"] != 0:
            raise DeviceSetError(self.name, name, result["code"])
        time.sleep(self.sleep_time)
        logger.debug(f"设置属性: {self.name} -> {name}, 值: {value}, 结果: {result}")

    def __getattr__(self, name: str) -> Union[bool, int, float, str]:
        if "prop_list" in self.__dict__ and name in self.prop_list:
            return self.get(name)
        else:
            return super().__getattr__(name)

    def __setattr__(self, name: str, value: Union[bool, int, float, str]) -> None:
        if "prop_list" in self.__dict__ and name in self.prop_list:
            self.set(name, value)
        else:
            super().__setattr__(name, value)

    def run_action(
            self,
            name: str,
            value: Optional[Union[list, tuple]] = None,
            **kwargs
    ):
        """执行设备动作"""
        if name not in self.action_list:
            raise ValueError(f"不支持的动作: {name}, 可用动作: {list(self.action_list.keys())}")
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
                    raise ValueError(f"无效的参数: {k}. 请勿使用以下参数 ({', '.join(method.keys())})")
                method[k] = v
        result = self.api.run_action(method)
        if result["code"] == 1:
            logger.warning(f"网关已经接收指令，无法判断是否执行成功: {self.name} -> {name}")
        elif result["code"] != 0:
            raise DeviceActionError(self.name, name, result["code"])
        time.sleep(self.sleep_time)
        logger.debug(f"执行动作: {self.name} -> {name}, 结果: {result}")


class PCDevice():
    """PC/笔记本设备高层封装

    在 MiotDevice 之上提供语义化的 PC 控制接口。
    自动检测设备支持的能力，不支持的操作会抛出明确的错误。

    用法:
        pc = PCDevice(api, dev_name="我的笔记本")
        pc.power_on()
        pc.power_off()
        pc.is_on()
        pc.sleep()
        pc.get_status()
        pc.get_temperature()
        pc.get_battery_level()
        print(pc.capabilities)
        print(pc.status)
    """

    # 常见 MIoT Spec 属性名到 PC 语义的映射
    _STATUS_PROPS = {"status", "working-status"}
    _TEMPERATURE_PROPS = {"temperature", "cpu-temperature"}
    _BATTERY_PROPS = {"battery-level", "battery"}
    _CHARGING_PROPS = {"charging-state", "charging-status"}

    # MIoT laptop action names from the standard and common aliases.
    _POWER_ON_ACTIONS = {"turn-on", "power-on", "on", "boot", "wake"}
    _POWER_OFF_ACTIONS = {"turn-off", "power-off", "off", "shutdown"}
    _SLEEP_ACTIONS = {"sleep-mode-on", "sleep", "suspend", "hibernate"}

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
        """设备支持的控制能力"""
        return self._capabilities.copy()

    @property
    def status(self) -> dict:
        """获取设备状态概览"""
        result = {
            "name": self.name,
            "model": self.model,
            "did": self.did,
            "capabilities": self.capabilities,
        }
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

    def _detect_capabilities(self):
        """自动检测设备支持的 PC 控制能力"""
        props = self._device.prop_list
        actions = self._device.action_list

        for name, prop in props.items():
            if "_" in name:
                continue
            name_lower = name.lower()
            if name_lower in self._STATUS_PROPS:
                self._capabilities["status"] = True
                self._prop_map["status"] = prop
            elif name_lower in self._TEMPERATURE_PROPS:
                self._capabilities["temperature"] = True
                self._prop_map["temperature"] = prop
            elif name_lower in self._BATTERY_PROPS:
                self._capabilities["battery_level"] = True
                self._prop_map["battery_level"] = prop
            elif name_lower in self._CHARGING_PROPS:
                self._capabilities["charging_state"] = True
                self._prop_map["charging_state"] = prop

        for name, action in actions.items():
            name_lower = name.lower()
            if name_lower in self._POWER_ON_ACTIONS:
                self._capabilities["power_on"] = True
                self._action_map["power_on"] = action
            if name_lower in self._POWER_OFF_ACTIONS:
                self._capabilities["power_off"] = True
                self._action_map["power_off"] = action
            if name_lower in self._SLEEP_ACTIONS:
                self._capabilities["sleep"] = True
                self._action_map["sleep"] = action

    def _check_capability(self, cap: str, action_desc: str):
        """检查设备是否支持某能力"""
        if not self._capabilities.get(cap, False):
            raise NotImplementedError(
                f"设备 {self.name} 不支持 {action_desc} 操作。"
                f"支持的能力: {self.capabilities}"
            )

    def power_on(self) -> bool:
        """开机"""
        if self._capabilities.get("power_on"):
            action = self._action_map["power_on"]
            self._device.run_action(action.name)
            return True
        self._check_capability("power_on", "开机")

    def power_off(self) -> bool:
        """关机"""
        if self._capabilities.get("power_off"):
            action = self._action_map["power_off"]
            self._device.run_action(action.name)
            return True
        self._check_capability("power_off", "关机")

    def is_on(self) -> bool:
        """查询电源状态"""
        self._check_capability("status", "状态查询")
        status = self._device.get(self._prop_map["status"].name)
        # Laptop Spec: 8=Running; 1/2/3/4/6 are transitional or off states.
        return status == 8

    def sleep(self) -> bool:
        """睡眠"""
        if self._capabilities.get("sleep"):
            action = self._action_map["sleep"]
            self._device.run_action(action.name)
            return True
        self._check_capability("sleep", "睡眠")

    def get_status(self):
        """获取笔记本工作状态枚举值。"""
        self._check_capability("status", "状态查询")
        return self._device.get(self._prop_map["status"].name)

    def get_temperature(self):
        """获取 CPU 温度。"""
        self._check_capability("temperature", "CPU 温度查询")
        return self._device.get(self._prop_map["temperature"].name)

    def get_battery_level(self):
        """获取电池电量百分比。"""
        self._check_capability("battery_level", "电池电量查询")
        return self._device.get(self._prop_map["battery_level"].name)

    def get_charging_state(self):
        """获取充电状态枚举值（1=插电，2=电池供电）。"""
        self._check_capability("charging_state", "充电状态查询")
        return self._device.get(self._prop_map["charging_state"].name)

    def get_prop(self, name: str):
        """获取任意属性（透传）"""
        return self._device.get(name)

    def set_prop(self, name: str, value):
        """设置任意属性（透传）"""
        self._device.set(name, value)

    def run_action(self, name: str, value=None, **kwargs):
        """执行任意动作（透传）"""
        self._device.run_action(name, value=value, **kwargs)

    def __str__(self) -> str:
        caps = ", ".join(k for k, v in self._capabilities.items() if v)
        return f"PCDevice: {self.name} ({self.model})\n支持的能力: {caps or '无'}"


def get_device_info(device_model: str, cache_path: Optional[Union[str, Path]] = None) -> dict:
    """
    获取设备 MIoT Spec 规格信息

    从 https://home.miot-spec.com/spec/{model} 获取设备的属性和动作定义。
    支持本地缓存。

    参数:
        device_model: 设备型号，如 'xiaomi.pc.v1'
        cache_path: 缓存目录路径，None 则不缓存

    返回值:
        dict: 设备规格信息

    说明:
        型号含 ".laptop." 的笔记本设备直接返回内置 Spec，不访问网络也不读缓存。
        其他型号仍从 home.miot-spec.com 获取并缓存。
    """
    if _is_laptop_model(device_model):
        logger.debug(f"使用内置笔记本 Spec: {device_model}")
        return {
            "version": DEVICE_INFO_CACHE_VERSION,
            "name": device_model,
            "model": device_model,
            "properties": copy.deepcopy(LAPTOP_SPEC_PROPERTIES),
            "actions": copy.deepcopy(LAPTOP_SPEC_ACTIONS),
        }

    cache_file = None
    if cache_path is not None:
        cache_file = Path(cache_path) / f"{device_model}.json"
        if cache_file.exists():
            logger.debug(f"从缓存加载设备信息: {cache_file}")
            with cache_file.open("r", encoding="utf-8") as f:
                cached_result = json.load(f)
            if cached_result.get("version") == DEVICE_INFO_CACHE_VERSION:
                return cached_result
            logger.debug(f"设备信息缓存版本不匹配，重新获取: {cache_file}")

    response = requests.get(DEVICE_SPEC_URL + device_model, headers={
        "User-Agent": f"miiotpcAPI/{version}"
    })
    if response.status_code != 200:
        raise GetDeviceInfoError(device_model)
    content = re.search(r"<script data-page=\"app\" type=\"application/json\">(.*?)</script>", response.text)
    if content is None:
        raise GetDeviceInfoError(device_model)
    content = content.group(1)
    content = json.loads(content)

    # home.miot-spec.com wraps the raw spec in props; callers may also
    # provide the raw MIoT document directly.
    if "props" in content:
        props = content["props"]
        product = props.get("product", {})
        name = product.get("name", content.get("description", device_model))
        model = product.get("model", device_model)
        services = props.get("tree", {}).get("services", [])
        i18n_zh = props.get("i18n", {}).get("zh_cn", {})
    else:
        name = content.get("description", device_model)
        model = device_model
        services = content.get("services", [])
        i18n_zh = {}
    result = {
        "version": DEVICE_INFO_CACHE_VERSION,
        "name": name,
        "model": model,
        "properties": [],
        "actions": []
    }
    for svc in services:
        siid = svc["iid"]
        for prop in svc.get("properties", []):
            piid = prop["iid"]
            if prop["format"].startswith("int"):
                prop_type = "int"
            elif prop["format"].startswith("uint"):
                prop_type = "uint"
            else:
                prop_type = prop["format"]
            access_str = "".join([
                "r" if "read" in prop["access"] else "",
                "w" if "write" in prop["access"] else ""
            ])
            zh_cn = i18n_zh.get(f"service:{siid:03d}:property:{piid:03d}", "")
            item = {
                "name": _type_name(prop["type"]),
                "description": f"{prop['description']} / {zh_cn}".rstrip(" / "),
                "type": prop_type,
                "rw": access_str,
                "range": prop.get("value-range", prop.get("valueRange", None)),
                "value-list": None,
                "method": {
                    "siid": siid,
                    "piid": piid
                }
            }
            value_list = prop.get("value-list", prop.get("valueList"))
            if value_list:
                item["value-list"] = []
                for vl_item in value_list:
                    vl_zh = i18n_zh.get(vl_item.get("i18nKey", vl_item.get("i18n-key", "")), "")
                    vl_entry = {
                        "value": vl_item["value"],
                        "description": vl_item["description"]
                    }
                    if vl_zh:
                        vl_entry["desc_zh_cn"] = vl_zh
                    item["value-list"].append(vl_entry)
            result["properties"].append(item)
        for act in svc.get("actions", []):
            aiid = act["iid"]
            zh_cn = i18n_zh.get(f"service:{siid:03d}:action:{aiid:03d}", "")
            act_item = {
                "name": _type_name(act["type"]),
                "description": f"{act['description']} / {zh_cn}".rstrip(" / "),
                "method": {
                    "siid": siid,
                    "aiid": aiid
                }
            }
            result["actions"].append(act_item)

    _deduplicate_names(result["properties"], "piid")
    _deduplicate_names(result["actions"], "aiid")

    if cache_file is not None:
        cache_file.parent.mkdir(parents=True, exist_ok=True)
        logger.debug(f"缓存设备信息到: {cache_file}")
        with cache_file.open("w", encoding="utf-8") as f:
            json.dump(result, f, indent=2, ensure_ascii=False)
    return result
