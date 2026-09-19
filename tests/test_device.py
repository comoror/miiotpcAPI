"""PCDevice.status 语义测试

核心回归防护（v0.1.3 语义已确认）：

- `status` 是**唯一**的开关机判据（8=运行中，非 8 即非运行中）。
- `isOnline` 是联网状态。关机时主板 EC 仍有待机供电、联网模块保持在线，
  所以 is_online 为 True 并不代表 OS 在运行。
- `data_is_live` 表示数值是否实时。温度与电量由主板 EC 上报，OS 关机后 EC
  仍在工作，**关机设备的数值依然是实时值**——只有设备真正离线时才为 False。

全部用例不联网：PCDevice 通过 object.__new__ 构造，注入假的 _device。
"""

import inspect
import re

import pytest

from miiotpcApi.device import DevProp, PCDevice

FULL_STATUS_ENUM = {"1", "2", "3", "4", "6", "8"}

STATUS_LABELS = {
    1: "正在唤醒",
    2: "已关机",
    3: "已睡眠",
    4: "正在关机",
    6: "正在进入睡眠",
    8: "运行中",
}


class FakeDevice:
    """替代 MiotDevice，不触发任何网络请求"""

    def __init__(
        self,
        *,
        name="测试笔记本",
        model="xiaomi.laptop.test",
        did="123456",
        is_online=True,
        values=None,
        error=None,
    ):
        self.name = name
        self.model = model
        self.did = did
        self.is_online = is_online
        self._values = values or {}
        self._error = error

    def get(self, prop_name):
        if self._error is not None:
            raise self._error
        return self._values.get(prop_name)


def make_prop(name: str, rw: str = "r") -> DevProp:
    return DevProp(
        {
            "name": name,
            "description": f"{name} 的描述",
            "type": "int",
            "rw": rw,
            "range": [0, 100, 1],
            "method": {"siid": 2, "piid": 1},
        }
    )


def make_pc(**kwargs) -> PCDevice:
    pc = object.__new__(PCDevice)
    pc._device = FakeDevice(**kwargs)
    pc._capabilities = {"status": True, "temperature": True, "battery_level": True}
    pc._prop_map = {
        "status": make_prop("status"),
        "temperature": make_prop("temperature"),
        "battery_level": make_prop("battery-level"),
        "charging_state": make_prop("charging-state"),
    }
    pc._action_map = {}
    return pc


class TestStatusSemantics:
    def test_running_device_has_live_data(self):
        pc = make_pc(
            is_online=True,
            values={"status": 8, "temperature": 51, "battery-level": 100, "charging-state": 1},
        )
        s = pc.status
        assert s["status"] == 8
        assert s["isOnline"] is True
        assert s["data_is_live"] is True
        assert "warning" not in s

    def test_powered_off_but_online_still_reports_live_values(self):
        """**关键回归防护**：OS 关机不等于数值过期。

        温度/电量由主板 EC 上报，EC 有待机供电，关机后仍在采样，
        所以 isOnline=True + status=2 时 data_is_live 依然为 True，
        且不应出现 warning。
        """
        pc = make_pc(
            is_online=True,
            values={"status": 2, "temperature": 33, "battery-level": 59, "charging-state": 2},
        )
        s = pc.status
        assert s["status"] == 2, "设备已关机"
        assert s["isOnline"] is True, "EC 待机供电，联网模块仍在线"
        assert s["data_is_live"] is True, "EC 仍在上报，数值是实时的"
        assert "warning" not in s
        assert s["temperature"] == 33
        assert s["battery_level"] == 59

    @pytest.mark.parametrize("status", [2, 3])
    def test_any_non_running_status_without_warning_when_online(self, status):
        """关机(2)/睡眠(3) 且在线时都不应提示数值过期"""
        pc = make_pc(is_online=True, values={"status": status, "temperature": 40})
        s = pc.status
        assert s["data_is_live"] is True
        assert "warning" not in s

    def test_truly_offline_device_marks_data_stale(self):
        """只有真正离线（断网/拔电）时数值才退化为过期快照"""
        pc = make_pc(
            is_online=False,
            values={"status": 3, "temperature": 34, "battery-level": 51},
        )
        s = pc.status
        assert s["isOnline"] is False
        assert s["data_is_live"] is False
        assert "warning" in s
        assert "离线" in s["warning"]

    @pytest.mark.parametrize("status,label", sorted(STATUS_LABELS.items()))
    def test_status_values_round_trip(self, status, label):
        """status 字段透传 MIoT 枚举值，不被篡改"""
        pc = make_pc(is_online=True, values={"status": status})
        assert pc.status["status"] == status

    @pytest.mark.parametrize("status,is_running", [(8, True), (2, False), (3, False), (1, False)])
    def test_is_on_matches_status_eight(self, status, is_running):
        """Python API 的 is_on() 判据是 status == 8"""
        pc = make_pc(is_online=True, values={"status": status})
        assert pc.is_on() is is_running


class TestStatusShape:
    def test_contains_identity_and_capabilities(self):
        pc = make_pc(is_online=True, values={"status": 8})
        s = pc.status
        assert s["name"] == "测试笔记本"
        assert s["model"] == "xiaomi.laptop.test"
        assert s["did"] == "123456"
        assert s["capabilities"] == {"status": True, "temperature": True, "battery_level": True}

    def test_capabilities_are_copied_not_aliased(self):
        """返回的 capabilities 被改动不应污染设备内部状态"""
        pc = make_pc(is_online=True, values={"status": 8})
        pc.status["capabilities"]["status"] = False
        assert pc.capabilities["status"] is True

    def test_property_read_failure_is_inlined_not_raised(self):
        """单个属性读取失败应渲染为占位字符串，不能中断整体查询"""
        pc = make_pc(is_online=True, values={"status": 8}, error=RuntimeError("网络超时"))
        s = pc.status
        assert str(s["temperature"]).startswith("<读取失败:")
        assert "网络超时" in str(s["temperature"])

    def test_uses_miot_property_names_for_fetch(self):
        """status 通过 MIoT 原始属性名（battery-level）取值，而非语义名"""
        seen = []

        class Recorder(FakeDevice):
            def get(self, prop_name):
                seen.append(prop_name)
                return 1

        pc = object.__new__(PCDevice)
        pc._device = Recorder(is_online=True)
        pc._capabilities = {}
        pc._prop_map = {"battery_level": make_prop("battery-level")}
        _ = pc.status
        assert "battery-level" in seen

    def test_is_online_reflects_device(self):
        assert make_pc(is_online=True).is_online is True
        assert make_pc(is_online=False).is_online is False


class TestDocstringContract:
    def test_documents_all_status_enums(self):
        doc = inspect.getdoc(PCDevice.status)
        found = set(re.findall(r"(?<!\d)(\d)=", doc))
        assert found == FULL_STATUS_ENUM, f"docstring 枚举不全: {sorted(found)}"

    def test_documents_non_eight_rule(self):
        assert "非 8 即非运行中" in inspect.getdoc(PCDevice.status)

    def test_documents_ec_reporting_mechanism(self):
        """docstring 必须说明 EC 上报机制，否则读者会误以为关机即数值过期"""
        doc = inspect.getdoc(PCDevice.status)
        assert "EC" in doc
        assert "实时" in doc
