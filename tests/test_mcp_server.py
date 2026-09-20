"""MCP server 测试。

分两层：

- **渲染函数层**（render_*）：领域解读逻辑，脱离 MCP 直接测。
  这是本模块的价值所在，也是回归防护的重点。
- **工具层**（server 上注册的 @tool 函数）：只负责把异常翻译成中文提示，
  以及工具元数据（名称、annotations、docstring 里的判读规则）。

全部用例不联网：API 用 ``object.__new__(miiotpcAPI)`` 构造并注入桩方法，
设备型号一律含 ``.laptop.`` 以命中内置 Spec（不访问 home.miot-spec.com）。
"""

import inspect
from pathlib import Path

import anyio
import pytest
from mcp.server.mcpserver.exceptions import ToolError

import miiotpcApi.mcp_server as mcp_server
from miiotpcApi.api import miiotpcAPI
from miiotpcApi.device import LAPTOP_SPEC_PROPERTIES
from miiotpcApi.mcp_server import (
    AUTH_MESSAGE,
    CHARGING_LABELS,
    POWER_ACTION_MIOT,
    STATUS_LABELS,
    _describe_power,
    render_device_list,
    render_device_spec,
    render_full_status,
    render_power_action,
    render_power_status,
    server,
)
from miiotpcApi.version import version

# 笔记本内置 Spec 的 (siid, piid) -> 语义属性名
_PIID_TO_PROP = {
    (2, 1): "status",
    (3, 1): "temperature",
    (4, 1): "battery-level",
    (4, 2): "charging-state",
}

RUNNING = {
    "did": "1001",
    "name": "REDMI Book Pro 16 2026",
    "model": "xiaomi.laptop.n56sr",
    "isOnline": True,
}
SLEEPING = {
    "did": "1002",
    "name": "REDMI Book 14 2027 3",
    "model": "xiaomi.laptop.p59",
    "isOnline": True,
}
OFFLINE = {
    "did": "1003",
    "name": "REDMI Book Pro 16 2026 2",
    "model": "xiaomi.laptop.n56sr",
    "isOnline": False,
}


class FakeAPI:
    """miiotpcAPI 的替身，注入真实 PCDevice 会用到的三个方法。

    用 object.__new__ 保留真实的 ``find_pc_devices``（纯逻辑，值得测），
    只替换会触网的 ``get_devices_list`` / ``get_devices_prop`` / ``run_action``。
    """

    def __init__(self, devices, values=None):
        self.devices = devices
        self.values = values or {}
        self.prop_calls = []
        self.action_calls = []

        def get_devices_list(use_cache=True):
            return devices

        def get_devices_prop(data):
            self.prop_calls.append(dict(data))
            name = _PIID_TO_PROP.get((data["siid"], data["piid"]))
            return {
                "did": data["did"],
                "siid": data["siid"],
                "piid": data["piid"],
                "value": self.values.get(data["did"], {}).get(name),
                "code": 0,
            }

        def run_action(data):
            self.action_calls.append(dict(data))
            return {"did": data["did"], "code": 0, "message": "成功"}

        api = object.__new__(miiotpcAPI)
        api.auth_data_path = Path("C:/nonexistent/auth.json")  # 仅取 .parent
        api.get_devices_list = get_devices_list
        api.get_devices_prop = get_devices_prop
        api.run_action = run_action
        self.api = api

    @property
    def queried_props(self):
        return [_PIID_TO_PROP.get((c["siid"], c["piid"])) for c in self.prop_calls]


def _resolve(result):
    """MCP 的 list_tools / call_tool 可能返回协程，统一等待。"""
    if inspect.isawaitable(result):
        async def _await():
            return await result

        return anyio.run(_await)
    return result


def list_tools():
    return _resolve(server.list_tools())


def call_tool(name, args=None):
    return _resolve(server.call_tool(name, args or {}))


def tool_text(name, args=None):
    """经工具层调用并取出模型实际读到的文本。"""
    result = call_tool(name, args)
    assert getattr(result, "is_error", False) is False, f"工具报错: {result}"
    return "\n".join(b.text for b in result.content if getattr(b, "text", None))


def _tool_fn(name):
    """取回注册前的原始函数，以便检查 docstring。"""
    fn = getattr(mcp_server, name, None)
    assert callable(fn), f"模块里找不到工具函数 {name}"
    return fn


def _patch_api(monkeypatch, fake):
    monkeypatch.setattr(mcp_server, "_get_api", lambda: fake.api)


# ----------------------------------------------------------- 解读辅助函数


class TestDescribePower:
    @pytest.mark.parametrize("status", sorted(STATUS_LABELS))
    def test_every_enum_value_is_labelled(self, status):
        """所有合法枚举值都必须有中文标签，不能出现「未知状态」"""
        text = _describe_power(status)
        assert STATUS_LABELS[status] in text
        assert "未知状态" not in text

    @pytest.mark.parametrize("status", [1, 2, 3, 4, 6])
    def test_non_running_values_marked_as_not_running(self, status):
        """**核心规则**：非 8 即非运行中，输出必须点明"""
        assert "非运行中" in _describe_power(status)

    def test_running_value(self):
        assert "运行中" in _describe_power(8)
        assert "非运行中" not in _describe_power(8)

    def test_none_means_offline_not_powered_off(self):
        """None = 离线查不到，**不等于关机**——输出必须说清楚"""
        text = _describe_power(None)
        assert "离线" in text
        assert "查不到" in text or "无从得知" in text


# ----------------------------------------------------------- 设备列表


class TestRenderDeviceList:
    def test_lists_identity_and_online_state(self):
        text = render_device_list(FakeAPI([RUNNING, OFFLINE]).api)
        assert "REDMI Book Pro 16 2026" in text
        assert "did: 1001" in text
        assert "model: xiaomi.laptop.n56sr" in text
        assert "联网状态: 在线" in text
        assert "联网状态: 离线" in text

    def test_note_says_online_is_not_power_state(self):
        """必须点明 isOnline 不等于开机，并给出 status 判据"""
        text = render_device_list(FakeAPI([RUNNING]).api)
        assert "不代表是否开机" in text
        assert "非 8 即非运行中" in text
        assert "EC" in text

    def test_all_status_enums_present_in_note(self):
        """提示行的枚举必须齐全，不能只列 8/2/3"""
        text = render_device_list(FakeAPI([RUNNING]).api)
        for status, label in STATUS_LABELS.items():
            assert f"{status}={label}" in text, f"提示行缺少 {status}={label}"

    def test_empty_list_explains_keyword_rule(self):
        text = render_device_list(FakeAPI([]).api)
        assert "未找到" in text
        assert "laptop" in text  # 说明筛选关键词，而不是只说没有

    def test_does_not_query_any_property(self):
        """list_devices 只读清单，不该碰任何设备属性"""
        fake = FakeAPI([RUNNING, SLEEPING])
        render_device_list(fake.api)
        assert fake.prop_calls == []


# ----------------------------------------------------------- 电源状态


class TestRenderPowerStatus:
    def test_batch_renders_every_device(self):
        values = {"1001": {"status": 8}, "1002": {"status": 3}}
        text = render_power_status(FakeAPI([RUNNING, SLEEPING, OFFLINE], values).api)
        assert "运行中（status=8" in text
        assert "已睡眠（status=3，非运行中）" in text
        assert "机器正在运行" in text
        assert "机器当前未在运行" in text

    def test_offline_device_reports_unknown_and_skips_query(self):
        """**v0.1.4 核心行为**：离线设备不发起属性查询"""
        fake = FakeAPI([OFFLINE], {"1003": {"status": 2, "temperature": 34}})
        text = render_power_status(fake.api)
        assert "未知" in text and "离线" in text
        assert "无法判断当前是否开机" in text
        assert fake.prop_calls == [], "离线设备不应发起任何属性查询"

    def test_online_sleeping_device_is_still_queried(self):
        """对照组：睡眠但在线的设备必须照常查询（EC 待机供电，非离线）"""
        fake = FakeAPI([SLEEPING], {"1002": {"status": 3}})
        text = render_power_status(fake.api)
        assert "已睡眠" in text
        assert len(fake.prop_calls) > 0, "在线设备必须实际查询"

    def test_only_queries_status_property(self):
        """电源快速路径只查 status，不碰温度/电量——这是它比 full_status 快的原因"""
        fake = FakeAPI([RUNNING], {"1001": {"status": 8, "temperature": 55}})
        render_power_status(fake.api)
        assert fake.queried_props == ["status"], (
            f"get_power_status 只应查询 status，实际查了 {fake.queried_props}"
        )

    def test_single_device_by_did(self):
        values = {"1002": {"status": 3}}
        text = render_power_status(FakeAPI([RUNNING, SLEEPING], values).api, did="1002")
        assert "REDMI Book 14 2027 3" in text
        assert "已睡眠" in text
        assert "REDMI Book Pro 16 2026" not in text, "指定 did 时不应列出其他设备"

    def test_batch_note_carries_online_vs_power_rule(self):
        text = render_power_status(FakeAPI([RUNNING], {"1001": {"status": 8}}).api)
        assert "不代表是否开机" in text
        assert "非 8 即非运行中" in text

    def test_empty_account(self):
        assert "未找到" in render_power_status(FakeAPI([]).api)


# ----------------------------------------------------------- 完整状态


class TestRenderFullStatus:
    def test_online_running_device_reports_live_values(self):
        values = {
            "1001": {"status": 8, "temperature": 55, "battery-level": 100, "charging-state": 1}
        }
        text = render_full_status(FakeAPI([RUNNING], values).api)
        assert "运行中（status=8" in text
        assert "55 °C" in text
        assert "100%" in text
        assert CHARGING_LABELS[1] in text
        assert "数据新鲜度：实时" in text

    def test_sleeping_but_online_still_reports_live_temperature(self):
        """**最重要的回归防护**：睡眠/关机设备的温度是 EC 实时值，必须照常报告。

        曾经的错误认知是把这当作「过期快照」丢掉。正确行为是：报告数值，
        并说明它来自 EC、以及机器当前并非运行状态。
        """
        values = {
            "1002": {"status": 3, "temperature": 41, "battery-level": 41, "charging-state": 2}
        }
        text = render_full_status(FakeAPI([SLEEPING], values).api)
        assert "41 °C" in text, "关机/睡眠设备的温度是实时值，必须报告"
        assert "41%" in text
        assert "EC" in text
        assert "实时" in text
        assert "已睡眠" in text
        assert "不代表运行中的工况" in text

    def test_offline_device_has_no_values_and_no_query(self):
        """离线设备：不查询、无数据、并明确禁止推测"""
        fake = FakeAPI([OFFLINE], {"1003": {"status": 2, "temperature": 34}})
        text = render_full_status(fake.api)
        assert fake.prop_calls == [], "离线设备不应发起任何属性查询"
        assert "无数据（未查询）" in text
        assert "不要推测" in text
        assert "34" not in text, "过期值绝不能出现在输出里"

    def test_offline_marks_data_not_live(self):
        text = render_full_status(FakeAPI([OFFLINE]).api)
        assert "数据新鲜度：不可用" in text
        assert "查询已跳过" in text

    def test_property_read_failure_rendered_inline(self):
        """单属性读取失败要渲染出来，不能吞掉也不能中断其余字段"""

        def get_devices_prop(data):
            name = _PIID_TO_PROP.get((data["siid"], data["piid"]))
            if name == "temperature":
                # code != 0 -> MiotDevice.get 抛 DeviceGetError -> status 渲染为占位
                return {"did": data["did"], "siid": data["siid"], "piid": data["piid"], "code": -1}
            values = {"status": 8, "battery-level": 90, "charging-state": 1}
            return {
                "did": data["did"],
                "siid": data["siid"],
                "piid": data["piid"],
                "value": values.get(name),
                "code": 0,
            }

        fake = FakeAPI([RUNNING])
        fake.api.get_devices_prop = get_devices_prop
        text = render_full_status(fake.api)
        assert "查询失败" in text
        assert "运行中" in text, "其他字段仍应正常渲染"
        assert "90%" in text

    def test_unknown_charging_value_falls_back(self):
        values = {"1001": {"status": 8, "charging-state": 99}}
        text = render_full_status(FakeAPI([RUNNING], values).api)
        assert "未知（99）" in text

    def test_trailing_note_mentions_ec_and_online_rule(self):
        values = {"1001": {"status": 8, "temperature": 50}}
        text = render_full_status(FakeAPI([RUNNING], values).api)
        assert "主板 EC" in text
        assert "不代表是否开机" in text


# ----------------------------------------------------------- 电源动作


class TestRenderPowerAction:
    @pytest.mark.parametrize("action", ["on", "sleep", "off"])
    def test_each_action_reports_its_miot_action_name(self, action):
        text = render_power_action(FakeAPI([RUNNING]).api, did="1001", action=action)
        assert POWER_ACTION_MIOT[action] in text
        assert "米家接口返回成功" in text

    @pytest.mark.parametrize("action", ["on", "sleep", "off"])
    def test_action_actually_dispatched(self, action):
        """必须真的调用了对应动作，而不是只打印文案"""
        fake = FakeAPI([RUNNING])
        render_power_action(fake.api, did="1001", action=action)
        assert len(fake.action_calls) == 1
        assert fake.action_calls[0]["did"] == "1001"

    @pytest.mark.parametrize("action", ["on", "sleep", "off"])
    def test_output_forbids_immediate_state_claim(self, action):
        """返回成功只代表指令被接受，不等于状态已变——必须提醒"""
        text = render_power_action(FakeAPI([RUNNING]).api, did="1001", action=action)
        assert "不代表设备状态已经改变" in text
        assert "get_power_status" in text

    @pytest.mark.parametrize("action", ["toggle", "reboot", "", "ON"])
    def test_invalid_action_rejected(self, action):
        """没有 toggle / 重启；大小写不同也不接受"""
        with pytest.raises(ValueError) as exc:
            render_power_action(FakeAPI([RUNNING]).api, did="1001", action=action)
        assert "on / sleep / off" in str(exc.value)

    def test_invalid_action_rejected_before_any_dispatch(self):
        """参数校验必须先于设备构造与动作下发"""
        fake = FakeAPI([RUNNING])
        with pytest.raises(ValueError):
            render_power_action(fake.api, did="1001", action="toggle")
        assert fake.action_calls == []

    def test_unsupported_capability_explains_and_forbids_retry(self, monkeypatch):
        """设备 Spec 没有该动作时：说明限制，且明确不要重试"""
        from miiotpcApi.device import PCDevice

        def refuse(self):
            raise NotImplementedError(f"设备 {self.name} 不支持 关机 操作")

        monkeypatch.setattr(PCDevice, "power_off", refuse)
        text = render_power_action(FakeAPI([RUNNING]).api, did="1001", action="off")
        assert "操作未执行" in text
        assert "不要重试" in text


# ----------------------------------------------------------- 设备 Spec


class TestRenderDeviceSpec:
    def test_laptop_model_uses_builtin_spec_without_network(self):
        text = render_device_spec("xiaomi.laptop.p59")
        assert "内置笔记本 Spec" in text
        assert "不访问网络" in text

    def test_laptop_lists_four_properties_and_three_actions(self):
        text = render_device_spec("xiaomi.laptop.p59")
        for prop in ("status", "temperature", "battery-level", "charging-state"):
            assert prop in text
        for action in ("turn-on", "turn-off", "sleep-mode-on"):
            assert action in text

    def test_status_enums_rendered_with_chinese_labels(self):
        text = render_device_spec("xiaomi.laptop.p59")
        for status, label in STATUS_LABELS.items():
            assert f"{status} = {label}" in text, f"Spec 输出缺少枚举 {status}={label}"

    def test_charging_enums_rendered_from_spec(self):
        """Spec 输出忠实呈现 MIoT 定义的枚举措辞（插电状态/离电状态）。

        注意这与 get_full_status 里给用户看的措辞（插电/电池供电）不同——
        Spec 工具的职责是还原规范本身，状态工具的职责是好读。两者取值集合一致，
        见 TestConsistency.test_charging_labels_cover_all_spec_values。
        """
        text = render_device_spec("xiaomi.laptop.p59")
        assert "插电状态" in text
        assert "离电状态" in text

    def test_notes_all_laptop_properties_are_read_only(self):
        text = render_device_spec("xiaomi.laptop.p59")
        assert "只读" in text
        assert "必然报错" in text


# ----------------------------------------------------------- 工具注册与元数据


class TestToolRegistration:
    def test_exactly_five_tools_registered(self):
        names = sorted(t.name for t in list_tools())
        assert names == [
            "get_device_spec",
            "get_full_status",
            "get_power_status",
            "list_devices",
            "set_power",
        ]

    def test_no_login_tool_exists(self):
        """**结构性安全**：不暴露 login，模型就无法调用它。

        这比在文档里写「绝对不要调用 login」可靠得多——文档只是祈使句，
        工具列表里没有的东西根本调不了。
        """
        names = {t.name for t in list_tools()}
        assert "login" not in names
        assert not any("login" in n.lower() or "qr" in n.lower() for n in names), (
            f"工具名不得暗示登录能力: {names}"
        )

    def test_set_power_marked_destructive(self):
        """电源操作有真实世界副作用，必须在元数据里标出来供宿主审批"""
        tools = {t.name: t for t in list_tools()}
        ann = tools["set_power"].annotations
        assert ann.destructive_hint is True
        assert ann.read_only_hint is False

    @pytest.mark.parametrize(
        "name", ["list_devices", "get_power_status", "get_full_status", "get_device_spec"]
    )
    def test_query_tools_marked_read_only(self, name):
        tools = {t.name: t for t in list_tools()}
        ann = tools[name].annotations
        assert ann.read_only_hint is True
        assert ann.destructive_hint is False

    def test_get_device_spec_is_offline_capable(self):
        """笔记本走内置 Spec，不联网也不需要认证——元数据不应暗示外部交互"""
        tools = {t.name: t for t in list_tools()}
        assert tools["get_device_spec"].annotations.open_world_hint is False


class TestInstructionsCarryDomainRules:
    """instructions 是常驻上下文的服务器级说明，必须带上最容易搞错的判读规则"""

    def test_states_non_eight_rule(self):
        assert "非 8 即非运行中" in mcp_server._INSTRUCTIONS

    def test_states_online_is_not_power_state(self):
        assert "isOnline" in mcp_server._INSTRUCTIONS
        assert "不是开关机判据" in mcp_server._INSTRUCTIONS

    def test_states_ec_keeps_reporting_after_power_off(self):
        assert "EC" in mcp_server._INSTRUCTIONS
        assert "实时" in mcp_server._INSTRUCTIONS

    def test_states_offline_has_no_values(self):
        assert "不要编造" in mcp_server._INSTRUCTIONS or "不要推测" in mcp_server._INSTRUCTIONS

    def test_states_login_is_not_exposed_and_what_to_run(self):
        assert "不提供登录工具" in mcp_server._INSTRUCTIONS
        assert "miiotpcApi" in mcp_server._INSTRUCTIONS

    def test_server_metadata(self):
        assert server.name == "miiotpc"
        assert server.version == version


class TestToolDocstringsCarryRules:
    """工具描述会被注入模型上下文，关键规则必须写在这里"""

    def test_get_power_status_docstring(self):
        doc = inspect.getdoc(_tool_fn("get_power_status"))
        assert "非 8 即非运行中" in doc
        assert "不代表" in doc  # 联网状态不代表开机
        assert "不等于关机" in doc  # 离线 != 关机

    def test_get_full_status_docstring(self):
        doc = inspect.getdoc(_tool_fn("get_full_status"))
        assert "实时" in doc
        assert "EC" in doc
        assert "不要编造" in doc

    def test_set_power_docstring_warns_about_side_effects(self):
        doc = inspect.getdoc(_tool_fn("set_power"))
        assert "副作用" in doc
        assert "没有 toggle" in doc
        assert "不代表设备状态已经改变" in doc

    def test_list_devices_docstring_disclaims_online(self):
        doc = inspect.getdoc(_tool_fn("list_devices"))
        assert "不代表" in doc
        assert "did" in doc

    def test_get_device_spec_docstring_says_no_auth_needed(self):
        doc = inspect.getdoc(_tool_fn("get_device_spec"))
        assert "不需要认证" in doc
        assert "完整型号" in doc


# ----------------------------------------------------------- 工具层异常翻译


class TestToolLayerErrorTranslation:
    def test_auth_unavailable_returns_login_reminder(self, monkeypatch):
        def boom():
            raise mcp_server.AuthUnavailableError("认证文件不存在")

        monkeypatch.setattr(mcp_server, "_get_api", boom)
        for tool in ("list_devices", "get_power_status", "get_full_status"):
            text = tool_text(tool, {})
            assert text == AUTH_MESSAGE, f"{tool} 未返回统一的认证提示"
            assert "扫码登录" in text
            assert "本 server 故意不提供登录工具" in text

    def test_unknown_did_points_user_to_list_devices(self, monkeypatch):
        _patch_api(monkeypatch, FakeAPI([RUNNING]))
        text = tool_text("get_power_status", {"did": "9999"})
        assert "未找到" in text
        assert "list_devices" in text

    def test_unknown_did_on_power_action_refuses_without_guessing(self, monkeypatch):
        _patch_api(monkeypatch, FakeAPI([RUNNING]))
        text = tool_text("set_power", {"did": "9999", "action": "off"})
        assert "操作未执行" in text
        assert "不要猜测" in text

    def test_set_power_invalid_action_rejected_by_schema(self, monkeypatch):
        """**结构性保证**：非法 action 在 schema 层就被拒，根本到不了工具函数。

        MCP SDK 用类型注解生成输入 schema 并在调用前校验，所以 `toggle`
        这类取值不会进入业务代码。这比在工具里 try/except 更强——
        模型在协议层就无法发出非法调用。
        """
        _patch_api(monkeypatch, FakeAPI([RUNNING]))
        with pytest.raises(ToolError) as exc:
            call_tool("set_power", {"did": "1001", "action": "toggle"})
        message = str(exc.value)
        assert "set_power" in message
        assert "'on', 'sleep' or 'off'" in message, f"报错应列出合法取值: {message}"

    def test_render_layer_still_validates_action_for_direct_callers(self, monkeypatch):
        """工具层拦不到不等于渲染层不该校验——Python 直接调用时仍需报错"""
        _patch_api(monkeypatch, FakeAPI([RUNNING]))
        with pytest.raises(ValueError) as exc:
            mcp_server.render_power_action(FakeAPI([RUNNING]).api, did="1001", action="toggle")
        assert "on / sleep / off" in str(exc.value)

    def test_spec_tool_reports_failure_with_guidance(self, monkeypatch):
        """不联网：桩掉 get_device_info 让它抛错，验证工具层的提示"""

        def boom(model):
            raise RuntimeError("模拟的 Spec 获取失败")

        monkeypatch.setattr(mcp_server, "get_device_info", boom)
        text = tool_text("get_device_spec", {"model": "xiaomi.laptop.nope"})
        assert "失败" in text
        assert "list_devices" in text

    def test_successful_call_returns_interpreted_text(self, monkeypatch):
        values = {"1001": {"status": 8, "temperature": 55, "battery-level": 100, "charging-state": 1}}
        _patch_api(monkeypatch, FakeAPI([RUNNING], values))
        text = tool_text("get_full_status", {})
        assert "运行中（status=8" in text
        assert "55 °C" in text

    def test_offline_device_tool_result_has_no_numbers(self, monkeypatch):
        """端到端：离线设备经工具层返回后，输出里不得出现任何过期数值"""
        fake = FakeAPI([OFFLINE], {"1003": {"status": 2, "temperature": 34, "battery-level": 51}})
        _patch_api(monkeypatch, fake)
        text = tool_text("get_full_status", {})
        assert "无数据（未查询）" in text
        assert "34" not in text, "过期的温度值不得出现在工具输出里"
        assert "51" not in text, "过期的电量值不得出现在工具输出里"

    def test_power_status_end_to_end_interprets_enum(self, monkeypatch):
        """端到端：裸枚举 3 不该出现在给用户看的结论里，只应作为标注"""
        _patch_api(monkeypatch, FakeAPI([SLEEPING], {"1002": {"status": 3}}))
        text = tool_text("get_power_status", {"did": "1002"})
        assert "已睡眠" in text
        assert "非运行中" in text
        assert "机器当前未在运行" in text


# ----------------------------------------------------------- 一致性守护


class TestConsistency:
    def test_package_init_does_not_import_mcp_server(self):
        """__init__ 不得导入 mcp_server，否则 CLI 用户装包时会被强制要求 mcp 依赖。

        注意不能用 hasattr 判断——本测试模块导入了 mcp_server，Python 会因此
        在包对象上设置该属性。要看的是 __init__.py 的源码。
        """
        import miiotpcApi

        init_src = Path(inspect.getfile(miiotpcApi)).read_text(encoding="utf-8")
        assert "mcp_server" not in init_src, "__init__.py 不应引用 mcp_server"
        assert "mcp_server" not in getattr(miiotpcApi, "__all__", [])

    def test_pyproject_declares_mcp_extra_and_entry_point(self):
        pyproject = Path(__file__).resolve().parents[1] / "pyproject.toml"
        text = pyproject.read_text(encoding="utf-8")
        assert "mcp = [" in text, "pyproject 缺少 mcp optional-dependency"
        assert "mcp>=" in text
        assert 'miiotpcApi-mcp = "miiotpcApi.mcp_server:main"' in text

    def test_status_labels_match_builtin_laptop_spec(self):
        """MCP 的枚举标签必须与内置 laptop Spec 的 desc_zh_cn 一致。

        那份 Spec 是唯一权威来源（真机规格），MCP/CLI/文档三处都要对齐它。
        """
        status_prop = next(p for p in LAPTOP_SPEC_PROPERTIES if p["name"] == "status")
        spec_labels = {i["value"]: i["desc_zh_cn"] for i in status_prop["value-list"]}
        assert STATUS_LABELS == spec_labels, (
            f"MCP 状态标签与内置 Spec 不一致: MCP={STATUS_LABELS} Spec={spec_labels}"
        )

    def test_charging_labels_cover_all_spec_values(self):
        """充电枚举措辞允许与 Spec 描述不同（项目统一用「插电/电池供电」），
        但取值集合必须一致，不能漏掉某个枚举。"""
        charging_prop = next(p for p in LAPTOP_SPEC_PROPERTIES if p["name"] == "charging-state")
        spec_values = {i["value"] for i in charging_prop["value-list"]}
        assert set(CHARGING_LABELS) == spec_values

    def test_server_instructions_version_matches_package(self):
        assert f"v{version}" in mcp_server._INSTRUCTIONS
