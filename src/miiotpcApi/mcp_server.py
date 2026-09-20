# miiotpcApi — 米家笔记本/PC 设备控制 API
# Copyright (C) 2026 comor <304593790@qq.com>
#
# 本文件是 mijiaAPI（https://github.com/Do1e/mijia-api, GPL-3.0-or-later）
# 的衍生作品，原项目著作权归 Do1e <i@do1e.cn> 所有。
#
# 本程序是自由软件：你可以在自由软件基金会发布的 GNU 通用公共许可证第 3 版
# （或任何更新版本）的条款下重新分发和/或修改它。本程序的分发是希望它有用，
# 但不提供任何担保。详情请见 <https://www.gnu.org/licenses/>。
#
# 完整的衍生声明与上游来源见项目根目录的 NOTICE 文件。

"""miiotpcApi 的 MCP server。

把米家笔记本/PC 查询与电源控制暴露为 MCP 工具，供本地 AI agent 调用。

设计原则：**所有工具都返回已解读的中文文本，而不是原始枚举值。**

这是本模块存在的主要理由。MIoT 的 ``status`` 是枚举（8=运行中，非 8 即非
运行中），``isOnline`` 是联网状态，二者正交且都容易被误读；如果工具只返回
``{"status": 2, "temperature": 33}`` 这样的裸数据，调用方几乎必然把「关机
设备的温度」当成过期快照丢掉——而实际上温度由主板 EC 上报，关机后依然实时。

把这些解读写进返回文本，领域规则就落在了 Python 里，可以被测试钉住，
而不是散落在文档里、靠调用方自觉阅读。

**本 server 不提供登录工具。** 二维码扫码必须由人完成，暴露成工具只会
诱使 agent 去调用一个必然阻塞的接口。认证缺失时返回提示，让用户自行登录。
"""

from __future__ import annotations

from typing import Literal, Optional

from mcp.server import MCPServer
from mcp.types import ToolAnnotations

from .api import miiotpcAPI
from .device import PCDevice, get_device_info
from .errors import DeviceActionError, DeviceNotFoundError, MultipleDevicesFoundError
from .version import version

SERVER_NAME = "miiotpc"

# MIoT laptop spec 的 status 枚举。判断开关机只认这一个字段：8=运行中，
# 非 8 即非运行中。其余取值都是过渡态或关机态。
STATUS_LABELS = {
    1: "正在唤醒",
    2: "已关机",
    3: "已睡眠",
    4: "正在关机",
    6: "正在进入睡眠",
    8: "运行中",
}

CHARGING_LABELS = {1: "插电（AC 供电）", 2: "电池供电"}

POWER_ACTION_LABELS = {"on": "开机/唤醒", "sleep": "睡眠", "off": "关机"}
POWER_ACTION_MIOT = {"on": "turn-on", "sleep": "sleep-mode-on", "off": "turn-off"}
POWER_ACTION_METHOD = {"on": "power_on", "sleep": "sleep", "off": "power_off"}

# 判断口径提示，反复出现在各类输出末尾。调用方最常见的两类误判是：
# 把 isOnline 当开关机判据、把关机设备的温度当过期快照。
_ONLINE_NOT_POWER_NOTE = (
    "「联网状态」是 isOnline，不代表是否开机——关机时主板 EC 仍有待机供电、"
    "联网模块照样在线。判断开机一律看运行状态：8=运行中，非 8 即非运行中"
    "（1=正在唤醒 / 2=已关机 / 3=已睡眠 / 4=正在关机 / 6=正在进入睡眠）。"
)

_EC_NOTE = (
    "温度与电量由主板 EC 上报。关机/睡眠只是操作系统停止，EC 仍有待机供电并"
    "持续采样，所以这些数值是实时的，可以直接引用。"
)

AUTH_MESSAGE = (
    "认证不可用：认证文件不存在、已损坏，或已失效且刷新失败。\n"
    "请提醒用户自行执行以下命令扫码登录（本 server 故意不提供登录工具，"
    "二维码扫码必须由人完成）：\n"
    "    uvx miiotpcApi@latest login\n"
    "登录后认证写入 ~/.config/miiotpc-api/auth.json，重启本 server 即可生效。"
)


class AuthUnavailableError(RuntimeError):
    """认证文件缺失或已失效，无法调用米家接口。"""


# ---------------------------------------------------------------- API 实例管理

_api_cache: Optional[miiotpcAPI] = None


def _get_api() -> miiotpcAPI:
    """获取已认证的 API 实例。

    缓存实例以复用设备列表缓存；但当缓存实例已失效时会丢弃重建，
    这样用户重新扫码登录后**无需重启 server**，下次调用即可生效。

    认证刷新逻辑与 ``__main__.init_api`` 保持一致：先试刷新，刷不动才报错。
    """
    global _api_cache

    if _api_cache is not None and _api_cache.available:
        return _api_cache

    api = miiotpcAPI()
    if not api.available:
        try:
            api._refresh_token()
        except Exception as exc:  # noqa: BLE001 - 任何刷新失败都归为认证不可用
            raise AuthUnavailableError(str(exc)) from exc
    _api_cache = api
    return api


def _reset_api_cache() -> None:
    """丢弃缓存的 API 实例（测试与登录变更后使用）。"""
    global _api_cache
    _api_cache = None


# ---------------------------------------------------------------- 解读辅助函数


def _describe_power(status_value) -> str:
    """把 status 枚举解读成一句话。

    None 表示设备离线、查询已被跳过——**这不等于关机**，只是无从得知。
    """
    if status_value is None:
        return "未知——设备已离线，查询已跳过（云端只剩过期快照，无从得知）"
    if status_value == 8:
        return "运行中（status=8，操作系统正在运行）"
    label = STATUS_LABELS.get(status_value, "未知状态")
    return f"{label}（status={status_value}，非运行中）"


def _describe_online(is_online: bool) -> str:
    return "在线" if is_online else "离线"


def _describe_value(value, unit: str = "") -> str:
    """把属性值渲染成可引用的文本。

    三类取值各有含义：None=离线未查询；``<读取失败: ...>``=查询报错；
    其余=实时数值。
    """
    if value is None:
        return "无数据（设备离线，未查询）"
    if isinstance(value, str) and value.startswith("<读取失败"):
        return f"查询失败 {value}"
    return f"{value}{unit}"


def _entry_header(status_dict: dict) -> str:
    return (
        f"{status_dict.get('name', '<未命名设备>')}  "
        f"[did {status_dict.get('did', '?')}]  "
        f"型号 {status_dict.get('model', '?')}"
    )


def _find_pc_entries(api: miiotpcAPI) -> list[dict]:
    return api.find_pc_devices()


# ---------------------------------------------------------------- 渲染函数


def render_device_list(api: miiotpcAPI) -> str:
    """渲染账号下的 PC/笔记本清单。只列设备，不查属性。"""
    devices = _find_pc_entries(api)
    if not devices:
        return (
            "未找到 PC/笔记本设备。\n"
            "筛选规则是设备名称或型号包含 pc / 电脑 / 笔记本 / laptop / desktop / "
            "notebook。若确实有笔记本却没被列出，说明米家 APP 里的设备名不含这些"
            "关键词，请改名后重试。"
        )

    lines = [f"米家账号下的 PC/笔记本设备（共 {len(devices)} 台）：", ""]
    for index, device in enumerate(devices, start=1):
        lines.append(f"{index}. {device.get('name', '<未命名设备>')}")
        lines.append(f"   did: {device.get('did', '?')}")
        lines.append(f"   model: {device.get('model', '?')}")
        lines.append(f"   联网状态: {_describe_online(bool(device.get('isOnline')))}")
        lines.append("")
    lines.append(f"说明：{_ONLINE_NOT_POWER_NOTE}")
    return "\n".join(lines)


def render_power_status(api: miiotpcAPI, did: Optional[str] = None) -> str:
    """渲染电源状态。只查 status 一个属性，不碰温度/电量。

    这是「笔记本开了吗」这类问题的专用快速路径：单属性查询，比全量状态快，
    也避免在只需要开关机时白白发起温度/电量请求。
    """
    if did is not None:
        pc = PCDevice(api, did=did, sleep_time=0)
        return _render_one_power(pc, show_did=False)

    entries = _find_pc_entries(api)
    if not entries:
        return "未找到 PC/笔记本设备，无法查询电源状态。"

    lines = [
        "笔记本电源状态（一次批量查询全部设备）",
        "",
    ]
    blocks = []
    for entry in entries:
        try:
            pc = PCDevice(api, did=entry["did"], sleep_time=0)
            blocks.append(_render_one_power(pc, show_did=True))
        except Exception as exc:  # noqa: BLE001 - 单台失败不应中断整批
            blocks.append(
                f"{entry.get('name', '<未命名设备>')}  [did {entry.get('did', '?')}]\n"
                f"   运行状态：查询失败（{exc}）"
            )
    for index, block in enumerate(blocks, start=1):
        lines.append(f"{index}. {block}")
        lines.append("")
    lines.append(f"说明：{_ONLINE_NOT_POWER_NOTE}")
    return "\n".join(lines)


def _render_one_power(pc: PCDevice, show_did: bool) -> str:
    """单台设备的电源状态。离线时不会发起属性查询（PCDevice 已内置该守卫）。"""
    header = pc.name if not show_did else f"{pc.name}  [did {pc.did}]"
    is_online = pc.is_online
    status_value = pc.get_status()  # 离线时返回 None 且不发请求

    lines = [
        header,
        f"   运行状态：{_describe_power(status_value)}",
        f"   联网状态：{_describe_online(is_online)}",
    ]
    if not is_online:
        lines.append("   结论：设备离线，无法判断当前是否开机。")
    elif status_value == 8:
        lines.append("   结论：机器正在运行。")
    else:
        lines.append(
            f"   结论：机器当前未在运行（{STATUS_LABELS.get(status_value, '未知')}）。"
        )
    return "\n".join(lines)


def render_full_status(api: miiotpcAPI, did: Optional[str] = None) -> str:
    """渲染完整状态：电源 + 温度 + 电量 + 充电，全部已解读。"""
    if did is not None:
        pc = PCDevice(api, did=did, sleep_time=0)
        return _render_one_full(pc.status)

    entries = _find_pc_entries(api)
    if not entries:
        return "未找到 PC/笔记本设备，无法查询状态。"

    blocks = []
    for entry in entries:
        try:
            pc = PCDevice(api, did=entry["did"], sleep_time=0)
            blocks.append(_render_one_full(pc.status))
        except Exception as exc:  # noqa: BLE001 - 单台失败不应中断整批
            blocks.append(
                f"{entry.get('name', '<未命名设备>')}  [did {entry.get('did', '?')}]\n"
                f"   查询失败：{exc}"
            )
    return ("\n\n".join(blocks) + "\n\n" + f"说明：{_EC_NOTE} {_ONLINE_NOT_POWER_NOTE}")


def _render_one_full(status: dict) -> str:
    """把 PCDevice.status 字典渲染成可直接引用的文本。"""
    is_online = bool(status.get("isOnline"))
    lines = [_entry_header(status)]
    lines.append(f"   运行状态：{_describe_power(status.get('status'))}")
    lines.append(f"   联网状态：{_describe_online(is_online)}")

    if is_online:
        lines.append("   数据新鲜度：实时")
        lines.append(f"     → {_EC_NOTE}")
        lines.append(f"   CPU 温度：{_describe_value(status.get('temperature'), ' °C')}")
        lines.append(f"   电池电量：{_describe_value(status.get('battery_level'), '%')}")
        charging = status.get("charging_state")
        if charging is None:
            lines.append("   充电状态：无数据（设备离线，未查询）")
        elif isinstance(charging, str) and charging.startswith("<读取失败"):
            lines.append(f"   充电状态：查询失败 {charging}")
        else:
            label = CHARGING_LABELS.get(charging, "未知")
            lines.append(f"   充电状态：{label}（{charging}）")
        status_value = status.get("status")
        if status_value is not None and status_value != 8:
            lines.append(
                f"   提示：机器当前是「{STATUS_LABELS.get(status_value, '未知')}」状态，"
                "上面的温度/电量依然实时有效（EC 上报），只是不代表运行中的工况。"
            )
    else:
        lines.append("   数据新鲜度：不可用——设备真正离线，属性查询已跳过")
        lines.append("   CPU 温度：无数据（未查询）")
        lines.append("   电池电量：无数据（未查询）")
        lines.append("   充电状态：无数据（未查询）")
        lines.append("   提示：输出里没有任何可引用的数值，不要推测。")
    return "\n".join(lines)


def render_power_action(api: miiotpcAPI, did: str, action: str) -> str:
    """执行电源动作并渲染确认文本。"""
    if action not in POWER_ACTION_LABELS:
        raise ValueError(
            f"无效的 action: {action!r}，只支持 on / sleep / off（没有 toggle）"
        )

    pc = PCDevice(api, did=did)
    method = getattr(pc, POWER_ACTION_METHOD[action])
    try:
        method()
    except NotImplementedError as exc:
        return f"操作未执行：{exc}\n该设备的 MIoT Spec 没有这个动作，请不要重试。"
    except DeviceActionError as exc:
        return f"操作失败：{exc}\n米家接口拒绝了这次动作，请检查设备是否支持。"

    return (
        f"已向「{pc.name}」[did {pc.did}] 发送{POWER_ACTION_LABELS[action]}指令"
        f"（MIoT 动作 {POWER_ACTION_MIOT[action]}）。\n"
        f"米家接口返回成功，但这不代表设备状态已经改变：\n"
        f"米家只确认指令已被接收，设备实际的状态变更需要数秒才会反映到 status 上。\n"
        f"不要立即断言设备已经{POWER_ACTION_LABELS[action]}。"
        f"如需确认，请稍后调用 get_power_status。"
    )


def render_device_spec(model: str) -> str:
    """渲染某型号的 MIoT Spec。**不需要认证**——笔记本走内置 Spec。

    用途：在调用 set_power / 通用透传前确认设备支持哪些属性与动作，
    以及属性的读写权限与枚举取值。
    """
    info = get_device_info(model)
    props = info.get("properties", [])
    actions = info.get("actions", [])
    built_in = ".laptop." in model.lower()

    lines = [
        f"设备型号 {model} 的 MIoT Spec",
        f"来源：{'内置笔记本 Spec（不访问网络）' if built_in else 'home.miot-spec.com'}",
        "",
        f"属性（{len(props)} 个）：",
    ]
    if not props:
        lines.append("  （无）")
    for prop in props:
        rw = {"r": "只读", "rw": "读写", "w": "只写"}.get(prop.get("rw"), prop.get("rw"))
        lines.append(f"  - {prop.get('name')}  [{rw}]  {prop.get('description')}")
        value_list = prop.get("value-list")
        if value_list:
            for item in value_list:
                zh = item.get("desc_zh_cn") or item.get("description")
                lines.append(f"        {item.get('value')} = {zh}")
        elif prop.get("range"):
            lines.append(f"        取值范围 {prop.get('range')}")

    lines.append("")
    lines.append(f"动作（{len(actions)} 个）：")
    if not actions:
        lines.append("  （无）")
    for action in actions:
        lines.append(f"  - {action.get('name')}  {action.get('description')}")

    if built_in:
        lines.append("")
        lines.append(
            "笔记本的这 4 个属性全部只读，对笔记本调用属性写入必然报错，"
            "这是预期行为。可执行的动作只有 turn-on / turn-off / sleep-mode-on。"
        )
    return "\n".join(lines)


# ---------------------------------------------------------------- MCP 工具封装
#
# 下面这些薄封装只做一件事：把渲染函数的异常翻译成调用方能读懂的文本。
# 领域逻辑全部在上面的渲染函数里，测试可以脱离 MCP 直接测它们。


_INSTRUCTIONS = f"""\
miiotpcApi MCP server v{version} —— 米家笔记本/PC 设备查询与电源控制。

回答用户问题前，请先记住这几条判读规则，它们是最容易搞错的地方：

1. **判断开关机只看 status**：8=运行中；非 8 即非运行中
   （1=正在唤醒 / 2=已关机 / 3=已睡眠 / 4=正在关机 / 6=正在进入睡眠）。
2. **isOnline 是联网状态，不是开关机判据。** 关机/睡眠时主板 EC 仍有待机供电、
   联网模块保持在线，所以设备显示「在线」完全可能已经关机。
3. **关机不等于数值过期。** 温度与电量由主板 EC 上报，OS 关机后 EC 仍在工作，
   所以关机设备返回的温度/电量是实时值，可以引用。
4. **设备真正离线（isOnline 为 false）时没有数值。** 所有属性查询都会被跳过、
   返回「无数据」，因为云端只剩最后一次上报的过期快照。此时正确回答是
   「设备离线，查不到当前状态」，**不要编造或推测数值**。
5. 所有工具都返回已解读的中文文本，可以直接引用给用户，不需要自己翻译枚举。
6. 本 server **不提供登录工具**。认证失效时请提醒用户自行执行
   `uvx miiotpcApi@latest login`，扫码必须由人完成。

常用工具：get_power_status 回答「开了吗」；get_full_status 回答
「现在什么情况」；list_devices 列设备拿 did；set_power 执行电源操作
（有副作用，需谨慎）。
"""

server = MCPServer(
    SERVER_NAME,
    title="米家笔记本/PC 控制",
    description="查询与控制米家账号下的笔记本/PC 设备（电源、温度、电量、充电状态）",
    instructions=_INSTRUCTIONS,
    version=version,
)


@server.tool(
    annotations=ToolAnnotations(
        read_only_hint=True,
        idempotent_hint=True,
        destructive_hint=False,
        open_world_hint=True,
    )
)
def list_devices() -> str:
    """列出米家账号下的全部 PC/笔记本设备，返回 did、名称、型号与联网状态。

    这是第一步：后续工具都用 did 定位设备。**本工具不查询任何设备属性**，
    只读设备清单，速度快。

    输出里的「联网状态」是 isOnline，**不代表是否开机**——关机时主板 EC
    待机供电仍保持在线。判断开机请调用 get_power_status。

    若返回「未找到 PC/笔记本设备」，说明设备名/型号不含 pc、电脑、笔记本、
    laptop、desktop、notebook 等关键词，请让用户在米家 APP 中改名。
    """
    try:
        return render_device_list(_get_api())
    except AuthUnavailableError:
        return AUTH_MESSAGE
    except Exception as exc:  # noqa: BLE001 - 工具层不向上抛异常
        return f"查询设备列表失败：{exc}"


@server.tool(
    annotations=ToolAnnotations(
        read_only_hint=True,
        idempotent_hint=True,
        destructive_hint=False,
        open_world_hint=True,
    )
)
def get_power_status(did: str | None = None) -> str:
    """查询笔记本的电源状态，回答「机器开了吗」。

    **判断开关机只看本工具返回的「运行状态」**：8=运行中，非 8 即非运行中。
    输出里的「联网状态」（isOnline）**不代表是否开机**——关机/睡眠时主板 EC
    仍有待机供电、联网模块照样在线，设备会显示「在线」但早已关机。

    参数 did 为空时**批量查询全部笔记本**（推荐，一条命令拿到全部结果）；
    指定 did 时只查那一台。

    本工具只查 status 一个属性，不查温度/电量，因此比 get_full_status 快。
    需要温度、电量、充电状态时请改用 get_full_status。

    设备真正离线时返回「未知——设备已离线」，这**不等于关机**，只是无从得知；
    此时不要断言机器是开着还是关着。
    """
    try:
        return render_power_status(_get_api(), did=did)
    except DeviceNotFoundError:
        return (
            f"未找到 did 为 {did!r} 的设备。\n"
            "请先调用 list_devices 查看可用的 did。"
        )
    except MultipleDevicesFoundError as exc:
        return f"设备定位冲突：{exc}"
    except AuthUnavailableError:
        return AUTH_MESSAGE
    except Exception as exc:  # noqa: BLE001
        return f"查询电源状态失败：{exc}"


@server.tool(
    annotations=ToolAnnotations(
        read_only_hint=True,
        idempotent_hint=True,
        destructive_hint=False,
        open_world_hint=True,
    )
)
def get_full_status(did: str | None = None) -> str:
    """查询笔记本的完整状态：运行状态 + CPU 温度 + 电池电量 + 充电状态。

    参数 did 为空时批量查询全部笔记本；指定 did 时只查那一台。

    **温度与电量在设备关机/睡眠时依然是实时值**，可以引用——它们由主板 EC
    上报，OS 停止后 EC 仍在工作。输出里会注明这一点。

    设备真正离线时**所有数值字段都没有数据**（查询已跳过，云端只剩过期快照），
    此时正确回答是「设备离线，查不到当前状态」，不要编造数值。

    只想知道开没开机的话，用更快的 get_power_status 即可。
    """
    try:
        return render_full_status(_get_api(), did=did)
    except DeviceNotFoundError:
        return (
            f"未找到 did 为 {did!r} 的设备。\n"
            "请先调用 list_devices 查看可用的 did。"
        )
    except MultipleDevicesFoundError as exc:
        return f"设备定位冲突：{exc}"
    except AuthUnavailableError:
        return AUTH_MESSAGE
    except Exception as exc:  # noqa: BLE001
        return f"查询状态失败：{exc}"


@server.tool(
    annotations=ToolAnnotations(
        read_only_hint=False,
        idempotent_hint=False,
        destructive_hint=True,
        open_world_hint=True,
    )
)
def set_power(did: str, action: Literal["on", "sleep", "off"]) -> str:
    """对指定笔记本执行电源操作：唤醒开机 / 睡眠 / 关机。

    **本工具有真实世界的副作用，会影响用户正在使用的电脑。**
    执行前请确认：用户确实要求了这个操作、did 指向的是正确设备、action 取值无误。

    参数：
        did：设备 did（必须，从 list_devices 获取）。电源操作不支持批量。
        action：on=唤醒/开机，sleep=睡眠，off=关机。

    **没有 toggle 这种取值**，也没有「重启」。设备不支持某动作时会返回
    「操作未执行」，那是设备 Spec 的限制，请向用户说明，不要重试。

    返回成功只表示米家接口接受了指令，**不代表设备状态已经改变**——
    状态变更需要数秒。不要紧接着就断言「机器已经关了」，
    要确认请稍后调用 get_power_status。
    """
    try:
        return render_power_action(_get_api(), did=did, action=action)
    except ValueError as exc:
        return f"参数无效：{exc}"
    except DeviceNotFoundError:
        return (
            f"未找到 did 为 {did!r} 的设备，操作未执行。\n"
            "请先调用 list_devices 查看可用的 did——电源操作有副作用，"
            "did 不确定时不要猜测。"
        )
    except MultipleDevicesFoundError as exc:
        return f"设备定位冲突，操作未执行：{exc}"
    except AuthUnavailableError:
        return AUTH_MESSAGE
    except Exception as exc:  # noqa: BLE001
        return f"电源操作失败：{exc}"


@server.tool(
    annotations=ToolAnnotations(
        read_only_hint=True,
        idempotent_hint=True,
        destructive_hint=False,
        open_world_hint=False,
    )
)
def get_device_spec(model: str) -> str:
    """查询某设备型号的 MIoT Spec：支持哪些属性、读写权限、枚举取值、哪些动作。

    参数 model 是**完整型号**，如 `xiaomi.laptop.p59`、`xiaomi.laptop.n56sr`，
    不是简称。完整型号可以从 list_devices 的输出里拿到。

    **不需要认证**：型号含 `.laptop.` 的笔记本走内置 Spec，不访问网络；
    其他米家设备从 home.miot-spec.com 获取。

    用途：在操作设备前确认它到底支持什么。笔记本固定只有 4 个只读属性
    （status / temperature / battery-level / charging-state）和 3 个动作
    （turn-on / turn-off / sleep-mode-on），**没有** manufacturer、
    serial-number、firmware-revision 之类的属性——查询这些会报错，是预期行为。
    """
    try:
        return render_device_spec(model)
    except Exception as exc:  # noqa: BLE001
        return (
            f"获取型号 {model!r} 的设备信息失败：{exc}\n"
            "常见原因是型号写错了（用了简称而不是完整型号）。"
            "请先调用 list_devices 查看每台设备的完整 model。"
        )


def main() -> None:
    """MCP server 入口（stdio 传输）。

    由 console script ``miiotpcApi-mcp`` 调用，注册方式：

        claude mcp add --transport stdio miiotpc \\
            -- uvx --from "miiotpcApi[mcp]@latest" miiotpcApi-mcp

    **``@latest`` 不能省。** 实测裸 ``"miiotpcApi[mcp]"`` 会被 uv 解析到 0.1.0，
    而旧版本没有 ``miiotpcApi-mcp`` 入口，server 起不来。等价的正确写法还有
    ``"miiotpcApi[mcp]==0.2.0"`` 与 ``"miiotpcApi[mcp]>=0.2.0"``。
    """
    server.run(transport="stdio")


if __name__ == "__main__":
    main()
