"""miiotpcApi command-line interface.

miiotpcApi — 米家笔记本/PC 设备控制 CLI
Copyright (C) 2026 comor <304593790@qq.com>

本文件是 mijiaAPI（https://github.com/Do1e/mijia-api, GPL-3.0-or-later）
的衍生作品。原项目著作权归 Do1e <i@do1e.cn> 所有。

本程序是自由软件：你可以在自由软件基金会发布的 GNU 通用公共许可证第 3 版
（或任何更新版本）的条款下重新分发和/或修改它。本程序的分发是希望它有用，
但不提供任何担保。详情请见 <https://www.gnu.org/licenses/>。

完整的衍生声明与上游来源见项目根目录的 NOTICE 文件。
"""

import argparse
import json
import sys
from pathlib import Path
from typing import Sequence

from .api import miiotpcAPI
from .device import MiotDevice, PCDevice, get_device_info
from .version import version

DEFAULT_AUTH_PATH = Path.home() / ".config" / "miiotpc-api" / "auth.json"


def json_object(value: str) -> dict:
    """Parse a command-line JSON object."""
    try:
        result = json.loads(value)
    except json.JSONDecodeError as exc:
        raise argparse.ArgumentTypeError(f"无效 JSON: {exc.msg}") from exc
    if not isinstance(result, dict):
        raise argparse.ArgumentTypeError("必须是 JSON 对象")
    return result


def add_auth_path_argument(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "-p",
        "--auth-path",
        type=Path,
        default=DEFAULT_AUTH_PATH,
        help=f"认证文件路径，默认 {DEFAULT_AUTH_PATH}",
    )


def add_device_arguments(parser: argparse.ArgumentParser, required: bool = True) -> None:
    group = parser.add_mutually_exclusive_group(required=required)
    group.add_argument("--did", help="设备 did")
    group.add_argument("--dev-name", help="设备名称")


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=f"miiotpcApi PC设备控制 CLI (v{version})")
    parser.add_argument("-v", "--version", action="version", version=f"%(prog)s {version}")
    add_auth_path_argument(parser)
    parser.add_argument("-l", "--list-devices", action="store_true", help="列出所有米家设备")
    parser.add_argument("--list-pc", action="store_true", help="仅列出 PC/笔记本设备")
    parser.add_argument("--get-device-info", metavar="MODEL", help="获取设备 MIoT Spec 信息")
    add_device_arguments(parser, required=False)
    pc_actions = parser.add_mutually_exclusive_group()
    pc_actions.add_argument(
        "--power",
        choices=("on", "sleep", "off"),
        help="电源操作：on=唤醒/开机，sleep=睡眠，off=关机",
    )
    pc_actions.add_argument("--temperature", action="store_true", help="获取 CPU 温度")
    pc_actions.add_argument("--battery", action="store_true", help="获取电池电量")
    pc_actions.add_argument("--charging-state", action="store_true", help="获取充电状态")
    pc_actions.add_argument(
        "--status",
        action="store_true",
        help="获取状态概览；不指定 --did/--dev-name 时批量查询所有笔记本",
    )
    pc_actions.add_argument(
        "--get-prop",
        metavar="PROP",
        help="按属性名读取（笔记本: status/temperature/battery-level/charging-state）",
    )
    pc_actions.add_argument("--list-properties", action="store_true", help="列出设备支持的属性")
    pc_actions.add_argument("--list-actions", action="store_true", help="列出设备支持的动作")

    subparsers = parser.add_subparsers(dest="command")

    login_cmd = subparsers.add_parser("login", help="二维码登录米家账号")
    add_auth_path_argument(login_cmd)

    get_cmd = subparsers.add_parser("get", help="获取设备属性")
    add_auth_path_argument(get_cmd)
    add_device_arguments(get_cmd)
    get_cmd.add_argument("--prop-name", required=True, help="MIoT Spec 属性名")

    set_cmd = subparsers.add_parser("set", help="设置设备属性")
    add_auth_path_argument(set_cmd)
    add_device_arguments(set_cmd)
    set_cmd.add_argument("--prop-name", required=True, help="MIoT Spec 属性名")
    set_cmd.add_argument("--value", required=True, help="属性值")

    action_cmd = subparsers.add_parser("action", help="执行设备动作")
    add_auth_path_argument(action_cmd)
    add_device_arguments(action_cmd)
    action_cmd.add_argument("--action-name", required=True, help="MIoT Spec 动作名")
    action_cmd.add_argument("--params", type=json_object, help='动作参数 JSON 对象，例如 {"value": [2]}')

    return parser.parse_args(argv)


def init_api(auth_path: Path) -> miiotpcAPI:
    """Create an authenticated API client or raise a user-facing error."""
    auth_path = auth_path / "auth.json" if auth_path.is_dir() else auth_path
    if not auth_path.exists():
        raise RuntimeError(f"认证文件不存在: {auth_path}\n请运行 'miiotpcApi login' 扫码登录")

    try:
        api = miiotpcAPI(auth_data_path=auth_path)
    except json.JSONDecodeError as exc:
        raise RuntimeError(f"认证文件已损坏: {auth_path}\n请运行 'miiotpcApi login' 重新登录") from exc

    if not api.available:
        try:
            api._refresh_token()
        except Exception as exc:
            raise RuntimeError(f"认证已失效且刷新失败: {auth_path}\n请运行 'miiotpcApi login' 重新登录") from exc
    return api


def print_devices(devices: list[dict], heading: str) -> None:
    if not devices:
        print(f"未找到{heading}。")
        return
    print(f"{heading}:")
    for device in devices:
        online = "在线" if device.get("isOnline") else "离线"
        print(f"  - {device.get('name', '<未命名设备>')}")
        print(f"    did: {device.get('did', '<未知>')}")
        print(f"    model: {device.get('model', '<未知>')}")
        print(f"    状态: {online}")


def handle_get(api: miiotpcAPI, args: argparse.Namespace) -> None:
    device = MiotDevice(api, did=args.did, dev_name=args.dev_name)
    value = device.get(args.prop_name)
    print(f"{device.name} ({device.did}) 的 {args.prop_name} = {value}")


def handle_set(api: miiotpcAPI, args: argparse.Namespace) -> None:
    device = MiotDevice(api, did=args.did, dev_name=args.dev_name)
    device.set(args.prop_name, args.value)
    print(f"{device.name} ({device.did}) 的 {args.prop_name} 已设置为 {args.value}")


def handle_action(api: miiotpcAPI, args: argparse.Namespace) -> None:
    device = MiotDevice(api, did=args.did, dev_name=args.dev_name)
    device.run_action(args.action_name, **(args.params or {}))
    print(f"{device.name} ({device.did}) 的动作 {args.action_name} 执行成功")


def handle_pc(api: miiotpcAPI, args: argparse.Namespace) -> None:
    # --status 不指定设备时，批量查询所有笔记本。
    # 这样智能体一次调用就能拿到全部设备的 isOnline / data_is_live，
    # 不必先 list 再逐台查询（N+1 次调用）。
    if args.status and not args.did and not args.dev_name:
        devices = api.find_pc_devices()
        if not devices:
            print("未找到 PC/笔记本设备。")
            return
        results = []
        for entry in devices:
            try:
                pc = PCDevice(api, did=entry["did"], sleep_time=0)
                results.append(pc.status)
            except Exception as exc:
                results.append({
                    "name": entry.get("name"),
                    "model": entry.get("model"),
                    "did": entry.get("did"),
                    "isOnline": bool(entry.get("isOnline")),
                    "data_is_live": False,
                    "error": str(exc),
                })
        print(json.dumps(results, indent=2, ensure_ascii=False))
        return

    if not args.did and not args.dev_name:
        raise RuntimeError("必须指定 --did 或 --dev-name；批量查看状态请用 '--status'（不带设备参数）")

    pc = PCDevice(api, did=args.did, dev_name=args.dev_name)
    if args.status:
        print(json.dumps(pc.status, indent=2, ensure_ascii=False))
    elif args.list_properties:
        for name, prop in pc._device.prop_list.items():
            if "_" in name:
                continue  # 跳过下划线别名
            rw = {"r": "只读", "rw": "读写", "w": "只写"}.get(prop.rw, prop.rw)
            m = prop.method
            print(f"{name:<20} siid={m.get('siid', '?'):<3} piid={m.get('piid', '?'):<3} {rw:<4} {prop.desc}")
    elif args.list_actions:
        for name, act in pc._device.action_list.items():
            m = act.method
            print(f"{name:<20} siid={m.get('siid', '?'):<3} aiid={m.get('aiid', '?'):<3} {act.desc}")
    elif args.get_prop:
        value = pc.get_prop(args.get_prop)
        print(f"{pc.name} 的 {args.get_prop} = {value}")
    elif args.power == "on":
        pc.power_on()
        print(f"{pc.name} 已开机")
    elif args.power == "sleep":
        pc.sleep()
        print(f"{pc.name} 已进入睡眠")
    elif args.power == "off":
        pc.power_off()
        print(f"{pc.name} 已关机")
    elif args.temperature:
        print(f"{pc.name} CPU 温度: {pc.get_temperature()} °C")
    elif args.battery:
        print(f"{pc.name} 电池电量: {pc.get_battery_level()}%")
    elif args.charging_state:
        state = pc.get_charging_state()
        label = {1: "插电状态", 2: "电池供电"}.get(state, str(state))
        print(f"{pc.name} 充电状态: {label} ({state})")
    else:
        raise RuntimeError("请指定操作，例如 --status 或 --power on/sleep/off")


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv)

    try:
        if args.get_device_info:
            print(json.dumps(get_device_info(args.get_device_info), indent=2, ensure_ascii=False))
            return 0

        if args.command == "login":
            api = miiotpcAPI(auth_data_path=args.auth_path)
            if not api.available:
                api.login()
            else:
                print("认证仍然有效，无需重新登录")
            return 0

        has_pc_action = any(
            getattr(args, name, None) not in (None, False)
            for name in (
                "power", "temperature", "battery", "charging_state", "status",
                "get_prop", "list_properties", "list_actions",
            )
        )
        if not args.command and not args.list_devices and not args.list_pc and not has_pc_action:
            parse_args(["--help"])
            return 0

        api = init_api(args.auth_path)
        if args.list_devices:
            print_devices(api.get_devices_list(), "设备列表")
        if args.list_pc:
            print_devices(api.find_pc_devices(), "PC/笔记本设备")

        if args.command == "get":
            handle_get(api, args)
        elif args.command == "set":
            handle_set(api, args)
        elif args.command == "action":
            handle_action(api, args)
        elif has_pc_action:
            handle_pc(api, args)
        return 0
    except KeyboardInterrupt:
        print("操作已取消", file=sys.stderr)
        return 130
    except Exception as exc:
        print(f"错误: {exc}", file=sys.stderr)
        return 1


def cli() -> None:
    """Console-script entry point."""
    raise SystemExit(main())


if __name__ == "__main__":
    cli()
